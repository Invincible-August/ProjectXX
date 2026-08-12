"""
机缘（聊天室红包）应用服务（M7 L5）。

拆分权威在服务端；领取行锁；过期惰性退邮件。
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time_utils import ensure_aware_utc, now_utc
from app.db.models import Character, User
from app.db.models.heritage import HeritageClaim, HeritageDailyCounter, HeritagePacket
from app.domain.channel_membership import ChannelMembership, parse_channel_ref, room_id_for
from app.domain.heritage_rules import build_share_plan, fixed_recycle_remainder
from app.domain.trade_rules import item_may_trade, parse_item_lines
from app.domain.ws_protocol import (
    TYPE_HERITAGE_CLAIMED,
    TYPE_HERITAGE_CREATED,
    TYPE_HERITAGE_EXPIRED,
)
from app.schemas.common import AppError
from app.services.currency_ledger_service import CurrencyLedgerService
from app.services.inventory_service import InventoryService
from app.services.mail_service import MailService
from app.services.play_gate import PlayGate
from app.services.realm_config import get_game_config
from app.services.ws_hub_service import get_ws_hub

logger = logging.getLogger(__name__)


def require_heritage_enabled() -> None:
    """机缘总闸。"""
    settings = get_settings()
    if not bool(getattr(settings, "heritage_system_enabled", True)):
        raise AppError(code=40000, message="机缘系统未开放", http_status=403)


class HeritageService:
    """发机缘 / 开缘 / 列表。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._gate = PlayGate(session)
        self._membership = ChannelMembership(session)
        self._inv = InventoryService(session)
        self._ledger = CurrencyLedgerService(session)

    def _cfg(self):
        return get_game_config().chat_heritage

    def _expire_sec(self) -> int:
        settings = get_settings()
        env_sec = int(getattr(settings, "heritage_expire_sec", 0) or 0)
        if env_sec > 0:
            return env_sec
        return int(self._cfg().expire_sec or 86400)

    async def list_active(self, user: User, *, channel_ref: str) -> dict[str, Any]:
        """某频道进行中机缘包。"""
        require_heritage_enabled()
        character = await self._gate.require_character(user)
        cref = parse_channel_ref(channel_ref)
        if cref is None:
            raise AppError(code=40000, message="频道无效", http_status=400)
        ok, reason = await self._membership.can_access(character, cref)
        if not ok:
            raise AppError(code=40130, message=reason or "频道无权限", http_status=403)
        await self._lazy_expire_channel(cref.channel_ref)
        await self._purge_closed_packets(cref.channel_ref)
        await self._cleanup_orphan_claims()
        lim = int(self._cfg().active_list_limit or 30)
        rows = (
            await self._session.execute(
                select(HeritagePacket)
                .where(
                    HeritagePacket.channel_ref == cref.channel_ref,
                    HeritagePacket.status == "open",
                )
                .order_by(HeritagePacket.id.desc())
                .limit(lim),
            )
        ).scalars().all()
        items = []
        for row in rows:
            items.append(await self._packet_public(row, viewer_id=character.id))
        return {
            "channel_ref": cref.channel_ref,
            "items": items,
            # 前端本会话保留已抢完条数（退出/关浏览器清空）
            "session_finished_keep": int(self._cfg().session_finished_keep or 20),
        }

    async def create(
        self,
        user: User,
        *,
        channel_ref: str,
        mode: str,
        share_count: int,
        spirit_stones: int,
        items: list[dict[str, Any]],
        note_zh: str | None = None,
    ) -> dict[str, Any]:
        """
        发机缘：扣发送方 → 预拆份 → 广播卡片。

        Args:
            user: 发送方。
            channel_ref: 频道。
            mode: random | fixed。
            share_count: 份数。
            spirit_stones: 总灵石。
            items: 物品行。
            note_zh: 附言。

        Returns:
            dict: 含 packet 公开体。
        """
        require_heritage_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        if character.status in ("awaiting_ferry", "tribulation", "reincarnating"):
            raise AppError(code=40000, message="当前状态不可发机缘", http_status=400)

        cref = parse_channel_ref(channel_ref)
        if cref is None:
            raise AppError(code=40000, message="频道无效", http_status=400)
        allowed = set(self._cfg().allowed_channel_types or ())
        if cref.channel_type not in allowed:
            raise AppError(code=40130, message="该频道不可发机缘", http_status=403)
        ok, reason = await self._membership.can_access(character, cref)
        if not ok:
            raise AppError(code=40130, message=reason or "频道无权限", http_status=403)

        mode_l = str(mode or "").strip().lower()
        if mode_l not in {"random", "fixed"}:
            raise AppError(code=40000, message="模式须为拼手气或定额", http_status=400)
        cfg = self._cfg()
        shares = int(share_count)
        if shares < int(cfg.min_shares) or shares > int(cfg.max_shares):
            raise AppError(
                code=40000,
                message=f"份数须在 {cfg.min_shares}～{cfg.max_shares}",
                http_status=400,
            )
        stones = max(0, int(spirit_stones or 0))
        lines = parse_item_lines(items)
        if stones <= 0 and not lines:
            raise AppError(code=40000, message="机缘内容不可为空", http_status=400)
        max_stone = int(cfg.max_spirit_stones or 0)
        if max_stone > 0 and stones > max_stone:
            raise AppError(code=40000, message="灵石超过单包上限", http_status=400)
        if len(lines) > int(cfg.max_item_lines or 8):
            raise AppError(code=40000, message="物品行超限", http_status=400)
        await self._assert_tradable(lines)
        await self._consume_daily_cap(character.id, count=1, spirit=stones)
        # 发包前清孤儿领取行，避免旧库 id 复用后误判「已开过这份缘」
        await self._cleanup_orphan_claims()

        # 校验库存后扣
        counts = await self._inv.material_counts(character.id)
        inv = get_game_config().inventory
        for line in lines:
            item_id = str(line["item_id"])
            need = int(line["quantity"])
            if int(counts.get(item_id, 0)) < need:
                defn = inv.items.get(item_id)
                raise AppError(
                    code=40055,
                    message=f"物品不足：{(defn.name if defn else item_id)}",
                    http_status=400,
                )
        if stones > 0:
            await self._ledger.adjust_spirit_stones(
                character,
                delta=-stones,
                reason="heritage_send",
                note_zh="发机缘",
                ref_type="heritage",
            )
        for line in lines:
            await self._inv._remove_item_id(
                character.id,
                str(line["item_id"]),
                int(line["quantity"]),
            )

        seed = secrets.randbits(63)
        plan = build_share_plan(
            spirit_stones=stones,
            items=lines,
            share_count=shares,
            mode=mode_l,
            seed=seed,
            remainder_policy=str(cfg.fixed_remainder or "last_share"),
        )
        # fixed+recycle：余数进系统回收
        if mode_l == "fixed" and str(cfg.fixed_remainder) == "recycle":
            rem = fixed_recycle_remainder(stones, shares)
            if rem > 0:
                await self._ledger.adjust_spirit_stones(
                    None,
                    delta=rem,
                    reason="heritage_fixed_recycle",
                    note_zh="机缘定额余数回收",
                    ref_type="heritage",
                )

        expires = now_utc() + timedelta(seconds=self._expire_sec())
        note = (note_zh or "").strip()[:64]
        row = HeritagePacket(
            channel_type=cref.channel_type,
            channel_ref=cref.channel_ref,
            sender_character_id=character.id,
            mode=mode_l,
            share_count=shares,
            shares_claimed=0,
            spirit_stones_total=stones,
            items_json=json.dumps(lines, ensure_ascii=False),
            shares_plan_json=json.dumps(plan, ensure_ascii=False),
            next_share_index=0,
            seed=seed,
            status="open",
            note_zh=note,
            expires_at=expires,
        )
        self._session.add(row)
        await self._session.flush()

        public = await self._packet_public(row, viewer_id=character.id)
        await self._push(cref.channel_ref, TYPE_HERITAGE_CREATED, public)
        logger.info(
            "heritage create id=%s channel=%s mode=%s shares=%s stones=%s",
            row.id,
            cref.channel_ref,
            mode_l,
            shares,
            stones,
        )
        return {
            "message": "机缘已发出",
            "packet": public,
            "character": await self._character_public(character),
        }

    async def claim(self, user: User, packet_id: int) -> dict[str, Any]:
        """
        开缘领取一份。

        Args:
            user: 领取人。
            packet_id: 包 id。

        Returns:
            dict: 领取摘要。
        """
        require_heritage_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        row = await self._session.get(HeritagePacket, int(packet_id))
        if row is None:
            raise AppError(code=40140, message="机缘不存在或已过期", http_status=404)
        await self._lazy_expire_one(row)
        if row.status != "open":
            raise AppError(code=40140, message="机缘已领完或已过期", http_status=400)

        ok, reason = await self._membership.can_access(character, row.channel_ref)
        if not ok:
            raise AppError(code=40140, message=reason or "非频道成员不可开缘", http_status=403)

        # 同人限领
        existing = (
            await self._session.execute(
                select(HeritageClaim).where(
                    HeritageClaim.packet_id == row.id,
                    HeritageClaim.character_id == character.id,
                ),
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise AppError(code=40140, message="你已开过这份缘", http_status=400)
        if int(row.shares_claimed) >= int(row.share_count):
            row.status = "exhausted"
            row.closed_at = now_utc()
            await self._session.flush()
            raise AppError(code=40140, message="机缘已领完", http_status=400)

        plan = json.loads(row.shares_plan_json or "[]")
        idx = int(row.next_share_index)
        if idx < 0 or idx >= len(plan):
            raise AppError(code=40140, message="机缘已领完", http_status=400)
        share = plan[idx]
        stone_get = int(share.get("spirit_stones") or 0)
        item_get = list(share.get("items") or [])

        # 入包
        if stone_get > 0:
            await self._ledger.adjust_spirit_stones(
                character,
                delta=stone_get,
                reason="heritage_claim",
                note_zh="开缘得灵石",
                ref_type="heritage",
                ref_id=str(row.id),
            )
        inv = get_game_config().inventory
        for line in item_get:
            item_id = str(line["item_id"])
            defn = inv.items.get(item_id)
            item_type = defn.item_type if defn else "material"
            await self._inv.add_item(
                character.id,
                item_type=item_type,
                item_id=item_id,
                quantity=int(line["quantity"]),
                bag_kind="normal",
            )

        claim = HeritageClaim(
            packet_id=row.id,
            character_id=character.id,
            share_index=idx,
            spirit_stones=stone_get,
            items_json=json.dumps(item_get, ensure_ascii=False),
        )
        self._session.add(claim)
        row.next_share_index = idx + 1
        row.shares_claimed = int(row.shares_claimed) + 1
        if int(row.shares_claimed) >= int(row.share_count):
            row.status = "exhausted"
            row.closed_at = now_utc()
        await self._session.flush()

        hide = bool(self._cfg().claim_broadcast_hide_amount)
        claim_public = {
            "packet_id": row.id,
            "channel_ref": row.channel_ref,
            "claimer_character_id": character.id,
            "claimer_name": character.name,
            "spirit_stones": None if hide else stone_get,
            "items": [] if hide else item_get,
            "shares_claimed": row.shares_claimed,
            "share_count": row.share_count,
            "status": row.status,
            # 供客户端丢弃「旧包 id 复用」后的迟到 claimed 推送
            "packet_created_at": row.created_at.isoformat() if row.created_at else None,
            "message_zh": f"「{character.name}」开缘成功",
        }
        await self._push(row.channel_ref, TYPE_HERITAGE_CLAIMED, claim_public)
        logger.info(
            "heritage claim packet=%s character=%s stones=%s",
            row.id,
            character.id,
            stone_get,
        )
        packet_public = await self._packet_public(row, viewer_id=character.id)
        # 抢完后可物理删除记录；响应仍带回最终态供前端立刻移除
        if row.status == "exhausted":
            await self._purge_packet_row(row)
        return {
            "message": "开缘成功",
            "claimed": {"spirit_stones": stone_get, "items": item_get},
            "packet": packet_public,
            "character": await self._character_public(character),
        }

    # ----- helpers -----

    async def _purge_closed_packets(self, channel_ref: str) -> None:
        """惰性删除本频道已抢完 / 已过期机缘行（未抢完保留）。"""
        if not bool(getattr(self._cfg(), "purge_closed_packets", True)):
            return
        rows = (
            await self._session.execute(
                select(HeritagePacket).where(
                    HeritagePacket.channel_ref == channel_ref,
                    HeritagePacket.status.in_(("exhausted", "expired")),
                ),
            )
        ).scalars().all()
        for row in rows:
            # 走单条 purge：先删 claims 再删包，避免外键未开时残留
            await self._purge_packet_row(row)
        if rows:
            logger.info(
                "heritage purge closed channel=%s count=%s",
                channel_ref,
                len(rows),
            )

    async def _purge_packet_row(self, row: HeritagePacket) -> None:
        """删除单条已结束机缘；显式清领取行（防 SQLite 未开 FK 时残留）。"""
        if not bool(getattr(self._cfg(), "purge_closed_packets", True)):
            return
        if row.status not in {"exhausted", "expired"}:
            return
        packet_id = int(row.id)
        # 显式删除领取记录，避免外键未启用时 id 复用后误判「已开过这份缘」
        claims = (
            await self._session.execute(
                select(HeritageClaim).where(HeritageClaim.packet_id == packet_id),
            )
        ).scalars().all()
        for claim in claims:
            await self._session.delete(claim)
        await self._session.delete(row)
        await self._session.flush()
        logger.info("heritage purge packet=%s claims=%s", packet_id, len(claims))

    async def _cleanup_orphan_claims(self) -> None:
        """删除已无对应机缘包的领取行（历史库 FK 未开时的残留）。"""
        packet_ids = select(HeritagePacket.id)
        result = await self._session.execute(
            delete(HeritageClaim).where(HeritageClaim.packet_id.not_in(packet_ids)),
        )
        removed = int(result.rowcount or 0)
        if removed > 0:
            await self._session.flush()
            logger.info("heritage cleanup orphan claims count=%s", removed)

    async def _lazy_expire_channel(self, channel_ref: str) -> None:
        rows = (
            await self._session.execute(
                select(HeritagePacket).where(
                    HeritagePacket.channel_ref == channel_ref,
                    HeritagePacket.status == "open",
                ),
            )
        ).scalars().all()
        for row in rows:
            await self._lazy_expire_one(row)

    async def _lazy_expire_one(self, row: HeritagePacket) -> None:
        if row.status != "open":
            return
        if now_utc() < ensure_aware_utc(row.expires_at):
            return
        await self._refund_remaining(row, reason="expired")
        row.status = "expired"
        row.closed_at = now_utc()
        await self._session.flush()
        await self._push(
            row.channel_ref,
            TYPE_HERITAGE_EXPIRED,
            {
                "packet_id": row.id,
                "channel_ref": row.channel_ref,
                "message_zh": "未领机缘已退回，请查收邮件",
            },
        )

    async def _refund_remaining(self, row: HeritagePacket, *, reason: str) -> None:
        """退还未领份给发送方。"""
        plan = json.loads(row.shares_plan_json or "[]")
        idx = int(row.next_share_index)
        remain_stones = 0
        remain_items: dict[str, int] = {}
        for share in plan[idx:]:
            remain_stones += int(share.get("spirit_stones") or 0)
            for line in share.get("items") or []:
                iid = str(line["item_id"])
                remain_items[iid] = remain_items.get(iid, 0) + int(line["quantity"])
        if remain_stones <= 0 and not remain_items:
            return
        item_lines = [
            {"item_id": k, "quantity": v} for k, v in remain_items.items() if v > 0
        ]
        policy = str(self._cfg().expire_refund or "mail")
        sender = await self._session.get(Character, row.sender_character_id)
        if sender is None:
            return
        if policy == "inventory":
            if remain_stones > 0:
                await self._ledger.adjust_spirit_stones(
                    sender,
                    delta=remain_stones,
                    reason="heritage_expire_refund",
                    note_zh="机缘过期退回",
                    ref_type="heritage",
                    ref_id=str(row.id),
                )
            inv = get_game_config().inventory
            for line in item_lines:
                defn = inv.items.get(str(line["item_id"]))
                await self._inv.add_item(
                    sender.id,
                    item_type=defn.item_type if defn else "material",
                    item_id=str(line["item_id"]),
                    quantity=int(line["quantity"]),
                    bag_kind="normal",
                )
        else:
            await MailService(self._session).send_system(
                to_character_id=sender.id,
                subject_zh="未领机缘已退回",
                body_zh=f"你发出的机缘（#{row.id}）已过期，未领部分已退回，请领取附件。",
                reason="heritage_expire",
                spirit_stones=remain_stones,
                items=item_lines,
            )
        logger.info(
            "heritage refund packet=%s reason=%s stones=%s items=%s",
            row.id,
            reason,
            remain_stones,
            item_lines,
        )

    async def _assert_tradable(self, lines: list[dict[str, Any]]) -> None:
        inv = get_game_config().inventory
        for line in lines:
            defn = inv.items.get(str(line["item_id"]))
            if defn is None:
                raise AppError(
                    code=40000,
                    message=f"未知物品：{line['item_id']}",
                    http_status=400,
                )
            ok, reason = item_may_trade(
                tradable=bool(defn.tradable),
                bound=bool(defn.bound),
                unique=bool(getattr(defn, 'unique', False)),
            )
            if not ok:
                raise AppError(
                    code=40111,
                    message=f"「{defn.name}」{reason}",
                    http_status=400,
                )

    async def _consume_daily_cap(self, character_id: int, *, count: int, spirit: int) -> None:
        cfg = self._cfg()
        day_key = now_utc().strftime("%Y-%m-%d")
        row = (
            await self._session.execute(
                select(HeritageDailyCounter).where(
                    HeritageDailyCounter.character_id == character_id,
                    HeritageDailyCounter.day_key == day_key,
                ),
            )
        ).scalar_one_or_none()
        if row is None:
            row = HeritageDailyCounter(
                character_id=character_id,
                day_key=day_key,
                send_count=0,
                spirit_sum=0,
            )
            self._session.add(row)
            await self._session.flush()
        if int(row.send_count) + count > int(cfg.daily_send_cap or 20):
            raise AppError(code=40000, message="今日发机缘次数已达上限", http_status=400)
        if int(row.spirit_sum) + spirit > int(cfg.daily_spirit_cap or 200000):
            raise AppError(code=40000, message="今日发机缘灵石已达上限", http_status=400)
        row.send_count = int(row.send_count) + count
        row.spirit_sum = int(row.spirit_sum) + spirit
        await self._session.flush()

    async def _packet_public(
        self,
        row: HeritagePacket,
        *,
        viewer_id: int,
    ) -> dict[str, Any]:
        sender = await self._session.get(Character, row.sender_character_id)
        claimed_self = (
            await self._session.execute(
                select(HeritageClaim.id).where(
                    HeritageClaim.packet_id == row.id,
                    HeritageClaim.character_id == viewer_id,
                ),
            )
        ).scalar_one_or_none()
        mode_zh = "拼手气" if row.mode == "random" else "定额均分"
        raw_items = json.loads(row.items_json or "[]")
        inv = get_game_config().inventory
        items_public: list[dict[str, Any]] = []
        for line in raw_items:
            if not isinstance(line, dict):
                continue
            iid = str(line.get("item_id") or "")
            defn = inv.items.get(iid)
            items_public.append(
                {
                    "item_id": iid,
                    "quantity": int(line.get("quantity") or 0),
                    "name": defn.name if defn else iid,
                },
            )
        return {
            "id": row.id,
            "channel_type": row.channel_type,
            "channel_ref": row.channel_ref,
            "room_id": room_id_for(row.channel_ref),
            "sender_character_id": row.sender_character_id,
            "sender_name": sender.name if sender else str(row.sender_character_id),
            "mode": row.mode,
            "mode_label_zh": mode_zh,
            "share_count": row.share_count,
            "shares_claimed": row.shares_claimed,
            "spirit_stones_total": int(row.spirit_stones_total),
            "items": items_public,
            "status": row.status,
            "note_zh": row.note_zh,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "already_claimed": claimed_self is not None,
            "can_claim": (
                row.status == "open"
                and claimed_self is None
                and int(row.shares_claimed) < int(row.share_count)
            ),
        }

    async def _push(self, channel_ref: str, msg_type: str, payload: dict[str, Any]) -> None:
        settings = get_settings()
        if not bool(getattr(settings, "chat_ws_push_enabled", True)):
            return
        if not bool(getattr(settings, "ws_enabled", True)):
            return
        hub = get_ws_hub()
        room_id = room_id_for(channel_ref)
        hub.ensure_room(room_id, kind="chat")
        await hub.broadcast_room(room_id, msg_type, payload)

    async def _character_public(self, character: Character) -> dict[str, Any]:
        from app.services.character_service import CharacterService

        await self._session.refresh(character)
        return (
            await CharacterService(self._session).enrich_public(character)
        ).model_dump(mode="json")
