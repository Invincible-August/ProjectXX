"""
邮件应用服务（M7 L3）。



领取幂等；玩家发信可附道具/灵石（原赠送并入）；批量已读/领取/删除；
宗门/弟子群发。
"""



from __future__ import annotations



import json
import logging
from datetime import timedelta
from typing import Any, Literal



from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession



from app.core.config import get_settings
from app.core.time_utils import ensure_aware_utc, now_utc
from app.db.models import Character, User
from app.db.models.mail import GiftDailyCounter, MailMessage
from app.db.models.mentor import MentorBond
from app.db.models.sect import SectMember
from app.domain.mail_rules import (
    attachments_empty,
    estimate_gift_spirit_value,
    mail_can_delete,
    normalize_attachments,
    sect_rank_allows_broadcast,
    validate_attachment_item_stacks,
)
from app.domain.sect_org_rules import normalize_member_rank, rank_label_zh
from app.domain.trade_rules import item_may_trade, parse_item_lines
from app.schemas.common import AppError
from app.services.currency_ledger_service import CurrencyLedgerService
from app.services.friend_service import FriendService
from app.services.inventory_service import InventoryService
from app.services.play_gate import PlayGate
from app.services.realm_config import get_game_config



logger = logging.getLogger(__name__)



BroadcastAudience = Literal["sect", "disciples"]





def require_mail_enabled() -> None:
    """邮件总闸。"""
    settings = get_settings()
    if not bool(getattr(settings, "mail_system_enabled", True)):
        raise AppError(code=40000, message="邮件系统未开放", http_status=403)





