"""
邮件与赠送应用服务（M7 L3）。

领取幂等；系统退回/赠送附件经邮件权威入包。
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time_utils import ensure_aware_utc, now_utc
from app.db.models import Character, User
from app.db.models.mail import GiftDailyCounter, MailMessage
from app.domain.mail_rules import (
    attachments_empty,
    estimate_gift_spirit_value,
    normalize_attachments,
)
from app.domain.trade_rules import item_may_trade, parse_item_lines
from app.schemas.common import AppError
from app.services.currency_ledger_service import CurrencyLedgerService
from app.services.friend_service import FriendService
from app.services.inventory_service import InventoryService
from app.services.play_gate import PlayGate
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)


def require_mail_enabled() -> None:
    """邮件总闸。"""
    settings = get_settings()
    if not bool(getattr(settings, "mail_system_enabled", True)):
        raise AppError(code=40000, message="邮件系统未开放", http_status=403)


class MailService:
    """邮件 / 赠送用例。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._gate = PlayGate(session)
        self._inv = InventoryService(session)
        self._ledger = CurrencyLedgerService(session)

    def _cfg(self):
        return get_game_config().mail

    async def unread_count(self, character_id: int) -> int:
        """未读且未过期清理后的邮件数（含未领附件）。"""
        await self._expire_for_character(character_id)
        rows = (
            await self._session.execute(
                select(MailMessage).where(
                    MailMessage.to_character_id == character_id,
                    MailMessage.read_at.is_(None),
                ),
            )
        ).scalars().all()
        return len(list(rows))

    async def list_mail(self, user: User) -> dict[str, Any]:
        """收件箱列表。"""
        require_mail_enabled()
        character = await self._gate.require_character(user)
        await self._expire_for_character(character.id)
        limit = int(self._cfg().list_limit)
        rows = (
            await self._session.execute(
                select(MailMessage)
                .where(MailMessage.to_character_id == character.id)
                .order_by(MailMessage.id.desc())
                .limit(limit),
            )
        ).scalars().all()
        # 打开列表：无附件可自动标已读；有附件仍未读直到领取或显式读
        items = []
        for row in rows:
            items.append(await self._public(row))
        return {
            "items": items,
            "unread": await self.unread_count(character.id),
        }

    async def mark_read(self, user: User, mail_id: int) -> dict[str, Any]:
        """标记已读（不领取附件）。"""
        require_mail_enabled()
        character = await self._gate.require_character(user)
        row = await self._get_owned(character.id, mail_id)
        if row.read_at is None:
            row.read_at = now_utc()
            await self._session.flush()
        return {"mail": await self._public(row)}

    async def claim(self, user: User, mail_id: int) -> dict[str, Any]:
        """
        领取附件（幂等：已领 → 40120）。

        Args:
            user: 当前用户。
            mail_id: 邮件 id。

        Returns:
            dict: 领取结果。
        """
        require_mail_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        await self._expire_for_character(character.id)
        row = await self._get_owned(character.id, mail_id)
        if row.claimed_at is not None:
            raise AppError(code=40120, message="附件已领取或不存在", http_status=400)
        att = json.loads(row.attachments_json or "{}")
        if attachments_empty(att):
            # 无附件：标已读已领
            row.claimed_at = now_utc()
            row.read_at = row.read_at or row.claimed_at
            await self._session.flush()
            return {
                "message": "无附件可领",
                "mail": await self._public(row),
                "character": await self._character_public(character),
            }
        await self._deliver_attachments(character, att, ref_id=str(row.id))
        row.claimed_at = now_utc()
        row.read_at = row.read_at or row.claimed_at
        # 清空附件 JSON 防重复展示；已领状态靠 claimed_at
        row.attachments_json = json.dumps(
            {"spirit_stones": 0, "items": [], "claimed_snapshot": att},
            ensure_ascii=False,
        )
        await self._session.flush()
        logger.info("mail claim character_id=%s mail_id=%s", character.id, mail_id)
        return {
            "message": "附件已入包",
            "claimed": att,
            "mail": await self._public(row),
            "character": await self._character_public(character),
        }

    async def send_system(
        self,
        *,
        to_character_id: int,
        subject_zh: str,
        body_zh: str,
        reason: str,
        spirit_stones: int = 0,
        items: list[dict[str, Any]] | None = None,
        from_character_id: int | None = None,
        mail_kind: str = "system",
    ) -> MailMessage:
        """
        发送系统信（含退回/赠送投递）。内部 API，无用户闸。

        Args:
            to_character_id: 收件人。
            subject_zh: 标题（中文）。
            body_zh: 正文。
            reason: 机读原因。
            spirit_stones: 附件灵石。
            items: 附件物品（须已从发送方扣出或新建）。
            from_character_id: 可选发件人。
            mail_kind: system / gift。

        Returns:
            MailMessage: 新建行。
        """
        att = normalize_attachments(spirit_stones=spirit_stones, items=items)
        cfg = self._cfg()
        if len(att["items"]) > int(cfg.max_attachment_lines):
            raise AppError(code=40000, message="附件物品行超限", http_status=400)
        max_stone = int(cfg.max_attachment_spirit_stones or 0)
        if max_stone > 0 and int(att["spirit_stones"]) > max_stone:
            raise AppError(code=40000, message="附件灵石超限", http_status=400)
        expires = now_utc() + timedelta(days=int(cfg.retain_days or 30))
        row = MailMessage(
            mail_kind=mail_kind,
            to_character_id=int(to_character_id),
            from_character_id=from_character_id,
            reason=reason,
            subject_zh=str(subject_zh)[:64],
            body_zh=str(body_zh)[: int(cfg.max_body_len)],
            attachments_json=json.dumps(att, ensure_ascii=False),
            expires_at=expires,
        )
        self._session.add(row)
        await self._session.flush()
        logger.info(
            "mail system to=%s reason=%s id=%s",
            to_character_id,
            reason,
            row.id,
        )
        return row

    async def send_player_mail(
        self,
        user: User,
        *,
        to_character_id: int | None,
        to_name: str | None,
        subject_zh: str,
        body_zh: str,
    ) -> dict[str, Any]:
        """玩家无附件信（可选；赠送走 gifts）。"""
        require_mail_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        target = await self._resolve_target(to_character_id, to_name)
        if target.id == character.id:
            raise AppError(code=40000, message="不可给自己写信", http_status=400)
        subject = (subject_zh or "").strip() or "道友来信"
        body = (body_zh or "").strip()
        if len(body) > int(self._cfg().max_body_len):
            raise AppError(code=40000, message="正文过长", http_status=400)
        row = await self.send_system(
            to_character_id=target.id,
            subject_zh=subject,
            body_zh=body,
            reason="player_mail",
            from_character_id=character.id,
            mail_kind="player",
        )
        return {
            "message": f"已送信给「{target.name}」",
            "mail_id": row.id,
        }

    async def send_gift(
        self,
        user: User,
        *,
        to_character_id: int | None,
        to_name: str | None,
        spirit_stones: int,
        items: list[dict[str, Any]],
        note_zh: str | None = None,
    ) -> dict[str, Any]:
        """
        赠送：扣发送方 → 邮件附件投递给道友。

        Args:
            user: 发送方。
            to_character_id: 目标 id。
            to_name: 目标道号。
            spirit_stones: 赠送灵石。
            items: 赠送物品。
            note_zh: 附言。

        Returns:
            dict: 结果。
        """
        require_mail_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        if character.status in ("awaiting_ferry", "tribulation", "reincarnating"):
            raise AppError(code=40000, message="当前状态不可赠送", http_status=400)
        target = await self._resolve_target(to_character_id, to_name)
        if target.id == character.id:
            raise AppError(code=40000, message="不可赠送给自己", http_status=400)

        gift_cfg = self._cfg().gift
        if bool(gift_cfg.get("require_friend", True)):
            ok = await FriendService(self._session).are_friends(character.id, target.id)
            if not ok:
                raise AppError(code=40110, message="仅可赠送给道友", http_status=400)

        lines = parse_item_lines(items)
        stones = max(0, int(spirit_stones or 0))
        if stones <= 0 and not lines:
            raise AppError(code=40000, message="赠送内容不可为空", http_status=400)
        await self._assert_tradable(lines)

        # 日限额估价：优先物品定义上的 spirit_value，否则用 gift.default_item_spirit_value
        inv = get_game_config().inventory
        default_unit = int(gift_cfg.get("default_item_spirit_value") or 10)
        item_values: dict[str, int] = {}
        for iid, defn in inv.items.items():
            raw_val = int(getattr(defn, "spirit_value", 0) or 0)
            item_values[iid] = raw_val if raw_val > 0 else default_unit
        value = estimate_gift_spirit_value(
            spirit_stones=stones,
            items=lines,
            item_values=item_values,
            default_value=default_unit,
        )
        await self._consume_daily_cap(character.id, count=1, spirit_value=value)

        # 先校验库存，再扣灵石与物品，避免半扣
        counts = await self._inv.material_counts(character.id)
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
                reason="gift_send",
                note_zh=f"赠送灵石给{target.name}",
                ref_type="gift",
            )
        for line in lines:
            await self._inv._remove_item_id(
                character.id,
                str(line["item_id"]),
                int(line["quantity"]),
            )

        note = (note_zh or "").strip()
        body = f"「{character.name}」赠予你一份机缘。"
        if note:
            body += f"\n附言：{note}"
        row = await self.send_system(
            to_character_id=target.id,
            subject_zh="道友赠礼",
            body_zh=body,
            reason="gift",
            spirit_stones=stones,
            items=lines,
            from_character_id=character.id,
            mail_kind="gift",
        )

        if bool(gift_cfg.get("receipt_to_sender", True)):
            await self.send_system(
                to_character_id=character.id,
                subject_zh="赠送回执",
                body_zh=f"已向「{target.name}」送出赠礼（估价约 {value}）。",
                reason="gift_receipt",
                mail_kind="system",
            )

        await self._session.flush()
        return {
            "message": f"已赠送给「{target.name}」，对方可在邮箱领取",
            "mail_id": row.id,
            "spirit_value": value,
            "character": await self._character_public(character),
        }

    # ----- helpers -----

    async def _get_owned(self, character_id: int, mail_id: int) -> MailMessage:
        row = await self._session.get(MailMessage, mail_id)
        if row is None or row.to_character_id != character_id:
            raise AppError(code=40000, message="邮件不存在", http_status=404)
        return row

    async def _deliver_attachments(
        self,
        character: Character,
        att: dict[str, Any],
        *,
        ref_id: str,
    ) -> None:
        stones = int(att.get("spirit_stones") or 0)
        if stones > 0:
            await self._ledger.adjust_spirit_stones(
                character,
                delta=stones,
                reason="mail_claim",
                note_zh="邮件附件灵石",
                ref_type="mail",
                ref_id=ref_id,
            )
        inv = get_game_config().inventory
        for line in att.get("items") or []:
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
            ok, reason = item_may_trade(tradable=bool(defn.tradable), bound=bool(defn.bound))
            if not ok:
                raise AppError(
                    code=40111,
                    message=f"「{defn.name}」{reason}",
                    http_status=400,
                )

    async def _consume_daily_cap(
        self,
        character_id: int,
        *,
        count: int,
        spirit_value: int,
    ) -> None:
        gift_cfg = self._cfg().gift
        day_key = now_utc().strftime("%Y-%m-%d")
        row = (
            await self._session.execute(
                select(GiftDailyCounter).where(
                    GiftDailyCounter.character_id == character_id,
                    GiftDailyCounter.day_key == day_key,
                ),
            )
        ).scalar_one_or_none()
        if row is None:
            row = GiftDailyCounter(
                character_id=character_id,
                day_key=day_key,
                gift_count=0,
                spirit_value_sum=0,
            )
            self._session.add(row)
            await self._session.flush()
        cap_c = int(gift_cfg.get("daily_count_cap") or 20)
        cap_v = int(gift_cfg.get("daily_spirit_value_cap") or 50000)
        if int(row.gift_count) + count > cap_c:
            raise AppError(code=40000, message="今日赠送次数已达上限", http_status=400)
        if int(row.spirit_value_sum) + spirit_value > cap_v:
            raise AppError(code=40000, message="今日赠送估价已达上限", http_status=400)
        row.gift_count = int(row.gift_count) + count
        row.spirit_value_sum = int(row.spirit_value_sum) + spirit_value
        await self._session.flush()

    async def _expire_for_character(self, character_id: int) -> None:
        """惰性处理过期未领邮件。"""
        now = now_utc()
        rows = (
            await self._session.execute(
                select(MailMessage).where(
                    MailMessage.to_character_id == character_id,
                    MailMessage.claimed_at.is_(None),
                    MailMessage.expires_at.is_not(None),
                ),
            )
        ).scalars().all()
        policy = str(self._cfg().expire_unclaimed or "return_sender")
        for row in rows:
            if row.expires_at is None:
                continue
            if now < ensure_aware_utc(row.expires_at):
                continue
            att = json.loads(row.attachments_json or "{}")
            if attachments_empty(att):
                row.claimed_at = now
                row.read_at = row.read_at or now
                continue
            if policy == "return_sender" and row.from_character_id is not None:
                # 退回发件人新系统信
                await self.send_system(
                    to_character_id=int(row.from_character_id),
                    subject_zh="邮件附件退回",
                    body_zh=f"原寄给收件人的邮件已过期，附件退回（原标题：{row.subject_zh}）。",
                    reason="mail_expire_return",
                    spirit_stones=int(att.get("spirit_stones") or 0),
                    items=list(att.get("items") or []),
                )
                row.attachments_json = json.dumps(
                    {"spirit_stones": 0, "items": []},
                    ensure_ascii=False,
                )
            elif policy == "destroy":
                # 附件销毁进回收（仅灵石）
                stones = int(att.get("spirit_stones") or 0)
                if stones > 0:
                    await self._ledger.adjust_spirit_stones(
                        None,
                        delta=stones,
                        reason="mail_expire_destroy",
                        note_zh="过期邮件灵石回收",
                        ref_type="mail",
                        ref_id=str(row.id),
                    )
                row.attachments_json = json.dumps(
                    {"spirit_stones": 0, "items": []},
                    ensure_ascii=False,
                )
            row.claimed_at = now
            row.read_at = row.read_at or now
        await self._session.flush()

    async def _resolve_target(
        self,
        to_character_id: int | None,
        to_name: str | None,
    ) -> Character:
        if to_character_id is not None:
            ch = await self._session.get(Character, int(to_character_id))
            if ch is None:
                raise AppError(code=40000, message="目标角色不存在", http_status=404)
            return ch
        name = (to_name or "").strip()
        if not name:
            raise AppError(code=40000, message="请提供目标角色 id 或道号", http_status=400)
        ch = (
            await self._session.execute(select(Character).where(Character.name == name))
        ).scalar_one_or_none()
        if ch is None:
            raise AppError(code=40000, message=f"找不到道号「{name}」", http_status=404)
        return ch

    async def _public(self, row: MailMessage) -> dict[str, Any]:
        att = json.loads(row.attachments_json or "{}")
        # 已领时不展示 snapshot 给玩家重复领
        if row.claimed_at is not None:
            display_att = {"spirit_stones": 0, "items": []}
        else:
            display_att = {
                "spirit_stones": int(att.get("spirit_stones") or 0),
                "items": list(att.get("items") or []),
            }
        from_name = None
        if row.from_character_id:
            sender = await self._session.get(Character, row.from_character_id)
            from_name = sender.name if sender else str(row.from_character_id)
        kind_zh = {
            "system": "系统",
            "player": "道友",
            "gift": "赠礼",
        }.get(row.mail_kind, row.mail_kind)
        return {
            "id": row.id,
            "mail_kind": row.mail_kind,
            "mail_kind_label_zh": kind_zh,
            "reason": row.reason,
            "subject_zh": row.subject_zh,
            "body_zh": row.body_zh,
            "from_character_id": row.from_character_id,
            "from_name": from_name or "天道驿使",
            "attachments": display_att,
            "has_attachments": not attachments_empty(display_att),
            "is_read": row.read_at is not None,
            "is_claimed": row.claimed_at is not None,
            "can_claim": row.claimed_at is None and not attachments_empty(display_att),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        }

    async def _character_public(self, character: Character) -> dict[str, Any]:
        from app.services.character_service import CharacterService

        await self._session.refresh(character)
        return (
            await CharacterService(self._session).enrich_public(character)
        ).model_dump(mode="json")