class MailService:
    """邮件用例（含原赠送投递）。"""



    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._gate = PlayGate(session)
        self._inv = InventoryService(session)
        self._ledger = CurrencyLedgerService(session)



    def _cfg(self):
        return get_game_config().mail



    async def unread_count(self, character_id: int) -> int:
        """未读且未过期清理后的邮件数。"""
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
        items = []
        for row in rows:
            items.append(await self._public(row))
        return {
            "items": items,
            "unread": await self.unread_count(character.id),
            "limits": self._limits_public(),
        }



    async def compose_options(self, user: User) -> dict[str, Any]:
        """
        写信快捷目标：道友 / 同门 / 弟子 + 群发权限。



        Returns:
            dict: 选项与限额。
        """
        require_mail_enabled()
        character = await self._gate.require_character(user)
        friends_payload = await FriendService(self._session).list_friends(user)
        friends = [
            {
                "character_id": int(f["peer_character_id"]),
                "name": str(f["peer_name"]),
            }
            for f in (friends_payload.get("friends") or [])
        ]



        sect_members: list[dict[str, Any]] = []
        can_sect_broadcast = False
        my_rank = None
        my_rank_label = None
        member_row = (
            await self._session.execute(
                select(SectMember).where(SectMember.character_id == character.id),
            )
        ).scalar_one_or_none()
        if member_row is not None:
            sects_cfg = get_game_config().sects
            my_rank = normalize_member_rank(member_row.rank, member_row.role)
            my_rank_label = rank_label_zh(my_rank, sects_cfg.disciple_ranks)
            min_order = int(getattr(self._cfg(), "sect_broadcast_min_rank_order", 9) or 9)
            can_sect_broadcast = sect_rank_allows_broadcast(
                my_rank,
                sects_cfg.disciple_ranks,
                min_order=min_order,
            )
            rows = (
                await self._session.execute(
                    select(SectMember, Character)
                    .join(Character, Character.id == SectMember.character_id)
                    .where(
                        SectMember.sect_id == member_row.sect_id,
                        SectMember.character_id != character.id,
                    )
                    .order_by(SectMember.id.asc()),
                )
            ).all()
            for m, ch in rows:
                r = normalize_member_rank(m.rank, m.role)
                sect_members.append(
                    {
                        "character_id": ch.id,
                        "name": ch.name,
                        "rank": r,
                        "rank_label_zh": rank_label_zh(r, sects_cfg.disciple_ranks),
                    },
                )



        disciples: list[dict[str, Any]] = []
        bonds = (
            await self._session.execute(
                select(MentorBond).where(
                    MentorBond.master_character_id == character.id,
                    MentorBond.status == "active",
                ),
            )
        ).scalars().all()
        for bond in bonds:
            appr = await self._session.get(Character, bond.apprentice_character_id)
            if appr is None:
                continue
            disciples.append(
                {
                    "character_id": appr.id,
                    "name": appr.name,
                    "bond_id": bond.id,
                },
            )



        return {
            "friends": friends,
            "sect_members": sect_members,
            "disciples": disciples,
            "can_sect_broadcast": can_sect_broadcast,
            "can_disciple_broadcast": len(disciples) > 0,
            "my_sect_rank": my_rank,
            "my_sect_rank_label_zh": my_rank_label,
            "limits": self._limits_public(),
        }



    def _limits_public(self) -> dict[str, Any]:
        """前端限额提示。"""
        cfg = self._cfg()
        return {
            "max_attachment_lines": int(cfg.max_attachment_lines),
            "max_attachment_spirit_stones": int(cfg.max_attachment_spirit_stones or 0),
            "max_body_len": int(cfg.max_body_len),
            "broadcast_max_recipients": int(
                getattr(cfg, "broadcast_max_recipients", 100) or 100,
            ),
            "sect_broadcast_min_rank_order": int(
                getattr(cfg, "sect_broadcast_min_rank_order", 9) or 9,
            ),
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



    async def mark_read_all(self, user: User) -> dict[str, Any]:
        """一键已读：全部未读标读（不领附件）。"""
        require_mail_enabled()
        character = await self._gate.require_character(user)
        await self._expire_for_character(character.id)
        rows = (
            await self._session.execute(
                select(MailMessage).where(
                    MailMessage.to_character_id == character.id,
                    MailMessage.read_at.is_(None),
                ),
            )
        ).scalars().all()
        now = now_utc()
        count = 0
        for row in rows:
            row.read_at = now
            count += 1
        await self._session.flush()
        return {
            "message": f"已将 {count} 封标为已读" if count else "没有未读邮件",
            "marked": count,
            "unread": await self.unread_count(character.id),
        }



    async def claim(self, user: User, mail_id: int) -> dict[str, Any]:
        """
        领取附件（幂等：已领 → 40120）。领取后自动已读。



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
        return await self._claim_row(character, row)



    async def claim_all(self, user: User) -> dict[str, Any]:
        """一键领取：所有可领附件；领取后标已读。"""
        require_mail_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        await self._expire_for_character(character.id)
        rows = (
            await self._session.execute(
                select(MailMessage)
                .where(
                    MailMessage.to_character_id == character.id,
                    MailMessage.claimed_at.is_(None),
                )
                .order_by(MailMessage.id.asc()),
            )
        ).scalars().all()
        claimed_count = 0
        last_character = None
        for row in rows:
            att = json.loads(row.attachments_json or "{}")
            display = {
                "spirit_stones": int(att.get("spirit_stones") or 0),
                "items": list(att.get("items") or []),
            }
            if attachments_empty(display):
                # 无附件：顺手标已读，不计入领取
                if row.read_at is None:
                    row.read_at = now_utc()
                continue
            try:
                result = await self._claim_row(character, row)
                if result.get("claimed"):
                    claimed_count += 1
                last_character = result.get("character")
            except AppError as exc:
                if exc.code == 40120:
                    continue
                raise
        await self._session.flush()
        return {
            "message": f"已领取 {claimed_count} 封附件" if claimed_count else "没有可领附件",
            "claimed_count": claimed_count,
            "unread": await self.unread_count(character.id),
            "character": last_character
            or await self._character_public(character),
        }



    async def delete_mail(self, user: User, mail_id: int) -> dict[str, Any]:
        """删除单封：须已读且附件已领（或无附件）。"""
        require_mail_enabled()
        character = await self._gate.require_character(user)
        row = await self._get_owned(character.id, mail_id)
        pub = await self._public(row)
        if not pub["can_delete"]:
            raise AppError(
                code=40000,
                message="仅可删除已读且附件已领取的邮件",
                http_status=400,
            )
        await self._session.delete(row)
        await self._session.flush()
        return {
            "message": "已删除",
            "deleted": 1,
            "unread": await self.unread_count(character.id),
        }



    async def delete_all_eligible(self, user: User) -> dict[str, Any]:
        """一键删除：已读且附件已领的邮件。"""
        require_mail_enabled()
        character = await self._gate.require_character(user)
        await self._expire_for_character(character.id)
        rows = (
            await self._session.execute(
                select(MailMessage).where(MailMessage.to_character_id == character.id),
            )
        ).scalars().all()
        deleted = 0
        for row in rows:
            pub = await self._public(row)
            if not pub["can_delete"]:
                continue
            await self._session.delete(row)
            deleted += 1
        await self._session.flush()
        return {
            "message": f"已删除 {deleted} 封" if deleted else "没有可删邮件",
            "deleted": deleted,
            "unread": await self.unread_count(character.id),
        }



    async def _claim_row(self, character: Character, row: MailMessage) -> dict[str, Any]:
        """对单行执行领取（内部）。"""
        if row.claimed_at is not None:
            raise AppError(code=40120, message="附件已领取或不存在", http_status=400)
        att = json.loads(row.attachments_json or "{}")
        display = {
            "spirit_stones": int(att.get("spirit_stones") or 0),
            "items": list(att.get("items") or []),
        }
        if attachments_empty(display):
            row.claimed_at = now_utc()
            row.read_at = row.read_at or row.claimed_at
            await self._session.flush()
            return {
                "message": "无附件可领",
                "mail": await self._public(row),
                "character": await self._character_public(character),
            }
        await self._deliver_attachments(character, display, ref_id=str(row.id))
        row.claimed_at = now_utc()
        row.read_at = row.read_at or row.claimed_at
        row.attachments_json = json.dumps(
            {"spirit_stones": 0, "items": [], "claimed_snapshot": display},
            ensure_ascii=False,
        )
        await self._session.flush()
        logger.info("mail claim character_id=%s mail_id=%s", character.id, row.id)
        return {
            "message": "附件已入包",
            "claimed": display,
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
        发送系统信（含退回/附物投递）。内部 API，无用户闸。



        Args:
            to_character_id: 收件人。
            subject_zh: 标题（中文）。
            body_zh: 正文。
            reason: 机读原因。
            spirit_stones: 附件灵石。
            items: 附件物品（须已从发送方扣出或新建）。
            from_character_id: 可选发件人。
            mail_kind: system / gift / player。



        Returns:
            MailMessage: 新建行。
        """
        att = normalize_attachments(spirit_stones=spirit_stones, items=items)
        cfg = self._cfg()
        if len(att["items"]) > int(cfg.max_attachment_lines):
            raise AppError(code=40000, message="附件物品种类超限", http_status=400)
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
        to_character_id: int | None = None,
        to_name: str | None = None,
        subject_zh: str,
        body_zh: str,
        spirit_stones: int = 0,
        items: list[dict[str, Any]] | None = None,
        broadcast: BroadcastAudience | None = None,
    ) -> dict[str, Any]:
        """
        玩家发信：可附灵石/道具；可宗门/弟子群发。



        Args:
            user: 发送方。
            to_character_id: 单发目标 id。
            to_name: 单发道号。
            subject_zh: 标题（空则「（无题）」）。
            body_zh: 正文。
            spirit_stones: 附件灵石。
            items: 附件物品。
            broadcast: ``sect`` / ``disciples`` 群发；与单发互斥优先。



        Returns:
            dict: 结果。
        """
        require_mail_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        if character.status in ("awaiting_ferry", "tribulation", "reincarnating"):
            raise AppError(code=40000, message="当前状态不可发信", http_status=400)



        subject = (subject_zh or "").strip() or "（无题）"
        body = (body_zh or "").strip()
        if len(body) > int(self._cfg().max_body_len):
            raise AppError(code=40000, message="正文过长", http_status=400)



        lines = parse_item_lines(items or [])
        stones = max(0, int(spirit_stones or 0))
        has_attach = stones > 0 or bool(lines)



        # 堆叠与种类上限
        if lines:
            ok, err, clamped = validate_attachment_item_stacks(
                lines,
                get_game_config().inventory,
            )
            if not ok:
                raise AppError(code=40000, message=err or "附件非法", http_status=400)
            lines = clamped
            if len(lines) > int(self._cfg().max_attachment_lines):
                raise AppError(
                    code=40000,
                    message=f"附件最多 {self._cfg().max_attachment_lines} 种道具",
                    http_status=400,
                )
        max_stone = int(self._cfg().max_attachment_spirit_stones or 0)
        if max_stone > 0 and stones > max_stone:
            raise AppError(code=40000, message="附件灵石超限", http_status=400)



        if broadcast:
            targets = await self._resolve_broadcast_targets(character, broadcast)
        else:
            target = await self._resolve_target(to_character_id, to_name)
            if target.id == character.id:
                raise AppError(code=40000, message="不可给自己写信", http_status=400)
            targets = [target]



        # 附物时：单发可要求道友；群发跳过道友校验
        gift_cfg = self._cfg().gift
        if has_attach and not broadcast and bool(gift_cfg.get("require_friend", True)):
            ok = await FriendService(self._session).are_friends(
                character.id,
                targets[0].id,
            )
            if not ok:
                raise AppError(
                    code=40110,
                    message="附带道具/灵石仅可发给道友（群发除外）",
                    http_status=400,
                )



        if has_attach:
            await self._assert_tradable(lines)
            # 群发：每种附件按人数倍扣
            n = len(targets)
            total_lines = [
                {"item_id": str(line["item_id"]), "quantity": int(line["quantity"]) * n}
                for line in lines
            ]
            total_stones = stones * n
            inv = get_game_config().inventory
            default_unit = int(gift_cfg.get("default_item_spirit_value") or 10)
            item_values: dict[str, int] = {}
            for iid, defn in inv.items.items():
                raw_val = int(getattr(defn, "spirit_value", 0) or 0)
                item_values[iid] = raw_val if raw_val > 0 else default_unit
            # 日限：按收件人数计次与估价
            per_value = estimate_gift_spirit_value(
                spirit_stones=stones,
                items=lines,
                item_values=item_values,
                default_value=default_unit,
            )
            await self._consume_daily_cap(
                character.id,
                count=n,
                spirit_value=per_value * n,
            )
            counts = await self._inv.material_counts(character.id)
            for line in total_lines:
                item_id = str(line["item_id"])
                need = int(line["quantity"])
                if int(counts.get(item_id, 0)) < need:
                    defn = inv.items.get(item_id)
                    raise AppError(
                        code=40055,
                        message=f"物品不足：{(defn.name if defn else item_id)}",
                        http_status=400,
                    )
            if total_stones > 0:
                await self._ledger.adjust_spirit_stones(
                    character,
                    delta=-total_stones,
                    reason="mail_send_attach",
                    note_zh="邮件附件灵石",
                    ref_type="mail",
                )
            for line in total_lines:
                await self._inv._remove_item_id(
                    character.id,
                    str(line["item_id"]),
                    int(line["quantity"]),
                )



        mail_ids: list[int] = []
        for target in targets:
            if has_attach:
                body_final = body
                if not body_final:
                    body_final = f"「{character.name}」寄来一份机缘。"
                row = await self.send_system(
                    to_character_id=target.id,
                    subject_zh=subject,
                    body_zh=body_final,
                    reason="gift" if not broadcast else f"mail_broadcast_{broadcast}",
                    spirit_stones=stones,
                    items=lines,
                    from_character_id=character.id,
                    mail_kind="gift" if has_attach else "player",
                )
            else:
                row = await self.send_system(
                    to_character_id=target.id,
                    subject_zh=subject,
                    body_zh=body,
                    reason=(
                        "player_mail"
                        if not broadcast
                        else f"mail_broadcast_{broadcast}"
                    ),
                    from_character_id=character.id,
                    mail_kind="player",
                )
            mail_ids.append(int(row.id))



        if has_attach and bool(gift_cfg.get("receipt_to_sender", True)) and not broadcast:
            await self.send_system(
                to_character_id=character.id,
                subject_zh="发信回执",
                body_zh=f"已向「{targets[0].name}」送出附物邮件。",
                reason="gift_receipt",
                mail_kind="system",
            )



        await self._session.flush()
        if broadcast:
            label = "宗门门众" if broadcast == "sect" else "弟子"
            msg = f"已群发给 {len(targets)} 位{label}"
        else:
            msg = f"已送信给「{targets[0].name}」"
            if has_attach:
                msg += "，对方可在邮箱领取"
        result: dict[str, Any] = {
            "message": msg,
            "mail_id": mail_ids[0] if len(mail_ids) == 1 else None,
            "mail_ids": mail_ids,
            "recipient_count": len(targets),
        }
        if has_attach:
            result["character"] = await self._character_public(character)
        return result



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
        兼容旧 ``POST /gifts``：转发到统一发信（附物）。



        Args:
            user: 发送方。
            to_character_id: 目标 id。
            to_name: 目标道号。
            spirit_stones: 灵石。
            items: 物品。
            note_zh: 附言作正文。



        Returns:
            dict: 结果。
        """
        return await self.send_player_mail(
            user,
            to_character_id=to_character_id,
            to_name=to_name,
            subject_zh="道友赠礼",
            body_zh=(note_zh or "").strip(),
            spirit_stones=spirit_stones,
            items=items,
            broadcast=None,
        )



    async def _resolve_broadcast_targets(
        self,
        character: Character,
        audience: BroadcastAudience,
    ) -> list[Character]:
        """解析群发收件人。"""
        max_n = int(getattr(self._cfg(), "broadcast_max_recipients", 100) or 100)
        if audience == "sect":
            member_row = (
                await self._session.execute(
                    select(SectMember).where(SectMember.character_id == character.id),
                )
            ).scalar_one_or_none()
            if member_row is None:
                raise AppError(code=40000, message="你尚未加入宗门", http_status=400)
            sects_cfg = get_game_config().sects
            my_rank = normalize_member_rank(member_row.rank, member_row.role)
            min_order = int(getattr(self._cfg(), "sect_broadcast_min_rank_order", 9) or 9)
            if not sect_rank_allows_broadcast(
                my_rank,
                sects_cfg.disciple_ranks,
                min_order=min_order,
            ):
                raise AppError(
                    code=40000,
                    message="宗门群发仅限掌门及以上职位",
                    http_status=403,
                )
            rows = (
                await self._session.execute(
                    select(Character)
                    .join(SectMember, SectMember.character_id == Character.id)
                    .where(
                        SectMember.sect_id == member_row.sect_id,
                        Character.id != character.id,
                    ),
                )
            ).scalars().all()
            targets = list(rows)
        elif audience == "disciples":
            bonds = (
                await self._session.execute(
                    select(MentorBond).where(
                        MentorBond.master_character_id == character.id,
                        MentorBond.status == "active",
                    ),
                )
            ).scalars().all()
            targets = []
            for bond in bonds:
                appr = await self._session.get(Character, bond.apprentice_character_id)
                if appr is not None:
                    targets.append(appr)
            if not targets:
                raise AppError(code=40000, message="当前没有可群发的弟子", http_status=400)
        else:
            raise AppError(code=40000, message="未知群发类型", http_status=400)



        if not targets:
            raise AppError(code=40000, message="没有可发送的收件人", http_status=400)
        if len(targets) > max_n:
            raise AppError(
                code=40000,
                message=f"群发人数超限（最多 {max_n}）",
                http_status=400,
            )
        return targets



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
            raise AppError(code=40000, message="今日附物发信次数已达上限", http_status=400)
        if int(row.spirit_value_sum) + spirit_value > cap_v:
            raise AppError(code=40000, message="今日附物发信估价已达上限", http_status=400)
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
            "gift": "附物",
        }.get(row.mail_kind, row.mail_kind)
        is_read = row.read_at is not None
        is_claimed = row.claimed_at is not None
        has_att = not attachments_empty(display_att)
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
            "has_attachments": has_att,
            "is_read": is_read,
            "is_claimed": is_claimed,
            "can_claim": row.claimed_at is None and has_att,
            "can_delete": mail_can_delete(
                is_read=is_read,
                is_claimed=is_claimed,
                has_attachments=has_att,
            ),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        }



    async def _character_public(self, character: Character) -> dict[str, Any]:
        from app.services.character_service import CharacterService



        await self._session.refresh(character)
        return (
            await CharacterService(self._session).enrich_public(character)
        ).model_dump(mode="json")
