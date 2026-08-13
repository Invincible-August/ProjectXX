"""
师徒应用服务（M7 L6）：拜师 / 任务 / 传功 / 出师 / 解除。
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time_utils import ensure_aware_utc, now_utc
from app.db.models import Character, User
from app.db.models.mentor import (
    CharacterCraftKnowledge,
    MentorBond,
    MentorPassDaily,
    MentorQuestProgress,
    MentorTransmission,
)
from app.db.models.technique import CharacterTechnique
from app.domain.channel_membership import build_mentor_ref
from app.domain.mentor_rules import (
    direct_can_appoint,
    direct_can_clear,
    disciple_ordinal_title,
    lesson_kind_daily_cap,
    lesson_transfer_amount,
    master_realm_ok,
    should_auto_graduate,
    teach_sessions_required,
)
from app.schemas.common import AppError
from app.services.currency_ledger_service import CurrencyLedgerService
from app.services.play_gate import PlayGate
from app.services.realm_config import get_game_config, get_major_realm

logger = logging.getLogger(__name__)


def require_mentor_enabled() -> None:
    """师徒总闸。"""
    settings = get_settings()
    if not bool(getattr(settings, "mentor_system_enabled", True)):
        raise AppError(code=40000, message="师徒系统未开放", http_status=403)


class MentorService:
    """师徒用例。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._gate = PlayGate(session)
        self._ledger = CurrencyLedgerService(session)

    def _cfg(self):
        return get_game_config().mentor

    def _realm_order(self) -> list[str]:
        return list(get_game_config().realms.keys())

    async def get_active_bond_for(self, character_id: int) -> MentorBond | None:
        """角色当前活跃师徒键（为师或为徒）。"""
        return (
            await self._session.execute(
                select(MentorBond).where(
                    MentorBond.status == "active",
                    or_(
                        MentorBond.master_character_id == character_id,
                        MentorBond.apprentice_character_id == character_id,
                    ),
                ).limit(1),
            )
        ).scalar_one_or_none()

    async def me(self, user: User) -> dict[str, Any]:
        """名录、申请、任务、日课/传授状态（并惰性自动出师）。"""
        require_mentor_enabled()
        character = await self._gate.require_character(user)
        await self._expire_stale()
        active = await self.get_active_bond_for(character.id)
        auto_msg = None
        if active is not None:
            auto = await self._maybe_auto_graduate(active)
            if auto is not None:
                auto_msg = auto.get("message")
                active = None
        pending_in = (
            await self._session.execute(
                select(MentorBond).where(
                    MentorBond.status == "pending",
                    or_(
                        MentorBond.master_character_id == character.id,
                        MentorBond.apprentice_character_id == character.id,
                    ),
                    MentorBond.requester_character_id != character.id,
                ),
            )
        ).scalars().all()
        pending_out = (
            await self._session.execute(
                select(MentorBond).where(
                    MentorBond.status == "pending",
                    MentorBond.requester_character_id == character.id,
                ),
            )
        ).scalars().all()
        bond_public = await self._bond_public(active, viewer_id=character.id) if active else None
        quests = await self._quests_public(active) if active else []
        daily = await self._daily_public(active) if active else None
        options = await self._teaching_options(active) if active else None
        transmissions = await self._transmissions_public(active) if active else []
        lineage = await self._lineage_public(character.id)
        return {
            "bond": bond_public,
            "incoming": [await self._bond_public(b, viewer_id=character.id) for b in pending_in],
            "outgoing": [await self._bond_public(b, viewer_id=character.id) for b in pending_out],
            "quests": quests,
            "daily": daily,
            "options": options,
            "transmissions": transmissions,
            "lineage": lineage,
            "channel_ref": bond_public["channel_ref"] if bond_public else None,
            "auto_graduate_message": auto_msg,
            "config": {
                "max_apprentices": int(self._cfg().max_apprentices),
                "min_realm_gap": int(self._cfg().min_realm_gap),
                "auto_graduate_max_gap": int(self._cfg().auto_graduate_max_gap),
                "daily_lesson": dict(self._cfg().daily_lesson or {}),
                "direct_disciple": dict(self._cfg().direct_disciple or {}),
                "teach": {
                    "daily_cap": int((self._cfg().teach or {}).get("daily_cap") or 1),
                    "sessions_by_tier": dict(
                        (self._cfg().teach or {}).get("sessions_by_tier") or {},
                    ),
                },
            },
        }

    async def apply(
        self,
        user: User,
        *,
        target_character_id: int | None,
        target_name: str | None,
        intent: str,
    ) -> dict[str, Any]:
        """
        发起拜师或收徒。

        Args:
            user: 申请人。
            target_character_id: 目标 id。
            target_name: 目标道号。
            intent: ``apprentice``=我拜对方为师；``master``=我收对方为徒。

        Returns:
            dict: 申请结果。
        """
        require_mentor_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        intent_l = str(intent or "").strip().lower()
        if intent_l not in {"apprentice", "master"}:
            raise AppError(code=40150, message="申请意图非法", http_status=400)
        target = await self._resolve_character(target_character_id, target_name)
        if target.id == character.id:
            raise AppError(code=40150, message="不可与自己结成师徒", http_status=400)
        await self._expire_stale()

        if intent_l == "apprentice":
            master, apprentice = target, character
        else:
            master, apprentice = character, target

        ok, reason = master_realm_ok(
            master_major=str(master.major_realm),
            apprentice_major=str(apprentice.major_realm),
            realm_order=self._realm_order(),
            min_gap=int(self._cfg().min_realm_gap),
        )
        if not ok:
            raise AppError(code=40150, message=reason or "境界不足", http_status=400)

        # 徒弟名额
        appr_active = (
            await self._session.execute(
                select(MentorBond).where(
                    MentorBond.apprentice_character_id == apprentice.id,
                    MentorBond.status.in_(("active", "pending")),
                ),
            )
        ).scalars().all()
        if len(list(appr_active)) >= int(self._cfg().max_masters_per_apprentice):
            raise AppError(code=40150, message="徒弟已有师傅或待确认申请", http_status=400)

        master_apprentices = (
            await self._session.execute(
                select(MentorBond).where(
                    MentorBond.master_character_id == master.id,
                    MentorBond.status.in_(("active", "pending")),
                ),
            )
        ).scalars().all()
        if len(list(master_apprentices)) >= int(self._cfg().max_apprentices):
            raise AppError(code=40150, message="师傅收徒名额已满", http_status=400)

        # 冷却：任一方最近 dissolve
        await self._assert_dissolve_cooldown(character.id)
        await self._assert_dissolve_cooldown(target.id)

        row = MentorBond(
            master_character_id=master.id,
            apprentice_character_id=apprentice.id,
            status="pending",
            requester_character_id=character.id,
            intent=intent_l,
        )
        self._session.add(row)
        await self._session.flush()
        logger.info(
            "mentor apply id=%s master=%s apprentice=%s intent=%s",
            row.id,
            master.id,
            apprentice.id,
            intent_l,
        )
        return {
            "message": "师徒申请已发送",
            "bond_id": row.id,
            "bond": await self._bond_public(row, viewer_id=character.id),
        }

    async def accept(self, user: User, bond_id: int) -> dict[str, Any]:
        """确认申请（非申请人一方）。"""
        require_mentor_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        row = await self._session.get(MentorBond, bond_id)
        if row is None or row.status != "pending":
            raise AppError(code=40150, message="申请不存在或已失效", http_status=404)
        if character.id not in (row.master_character_id, row.apprentice_character_id):
            raise AppError(code=40150, message="无权处理该申请", http_status=403)
        if row.requester_character_id == character.id:
            raise AppError(code=40150, message="不可确认自己发出的申请", http_status=400)
        # 再次校验名额与境界
        master = await self._session.get(Character, row.master_character_id)
        apprentice = await self._session.get(Character, row.apprentice_character_id)
        if master is None or apprentice is None:
            raise AppError(code=40150, message="角色不存在", http_status=404)
        ok, reason = master_realm_ok(
            master_major=str(master.major_realm),
            apprentice_major=str(apprentice.major_realm),
            realm_order=self._realm_order(),
            min_gap=int(self._cfg().min_realm_gap),
        )
        if not ok:
            raise AppError(code=40150, message=reason or "境界不足", http_status=400)
        row.status = "active"
        row.accepted_at = now_utc()
        await self._session.flush()
        # 初始化任务进度行
        for qid in (self._cfg().quests or {}):
            self._session.add(
                MentorQuestProgress(bond_id=row.id, quest_id=str(qid), progress=0),
            )
        await self._session.flush()
        return {
            "message": "已结成师徒",
            "bond": await self._bond_public(row, viewer_id=character.id),
        }

    async def reject(self, user: User, bond_id: int) -> dict[str, Any]:
        """拒绝申请。"""
        require_mentor_enabled()
        character = await self._gate.require_character(user)
        row = await self._session.get(MentorBond, bond_id)
        if row is None or row.status != "pending":
            raise AppError(code=40150, message="申请不存在或已失效", http_status=404)
        if character.id not in (row.master_character_id, row.apprentice_character_id):
            raise AppError(code=40150, message="无权处理该申请", http_status=403)
        if row.requester_character_id == character.id:
            raise AppError(code=40150, message="请改用取消申请", http_status=400)
        row.status = "rejected"
        row.closed_at = now_utc()
        await self._session.flush()
        return {"message": "已拒绝申请", "bond_id": row.id}

    async def progress_quest(
        self,
        user: User,
        quest_id: str,
        *,
        amount: int = 1,
    ) -> dict[str, Any]:
        """推进师徒任务（徒弟或师傅均可计次）。"""
        require_mentor_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        bond = await self.get_active_bond_for(character.id)
        if bond is None:
            raise AppError(code=40150, message="无活跃师徒关系", http_status=400)
        qdef = (self._cfg().quests or {}).get(quest_id)
        if not isinstance(qdef, dict):
            raise AppError(code=40000, message="未知任务", http_status=404)
        row = (
            await self._session.execute(
                select(MentorQuestProgress).where(
                    MentorQuestProgress.bond_id == bond.id,
                    MentorQuestProgress.quest_id == quest_id,
                ),
            )
        ).scalar_one_or_none()
        if row is None:
            row = MentorQuestProgress(bond_id=bond.id, quest_id=quest_id, progress=0)
            self._session.add(row)
            await self._session.flush()
        if row.completed_at is not None:
            return {
                "message": "任务已完成",
                "quests": await self._quests_public(bond),
            }
        target = int(qdef.get("target_count") or 1)
        row.progress = min(target, int(row.progress) + max(1, int(amount)))
        if row.progress >= target:
            row.completed_at = now_utc()
            # 任务奖励
            apprentice = await self._session.get(Character, bond.apprentice_character_id)
            master = await self._session.get(Character, bond.master_character_id)
            gain = int(qdef.get("reward_apprentice_spirit_pool") or 0)
            if apprentice is not None and gain > 0:
                apprentice.cultivation_points = int(apprentice.cultivation_points or 0) + gain
            stone = int(qdef.get("reward_master_spirit_stones") or 0)
            if master is not None and stone > 0:
                await self._ledger.adjust_spirit_stones(
                    master,
                    delta=stone,
                    reason="mentor_quest_reward",
                    note_zh=f"师徒任务奖励·{qdef.get('name') or quest_id}",
                    ref_type="mentor",
                    ref_id=str(bond.id),
                )
        await self._session.flush()
        return {
            "message": "任务进度已更新" if row.completed_at is None else "任务完成",
            "quests": await self._quests_public(bond),
        }

    async def pass_cultivation(self, user: User) -> dict[str, Any]:
        """兼容旧接口：等价于传道·修为。"""
        return await self.teach_lesson(user, kind="dao", resource="spirit")

    async def teach_lesson(
        self,
        user: User,
        *,
        kind: str,
        resource: str | None = None,
        target_id: str | None = None,
    ) -> dict[str, Any]:
        """
        日课三选一：传道 / 授业 / 解惑。

        Args:
            user: 师傅。
            kind: ``dao`` | ``craft`` | ``technique``.
            resource: 传道时 ``spirit`` | ``body``.
            target_id: 授业/解惑目标功法 id。

        Returns:
            dict: 结果与角色摘要。
        """
        require_mentor_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        bond = await self.get_active_bond_for(character.id)
        if bond is None:
            raise AppError(code=40150, message="无活跃师徒关系", http_status=400)
        auto = await self._maybe_auto_graduate(bond)
        if auto is not None:
            return auto
        if character.id != bond.master_character_id:
            raise AppError(code=40150, message="仅师傅可授业日课", http_status=403)

        kind_l = str(kind or "").strip().lower()
        if kind_l not in {"dao", "craft", "technique"}:
            raise AppError(code=40000, message="日课须为传道/授业/解惑", http_status=400)

        daily = await self._get_or_create_daily(bond.id)
        self._sync_legacy_lesson_counts(daily)
        is_direct = bool(bond.is_direct)
        direct_cfg = dict(self._cfg().direct_disciple or {})
        kind_cap = lesson_kind_daily_cap(
            kind=kind_l,
            is_direct=is_direct,
            direct_cfg=direct_cfg,
        )
        kind_used = self._lesson_kind_count(daily, kind_l)
        if kind_used >= kind_cap:
            raise AppError(
                code=40000,
                message=f"今日「{_lesson_label(kind_l)}」次数已用完",
                http_status=400,
            )
        # 非亲传仍为三选一：任一日课做过即不可再做其他类型
        if not is_direct:
            total_used = (
                int(daily.lesson_dao_count or 0)
                + int(daily.lesson_craft_count or 0)
                + int(daily.lesson_technique_count or 0)
            )
            if total_used > 0:
                raise AppError(
                    code=40000,
                    message=(
                        f"今日已完成日课（{_lesson_label(daily.lesson_kind)}），明日再来"
                    ),
                    http_status=400,
                )

        master = character
        apprentice = await self._session.get(Character, bond.apprentice_character_id)
        if apprentice is None:
            raise AppError(code=40150, message="徒弟不存在", http_status=404)

        lesson_cfg = dict(self._cfg().daily_lesson or {})
        need_ratio = float(lesson_cfg.get("apprentice_need_ratio") or 1.0)
        pool_ratio = float(lesson_cfg.get("master_pool_ratio") or 0.1)

        if kind_l == "dao":
            result = await self._lesson_dao(
                master=master,
                apprentice=apprentice,
                resource=resource or "spirit",
                need_ratio=need_ratio,
                pool_ratio=pool_ratio,
            )
        elif kind_l == "craft":
            result = await self._lesson_craft(
                master=master,
                apprentice=apprentice,
                technique_id=target_id,
                need_ratio=need_ratio,
                pool_ratio=pool_ratio,
            )
        else:
            result = await self._lesson_technique(
                master=master,
                apprentice=apprentice,
                technique_id=target_id,
                need_ratio=need_ratio,
                pool_ratio=pool_ratio,
            )

        daily.lesson_kind = kind_l
        self._bump_lesson_kind_count(daily, kind_l)
        daily.pass_count = int(daily.pass_count or 0) + 1
        await self._session.flush()
        if "first_lesson" in (self._cfg().quests or {}):
            await self.progress_quest(user, "first_lesson", amount=1)
        return {
            **result,
            "lesson_kind": kind_l,
            "lesson_kind_label_zh": _lesson_label(kind_l),
            "is_direct": is_direct,
            "quests": await self._quests_public(bond),
            "daily": await self._daily_public(bond),
            "character": await self._character_public(master),
            "apprentice_character": await self._character_public(apprentice),
        }

    async def set_direct_disciples(
        self,
        user: User,
        *,
        apprentice_character_ids: list[int],
    ) -> dict[str, Any]:
        """
        师傅指定/解除亲传弟子（最多配置名额；同人一日冷却）。

        指定后隔日方可解除；解除当日不可再指定同一人。出师会自动解除亲传。

        Args:
            user: 师傅。
            apprentice_character_ids: 目标亲传弟子角色 id 列表（全量覆盖）。

        Returns:
            dict: 更新后的师承单。
        """
        require_mentor_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        ids = [int(x) for x in (apprentice_character_ids or []) if int(x) > 0]
        seen: set[int] = set()
        unique_ids: list[int] = []
        for cid in ids:
            if cid in seen:
                continue
            seen.add(cid)
            unique_ids.append(cid)
        direct_cfg = dict(self._cfg().direct_disciple or {})
        cap = int(direct_cfg.get("max_count") or 3)
        cooldown_days = int(direct_cfg.get("cooldown_days") or 1)
        if len(unique_ids) > cap:
            raise AppError(
                code=40000,
                message=f"亲传弟子最多 {cap} 人",
                http_status=400,
            )
        roster = (
            await self._session.execute(
                select(MentorBond).where(
                    MentorBond.master_character_id == character.id,
                    MentorBond.status.in_(("active", "graduated")),
                ),
            )
        ).scalars().all()
        roster_by_appr = {int(b.apprentice_character_id): b for b in roster}
        for cid in unique_ids:
            if cid not in roster_by_appr:
                raise AppError(
                    code=40000,
                    message="只能指定本门弟子（含已出师）为亲传",
                    http_status=400,
                )
        today = now_utc().strftime("%Y-%m-%d")
        appointed: list[str] = []
        cleared: list[str] = []
        for bond in roster:
            want = int(bond.apprentice_character_id) in seen
            was = bool(bond.is_direct)
            if want == was:
                continue
            ch = await self._session.get(Character, bond.apprentice_character_id)
            label = ch.name if ch else str(bond.apprentice_character_id)
            if was and not want:
                # 解除
                if not direct_can_clear(
                    set_day_key=bond.direct_set_day_key,
                    today_key=today,
                    cooldown_days=cooldown_days,
                ):
                    raise AppError(
                        code=40000,
                        message=f"「{label}」指定亲传后需隔日方可解除",
                        http_status=400,
                    )
                bond.is_direct = False
                bond.direct_set_day_key = None
                bond.direct_cleared_day_key = today
                cleared.append(label)
            else:
                # 指定
                if not direct_can_appoint(
                    cleared_day_key=bond.direct_cleared_day_key,
                    today_key=today,
                ):
                    raise AppError(
                        code=40000,
                        message=f"「{label}」今日刚解除亲传，不可再指定",
                        http_status=400,
                    )
                bond.is_direct = True
                bond.direct_set_day_key = today
                bond.direct_cleared_day_key = None
                appointed.append(label)
        await self._session.flush()
        log_lines: list[str] = [f"已更新亲传弟子（{len(unique_ids)}/{cap}）"]
        for name in appointed:
            log_lines.append(f"「{name}」被设为亲传弟子")
        for name in cleared:
            log_lines.append(f"已解除「{name}」的亲传")
        return {
            "message": "；".join(log_lines),
            "log_lines": log_lines,
            "appointed": appointed,
            "cleared": cleared,
            "lineage": await self._lineage_public(character.id),
        }

    async def teach_item(
        self,
        user: User,
        *,
        item_kind: str,
        item_id: str,
    ) -> dict[str, Any]:
        """
        传授功法 / 配方图纸（每日一次，多日累计）。

        Args:
            user: 师傅。
            item_kind: ``technique`` | ``recipe``.
            item_id: 功法或配方 id。

        Returns:
            dict: 进度或完成结果。
        """
        require_mentor_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        bond = await self.get_active_bond_for(character.id)
        if bond is None:
            raise AppError(code=40150, message="无活跃师徒关系", http_status=400)
        auto = await self._maybe_auto_graduate(bond)
        if auto is not None:
            return auto
        if character.id != bond.master_character_id:
            raise AppError(code=40150, message="仅师傅可传授", http_status=403)

        kind_l = str(item_kind or "").strip().lower()
        tid = str(item_id or "").strip()
        if kind_l not in {"technique", "recipe"} or not tid:
            raise AppError(code=40000, message="请选择功法或配方图纸", http_status=400)

        teach_cfg = dict(self._cfg().teach or {})
        daily = await self._get_or_create_daily(bond.id)
        cap = int(teach_cfg.get("daily_cap") or 1)
        if int(daily.teach_count or 0) >= cap:
            raise AppError(code=40000, message="今日传授次数已用完", http_status=400)

        day_key = daily.day_key
        row = (
            await self._session.execute(
                select(MentorTransmission).where(
                    MentorTransmission.bond_id == bond.id,
                    MentorTransmission.item_kind == kind_l,
                    MentorTransmission.item_id == tid,
                ),
            )
        ).scalar_one_or_none()
        if row is not None and row.status == "completed":
            raise AppError(code=40000, message="该项已传授完成", http_status=400)
        if row is not None and row.last_day_key == day_key:
            raise AppError(code=40000, message="今日已对本项传授过，请明日继续", http_status=400)

        meta, label = self._resolve_teach_meta(kind_l, tid, master=character)
        if kind_l == "technique":
            master_tech = (
                await self._session.execute(
                    select(CharacterTechnique).where(
                        CharacterTechnique.character_id == character.id,
                        CharacterTechnique.technique_id == tid,
                    ),
                )
            ).scalar_one_or_none()
            if master_tech is None or int(master_tech.level or 0) < 1:
                raise AppError(
                    code=40000,
                    message="须先自行掌握该功法后方可传授",
                    http_status=400,
                )
        required = teach_sessions_required(
            item_kind=kind_l,
            item_meta=meta,
            teach_cfg=teach_cfg,
        )
        if row is None:
            row = MentorTransmission(
                bond_id=bond.id,
                item_kind=kind_l,
                item_id=tid,
                required_sessions=required,
                progress=0,
                status="active",
            )
            self._session.add(row)
            await self._session.flush()
        else:
            row.required_sessions = max(int(row.required_sessions), required)

        row.progress = int(row.progress) + 1
        row.last_day_key = day_key
        daily.teach_count = int(daily.teach_count or 0) + 1
        completed = False
        if row.progress >= int(row.required_sessions):
            row.status = "completed"
            row.completed_at = now_utc()
            completed = True
            apprentice = await self._session.get(Character, bond.apprentice_character_id)
            if apprentice is None:
                raise AppError(code=40150, message="徒弟不存在", http_status=404)
            await self._apply_teach_complete(
                master=character,
                apprentice=apprentice,
                item_kind=kind_l,
                item_id=tid,
                teach_cfg=teach_cfg,
            )
        await self._session.flush()
        msg = (
            f"「{label}」传授完成"
            if completed
            else f"「{label}」传授进度 {row.progress}/{row.required_sessions}"
        )
        await self._notify_apprentice_log(
            apprentice_id=int(bond.apprentice_character_id),
            master_name=str(character.name or character.id),
            message=msg,
            level="success",
        )
        return {
            "message": msg,
            "completed": completed,
            "transmission": {
                "item_kind": kind_l,
                "item_id": tid,
                "name": label,
                "progress": int(row.progress),
                "required_sessions": int(row.required_sessions),
                "status": row.status,
            },
            "daily": await self._daily_public(bond),
            "transmissions": await self._transmissions_public(bond),
            "character": await self._character_public(character),
        }

    async def _notify_apprentice_log(
        self,
        *,
        apprentice_id: int,
        master_name: str,
        message: str,
        level: str = "success",
    ) -> None:
        """
        向徒弟同步传授记录：在线 WS 直推事件日志；离线写入待领取缓冲。

        Args:
            apprentice_id: 徒弟角色 id。
            master_name: 师傅道号。
            message: 传授摘要（进度/完成）。
            level: 日志级别。
        """
        from app.core.config import get_settings
        from app.domain.event_logs import append_pending_event_log
        from app.domain.ws_protocol import TYPE_GAME_LOG
        from app.services.presence_service import get_presence
        from app.services.ws_hub_service import get_ws_hub

        text = str(message or "").strip()
        if not text:
            return
        full = f"师傅「{master_name}」传授：{text}"
        payload = {
            "message": full,
            "level": level,
            "source": "mentor.teach",
        }
        online = get_presence().is_online(int(apprentice_id))
        if online and bool(getattr(get_settings(), "ws_enabled", True)):
            try:
                await get_ws_hub().send_to_character(
                    int(apprentice_id),
                    TYPE_GAME_LOG,
                    payload,
                )
                return
            except Exception:  # noqa: BLE001
                logger.debug(
                    "mentor teach ws push failed apprentice=%s",
                    apprentice_id,
                    exc_info=True,
                )
        apprentice = await self._session.get(Character, int(apprentice_id))
        if apprentice is None:
            return
        append_pending_event_log(
            apprentice,
            message=full,
            level=level,
            source="mentor.teach",
        )
        await self._session.flush()

    async def study_technique(
        self,
        user: User,
        *,
        technique_id: str,
    ) -> dict[str, Any]:
        """
        徒弟请学：指定师傅已掌握的功法，每日一次，可叠加未学完的同种传授进度。

        Args:
            user: 徒弟。
            technique_id: 功法 id。

        Returns:
            dict: 进度或完成结果。
        """
        require_mentor_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        bond = await self.get_active_bond_for(character.id)
        if bond is None:
            raise AppError(code=40150, message="无活跃师徒关系", http_status=400)
        auto = await self._maybe_auto_graduate(bond)
        if auto is not None:
            return auto
        if character.id != bond.apprentice_character_id:
            raise AppError(code=40150, message="仅徒弟可请学功法", http_status=403)

        tid = str(technique_id or "").strip()
        if not tid:
            raise AppError(code=40000, message="请选择师傅功法", http_status=400)

        study_cfg = dict(self._cfg().study or {})
        teach_cfg = dict(self._cfg().teach or {})
        daily = await self._get_or_create_daily(bond.id)
        cap = int(study_cfg.get("daily_cap") or 1)
        if int(daily.study_count or 0) >= cap:
            raise AppError(code=40000, message="今日请学次数已用完", http_status=400)

        master = await self._session.get(Character, bond.master_character_id)
        if master is None:
            raise AppError(code=40150, message="师傅不存在", http_status=404)
        master_tech = (
            await self._session.execute(
                select(CharacterTechnique).where(
                    CharacterTechnique.character_id == master.id,
                    CharacterTechnique.technique_id == tid,
                ),
            )
        ).scalar_one_or_none()
        if master_tech is None or int(master_tech.level or 0) < 1:
            raise AppError(
                code=40000,
                message="师傅尚未掌握该功法，无法请学",
                http_status=400,
            )

        day_key = daily.day_key
        row = (
            await self._session.execute(
                select(MentorTransmission).where(
                    MentorTransmission.bond_id == bond.id,
                    MentorTransmission.item_kind == "technique",
                    MentorTransmission.item_id == tid,
                ),
            )
        ).scalar_one_or_none()
        if row is not None and row.status == "completed":
            raise AppError(code=40000, message="该项已学习完成", http_status=400)
        if row is not None and row.last_study_day_key == day_key:
            raise AppError(code=40000, message="今日已请学过该项，请明日再来", http_status=400)

        meta, label = self._resolve_teach_meta("technique", tid, master=master)
        required = teach_sessions_required(
            item_kind="technique",
            item_meta=meta,
            teach_cfg=teach_cfg,
        )
        gain = max(1, int(study_cfg.get("progress_gain") or 1))
        if row is None:
            row = MentorTransmission(
                bond_id=bond.id,
                item_kind="technique",
                item_id=tid,
                required_sessions=required,
                progress=0,
                status="active",
            )
            self._session.add(row)
            await self._session.flush()
        else:
            row.required_sessions = max(int(row.required_sessions), required)

        row.progress = int(row.progress) + gain
        row.last_study_day_key = day_key
        daily.study_count = int(daily.study_count or 0) + 1
        completed = False
        if row.progress >= int(row.required_sessions):
            row.status = "completed"
            row.completed_at = now_utc()
            completed = True
            await self._apply_teach_complete(
                master=master,
                apprentice=character,
                item_kind="technique",
                item_id=tid,
                teach_cfg=teach_cfg,
            )
        await self._session.flush()
        msg = (
            f"请学「{label}」完成"
            if completed
            else f"请学「{label}」进度 {row.progress}/{row.required_sessions}"
        )
        return {
            "message": msg,
            "completed": completed,
            "transmission": {
                "item_kind": "technique",
                "item_id": tid,
                "name": label,
                "progress": int(row.progress),
                "required_sessions": int(row.required_sessions),
                "status": row.status,
            },
            "daily": await self._daily_public(bond),
            "transmissions": await self._transmissions_public(bond),
            "character": await self._character_public(character),
        }

    async def _lesson_dao(
        self,
        *,
        master: Character,
        apprentice: Character,
        resource: str,
        need_ratio: float,
        pool_ratio: float,
    ) -> dict[str, Any]:
        """传道：灌体修为或炼体度。"""
        res = str(resource or "spirit").strip().lower()
        if res not in {"spirit", "body"}:
            raise AppError(code=40000, message="传道资源须为修为或炼体度", http_status=400)
        if res == "spirit":
            need = self._apprentice_spirit_breakthrough_need(apprentice)
            pool = int(master.cultivation_points or 0)
            amount = lesson_transfer_amount(
                apprentice_need=need,
                master_pool=pool,
                need_ratio=need_ratio,
                pool_ratio=pool_ratio,
            )
            if amount <= 0:
                raise AppError(code=40000, message="可传授修为不足（受双方资源限制）", http_status=400)
            master.cultivation_points = pool - amount
            apprentice.cultivation_points = int(apprentice.cultivation_points or 0) + amount
            return {
                "message": f"传道成功：徒弟修为池 +{amount}（师傅修为 -{amount}）",
                "amount": amount,
                "resource": "spirit",
                "resource_label_zh": "修为",
            }
        from app.domain.body_temper import current_progress_required

        need = int(current_progress_required(apprentice))
        pool = int(master.body_tempering_points or 0)
        amount = lesson_transfer_amount(
            apprentice_need=need,
            master_pool=pool,
            need_ratio=need_ratio,
            pool_ratio=pool_ratio,
        )
        if amount <= 0:
            raise AppError(code=40000, message="可传授炼体度不足（受双方资源限制）", http_status=400)
        master.body_tempering_points = pool - amount
        apprentice.body_tempering_points = int(apprentice.body_tempering_points or 0) + amount
        return {
            "message": f"传道成功：徒弟炼体度 +{amount}（师傅炼体度 -{amount}）",
            "amount": amount,
            "resource": "body",
            "resource_label_zh": "炼体度",
        }

    async def _lesson_craft(
        self,
        *,
        master: Character,
        apprentice: Character,
        technique_id: str | None,
        need_ratio: float,
        pool_ratio: float,
    ) -> dict[str, Any]:
        """授业：提升制造业功法等级，消耗师傅制造业经验。"""
        tid = str(technique_id or "").strip()
        if not tid:
            raise AppError(code=40000, message="请选择要授业的制造业功法", http_status=400)
        cfg = get_game_config().techniques.get(tid)
        if cfg is None or str(getattr(cfg, "track", "") or "") != "crafting":
            raise AppError(code=40000, message="仅可授业制造业轨道功法", http_status=400)
        need = await self._technique_next_cost(apprentice, tid)
        pool = int(master.crafting_exp or 0)
        amount = lesson_transfer_amount(
            apprentice_need=need,
            master_pool=pool,
            need_ratio=need_ratio,
            pool_ratio=pool_ratio,
        )
        if amount <= 0:
            raise AppError(code=40000, message="可授业经验不足（受双方资源限制）", http_status=400)
        master.crafting_exp = pool - amount
        levels = await self._invest_technique_points(apprentice, tid, amount)
        name = str(getattr(cfg, "name", None) or tid)
        return {
            "message": (
                f"授业成功：「{name}」投入 {amount} 制造业经验，提升 {levels} 级"
            ),
            "amount": amount,
            "levels_gained": levels,
            "technique_id": tid,
            "technique_name": name,
        }

    async def _lesson_technique(
        self,
        *,
        master: Character,
        apprentice: Character,
        technique_id: str | None,
        need_ratio: float,
        pool_ratio: float,
    ) -> dict[str, Any]:
        """解惑：提升功法等级，按轨道消耗师傅修为/炼体度。"""
        tid = str(technique_id or "").strip()
        if not tid:
            raise AppError(code=40000, message="请选择要解惑的功法", http_status=400)
        cfg = get_game_config().techniques.get(tid)
        if cfg is None:
            raise AppError(code=40000, message="未知功法", http_status=404)
        track = str(getattr(cfg, "track", "") or "spirit")
        need = await self._technique_next_cost(apprentice, tid)
        if track == "body":
            pool = int(master.body_tempering_points or 0)
            pool_label = "炼体度"
        elif track == "crafting":
            pool = int(master.crafting_exp or 0)
            pool_label = "制造业经验"
        else:
            pool = int(master.cultivation_points or 0)
            pool_label = "修为"
        amount = lesson_transfer_amount(
            apprentice_need=need,
            master_pool=pool,
            need_ratio=need_ratio,
            pool_ratio=pool_ratio,
        )
        if amount <= 0:
            raise AppError(code=40000, message="可解惑资源不足（受双方资源限制）", http_status=400)
        if track == "body":
            master.body_tempering_points = pool - amount
        elif track == "crafting":
            master.crafting_exp = pool - amount
        else:
            master.cultivation_points = pool - amount
        levels = await self._invest_technique_points(apprentice, tid, amount)
        name = str(getattr(cfg, "name", None) or tid)
        return {
            "message": (
                f"解惑成功：「{name}」投入 {amount}（师傅{pool_label} -{amount}），提升 {levels} 级"
            ),
            "amount": amount,
            "levels_gained": levels,
            "technique_id": tid,
            "technique_name": name,
            "resource_label_zh": pool_label,
        }

    async def _maybe_auto_graduate(self, bond: MentorBond) -> dict[str, Any] | None:
        """弟子追上师傅大境界时自动出师。"""
        if bond.status != "active":
            return None
        master = await self._session.get(Character, bond.master_character_id)
        apprentice = await self._session.get(Character, bond.apprentice_character_id)
        if master is None or apprentice is None:
            return None
        if not should_auto_graduate(
            master_major=str(master.major_realm),
            apprentice_major=str(apprentice.major_realm),
            realm_order=self._realm_order(),
            max_gap=int(self._cfg().auto_graduate_max_gap),
        ):
            return None
        return await self._complete_graduate(
            bond,
            master=master,
            apprentice=apprentice,
            auto=True,
            viewer_id=master.id,
        )

    async def _complete_graduate(
        self,
        bond: MentorBond,
        *,
        master: Character,
        apprentice: Character,
        auto: bool,
        viewer_id: int,
    ) -> dict[str, Any]:
        """结算出师奖励并关闭师徒键。"""
        grad = dict(self._cfg().graduate or {})
        ap_gain = int(grad.get("apprentice_spirit_pool") or 0)
        if ap_gain > 0:
            apprentice.cultivation_points = int(apprentice.cultivation_points or 0) + ap_gain
        m_stone = int(grad.get("master_spirit_stones") or 0)
        if m_stone > 0:
            await self._ledger.adjust_spirit_stones(
                master,
                delta=m_stone,
                reason="mentor_graduate",
                note_zh="自动出师奖励" if auto else "出师奖励",
                ref_type="mentor",
                ref_id=str(bond.id),
            )
        bond.status = "graduated"
        bond.closed_at = now_utc()
        cleared_direct = False
        # 出师自动解除亲传
        if bool(bond.is_direct):
            bond.is_direct = False
            bond.direct_set_day_key = None
            bond.direct_cleared_day_key = now_utc().strftime("%Y-%m-%d")
            cleared_direct = True
        await self._session.flush()
        msg = (
            "弟子已达师傅大境界，自动出师，师徒缘圆满"
            if auto
            else "出师成功，师徒缘已圆满"
        )
        log_lines = [msg]
        if cleared_direct:
            log_lines.append(f"「{apprentice.name}」出师，已自动解除亲传")
        return {
            "message": "；".join(log_lines),
            "log_lines": log_lines,
            "auto": auto,
            "bond": await self._bond_public(bond, viewer_id=viewer_id),
        }

    async def graduate(self, user: User) -> dict[str, Any]:
        """出师（须完成 required 任务；同境界会优先自动出师）。"""
        require_mentor_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        bond = await self.get_active_bond_for(character.id)
        if bond is None:
            raise AppError(code=40150, message="无活跃师徒关系", http_status=400)
        auto = await self._maybe_auto_graduate(bond)
        if auto is not None:
            return auto
        for qid, qdef in (self._cfg().quests or {}).items():
            if not isinstance(qdef, dict):
                continue
            if not bool(qdef.get("required_for_graduate", True)):
                continue
            prog = (
                await self._session.execute(
                    select(MentorQuestProgress).where(
                        MentorQuestProgress.bond_id == bond.id,
                        MentorQuestProgress.quest_id == str(qid),
                    ),
                )
            ).scalar_one_or_none()
            if prog is None or prog.completed_at is None:
                raise AppError(
                    code=40150,
                    message=f"尚未完成任务「{qdef.get('name') or qid}」",
                    http_status=400,
                )
        apprentice = await self._session.get(Character, bond.apprentice_character_id)
        master = await self._session.get(Character, bond.master_character_id)
        if apprentice is None or master is None:
            raise AppError(code=40150, message="角色不存在", http_status=404)
        return await self._complete_graduate(
            bond,
            master=master,
            apprentice=apprentice,
            auto=False,
            viewer_id=character.id,
        )

    async def dissolve(self, user: User) -> dict[str, Any]:
        """解除师徒。"""
        require_mentor_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        bond = await self.get_active_bond_for(character.id)
        if bond is None:
            raise AppError(code=40150, message="无活跃师徒关系", http_status=400)
        bond.status = "dissolved"
        bond.closed_at = now_utc()
        await self._session.flush()
        return {"message": "已解除师徒关系", "bond_id": bond.id}

    # ----- helpers -----

    async def _expire_stale(self) -> None:
        sec = int(self._cfg().request_expire_sec or 0)
        if sec <= 0:
            return
        cutoff = now_utc() - timedelta(seconds=sec)
        rows = (
            await self._session.execute(
                select(MentorBond).where(MentorBond.status == "pending"),
            )
        ).scalars().all()
        for row in rows:
            created = ensure_aware_utc(row.created_at) if row.created_at else None
            if created is not None and created < cutoff:
                row.status = "rejected"
                row.closed_at = now_utc()
        await self._session.flush()

    async def _assert_dissolve_cooldown(self, character_id: int) -> None:
        sec = int(self._cfg().dissolve_cooldown_sec or 0)
        if sec <= 0:
            return
        last = (
            await self._session.execute(
                select(MentorBond)
                .where(
                    MentorBond.status.in_(("dissolved", "graduated")),
                    or_(
                        MentorBond.master_character_id == character_id,
                        MentorBond.apprentice_character_id == character_id,
                    ),
                )
                .order_by(MentorBond.closed_at.desc())
                .limit(1),
            )
        ).scalar_one_or_none()
        if last is None or last.closed_at is None:
            return
        elapsed = (now_utc() - ensure_aware_utc(last.closed_at)).total_seconds()
        if elapsed < sec:
            raise AppError(
                code=40150,
                message=f"解除冷却中（还需 {int(sec - elapsed)} 秒）",
                http_status=400,
            )

    async def _resolve_character(
        self,
        character_id: int | None,
        name: str | None,
    ) -> Character:
        if character_id is not None:
            ch = await self._session.get(Character, int(character_id))
            if ch is None:
                raise AppError(code=40000, message="目标角色不存在", http_status=404)
            return ch
        nm = (name or "").strip()
        if not nm:
            raise AppError(code=40000, message="请提供目标角色 id 或道号", http_status=400)
        ch = (
            await self._session.execute(select(Character).where(Character.name == nm))
        ).scalar_one_or_none()
        if ch is None:
            raise AppError(code=40000, message=f"找不到道号「{nm}」", http_status=404)
        return ch

    async def _bond_public(self, row: MentorBond, *, viewer_id: int) -> dict[str, Any]:
        master = await self._session.get(Character, row.master_character_id)
        apprentice = await self._session.get(Character, row.apprentice_character_id)
        role = "master" if viewer_id == row.master_character_id else "apprentice"
        if viewer_id not in (row.master_character_id, row.apprentice_character_id):
            role = "other"
        cref = build_mentor_ref(row.id) if row.status == "active" else None
        return {
            "bond_id": row.id,
            "status": row.status,
            "intent": row.intent,
            "role": role,
            "is_direct": bool(row.is_direct),
            "master_character_id": row.master_character_id,
            "master_name": master.name if master else str(row.master_character_id),
            "apprentice_character_id": row.apprentice_character_id,
            "apprentice_name": apprentice.name if apprentice else str(row.apprentice_character_id),
            "channel_ref": cref.channel_ref if cref else None,
            "room_id": cref.room_id if cref else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "accepted_at": row.accepted_at.isoformat() if row.accepted_at else None,
        }

    async def _quests_public(self, bond: MentorBond) -> list[dict[str, Any]]:
        items = []
        for qid, qdef in (self._cfg().quests or {}).items():
            if not isinstance(qdef, dict):
                continue
            prog = (
                await self._session.execute(
                    select(MentorQuestProgress).where(
                        MentorQuestProgress.bond_id == bond.id,
                        MentorQuestProgress.quest_id == str(qid),
                    ),
                )
            ).scalar_one_or_none()
            target = int(qdef.get("target_count") or 1)
            progress = int(prog.progress) if prog else 0
            items.append(
                {
                    "quest_id": str(qid),
                    "name": str(qdef.get("name") or qid),
                    "description": str(qdef.get("description") or ""),
                    "progress": progress,
                    "target_count": target,
                    "completed": prog is not None and prog.completed_at is not None,
                    "required_for_graduate": bool(qdef.get("required_for_graduate", True)),
                },
            )
        return items

    async def _character_public(self, character: Character) -> dict[str, Any]:
        from app.services.character_service import CharacterService

        await self._session.refresh(character)
        return (
            await CharacterService(self._session).enrich_public(character)
        ).model_dump(mode="json")

    async def _get_or_create_daily(self, bond_id: int) -> MentorPassDaily:
        day_key = now_utc().strftime("%Y-%m-%d")
        daily = (
            await self._session.execute(
                select(MentorPassDaily).where(
                    MentorPassDaily.bond_id == bond_id,
                    MentorPassDaily.day_key == day_key,
                ),
            )
        ).scalar_one_or_none()
        if daily is None:
            daily = MentorPassDaily(
                bond_id=bond_id,
                day_key=day_key,
                pass_count=0,
                lesson_kind=None,
                lesson_dao_count=0,
                lesson_craft_count=0,
                lesson_technique_count=0,
                teach_count=0,
                study_count=0,
            )
            self._session.add(daily)
            await self._session.flush()
        return daily

    async def _daily_public(self, bond: MentorBond) -> dict[str, Any]:
        daily = await self._get_or_create_daily(bond.id)
        self._sync_legacy_lesson_counts(daily)
        teach_cap = int((self._cfg().teach or {}).get("daily_cap") or 1)
        study_cap = int((self._cfg().study or {}).get("daily_cap") or 1)
        is_direct = bool(bond.is_direct)
        direct_cfg = dict(self._cfg().direct_disciple or {})
        dao_cap = lesson_kind_daily_cap(
            kind="dao", is_direct=is_direct, direct_cfg=direct_cfg,
        )
        craft_cap = lesson_kind_daily_cap(
            kind="craft", is_direct=is_direct, direct_cfg=direct_cfg,
        )
        tech_cap = lesson_kind_daily_cap(
            kind="technique", is_direct=is_direct, direct_cfg=direct_cfg,
        )
        dao_n = int(daily.lesson_dao_count or 0)
        craft_n = int(daily.lesson_craft_count or 0)
        tech_n = int(daily.lesson_technique_count or 0)
        total = dao_n + craft_n + tech_n
        can_dao = dao_n < dao_cap and (is_direct or total == 0)
        can_craft = craft_n < craft_cap and (is_direct or total == 0)
        can_technique = tech_n < tech_cap and (is_direct or total == 0)
        return {
            "day_key": daily.day_key,
            "lesson_kind": daily.lesson_kind,
            "lesson_kind_label_zh": (
                _lesson_label(daily.lesson_kind) if daily.lesson_kind else None
            ),
            "lesson_dao_count": dao_n,
            "lesson_craft_count": craft_n,
            "lesson_technique_count": tech_n,
            "lesson_dao_cap": dao_cap,
            "lesson_craft_cap": craft_cap,
            "lesson_technique_cap": tech_cap,
            "can_lesson_dao": can_dao,
            "can_lesson_craft": can_craft,
            "can_lesson_technique": can_technique,
            "lesson_done": not (can_dao or can_craft or can_technique),
            "is_direct": is_direct,
            "teach_count": int(daily.teach_count or 0),
            "teach_cap": teach_cap,
            "teach_done": int(daily.teach_count or 0) >= teach_cap,
            "study_count": int(daily.study_count or 0),
            "study_cap": study_cap,
            "study_done": int(daily.study_count or 0) >= study_cap,
        }

    def _sync_legacy_lesson_counts(self, daily: MentorPassDaily) -> None:
        """旧数据仅有 lesson_kind 时回填分项计数。"""
        total = (
            int(daily.lesson_dao_count or 0)
            + int(daily.lesson_craft_count or 0)
            + int(daily.lesson_technique_count or 0)
        )
        if total > 0 or not daily.lesson_kind:
            return
        kind = str(daily.lesson_kind)
        if kind == "dao":
            daily.lesson_dao_count = 1
        elif kind == "craft":
            daily.lesson_craft_count = 1
        elif kind == "technique":
            daily.lesson_technique_count = 1

    @staticmethod
    def _lesson_kind_count(daily: MentorPassDaily, kind: str) -> int:
        if kind == "dao":
            return int(daily.lesson_dao_count or 0)
        if kind == "craft":
            return int(daily.lesson_craft_count or 0)
        if kind == "technique":
            return int(daily.lesson_technique_count or 0)
        return 0

    @staticmethod
    def _bump_lesson_kind_count(daily: MentorPassDaily, kind: str) -> None:
        if kind == "dao":
            daily.lesson_dao_count = int(daily.lesson_dao_count or 0) + 1
        elif kind == "craft":
            daily.lesson_craft_count = int(daily.lesson_craft_count or 0) + 1
        elif kind == "technique":
            daily.lesson_technique_count = int(daily.lesson_technique_count or 0) + 1

    async def _lineage_public(self, viewer_id: int) -> dict[str, Any] | None:
        """
        师承单：优先展示「我为师傅」的名录；否则展示当前/最近师傅门下。

        含 active + graduated，按拜师时间排序并标注大/二/三弟子。
        """
        as_master = (
            await self._session.execute(
                select(MentorBond).where(
                    MentorBond.master_character_id == viewer_id,
                    MentorBond.status.in_(("active", "graduated")),
                ),
            )
        ).scalars().all()
        master_id: int | None = None
        can_set_direct = False
        if as_master:
            master_id = viewer_id
            can_set_direct = True
        else:
            as_appr = (
                await self._session.execute(
                    select(MentorBond)
                    .where(
                        MentorBond.apprentice_character_id == viewer_id,
                        MentorBond.status.in_(("active", "graduated")),
                    )
                    .order_by(MentorBond.accepted_at.desc(), MentorBond.id.desc()),
                )
            ).scalars().all()
            if not as_appr:
                return None
            master_id = int(as_appr[0].master_character_id)
        assert master_id is not None
        master = await self._session.get(Character, master_id)
        rows = (
            await self._session.execute(
                select(MentorBond).where(
                    MentorBond.master_character_id == master_id,
                    MentorBond.status.in_(("active", "graduated")),
                ),
            )
        ).scalars().all()

        def _sort_key(b: MentorBond) -> tuple:
            at = ensure_aware_utc(b.accepted_at) if b.accepted_at else None
            # 无 accepted_at 时退回 created_at
            ts = at or (ensure_aware_utc(b.created_at) if b.created_at else now_utc())
            return (ts, int(b.id))

        ordered = sorted(rows, key=_sort_key)
        disciples: list[dict[str, Any]] = []
        direct_count = 0
        today = now_utc().strftime("%Y-%m-%d")
        direct_cfg = dict(self._cfg().direct_disciple or {})
        cooldown_days = int(direct_cfg.get("cooldown_days") or 1)
        for idx, bond in enumerate(ordered):
            appr = await self._session.get(Character, bond.apprentice_character_id)
            graduated = bond.status == "graduated"
            is_direct = bool(bond.is_direct)
            if is_direct:
                direct_count += 1
            title = disciple_ordinal_title(idx)
            name = appr.name if appr else str(bond.apprentice_character_id)
            can_clear = is_direct and direct_can_clear(
                set_day_key=bond.direct_set_day_key,
                today_key=today,
                cooldown_days=cooldown_days,
            )
            can_appoint = (not is_direct) and direct_can_appoint(
                cleared_day_key=bond.direct_cleared_day_key,
                today_key=today,
            )
            lock_reason = None
            if is_direct and not can_clear:
                lock_reason = "指定后需隔日方可解除"
            elif (not is_direct) and not can_appoint:
                lock_reason = "解除当日不可再指定"
            disciples.append(
                {
                    "bond_id": bond.id,
                    "character_id": bond.apprentice_character_id,
                    "name": name,
                    "display_name": (
                        f"{name}（已出师）" if graduated else name
                    ),
                    "ordinal": idx + 1,
                    "ordinal_title_zh": title,
                    "status": bond.status,
                    "graduated": graduated,
                    "is_direct": is_direct,
                    "can_clear_direct": can_clear if can_set_direct else False,
                    "can_appoint_direct": can_appoint if can_set_direct else False,
                    "direct_lock_reason": lock_reason if can_set_direct else None,
                    "accepted_at": (
                        bond.accepted_at.isoformat() if bond.accepted_at else None
                    ),
                },
            )
        direct_cap = int(direct_cfg.get("max_count") or 3)
        return {
            "master_character_id": master_id,
            "master_name": master.name if master else str(master_id),
            "disciples": disciples,
            "direct_cap": direct_cap,
            "direct_count": direct_count,
            "direct_cooldown_days": cooldown_days,
            "can_set_direct": can_set_direct,
        }

    async def _teaching_options(self, bond: MentorBond) -> dict[str, Any]:
        master = await self._session.get(Character, bond.master_character_id)
        apprentice = await self._session.get(Character, bond.apprentice_character_id)
        if master is None or apprentice is None:
            return {
                "craft_techniques": [],
                "techniques": [],
                "recipes": [],
                "study_techniques": [],
            }
        tech_cfg = get_game_config().techniques
        craft_opts: list[dict[str, Any]] = []
        tech_opts: list[dict[str, Any]] = []
        for tid, cfg in tech_cfg.items():
            next_cost = await self._technique_next_cost(apprentice, tid)
            item = {
                "technique_id": tid,
                "name": str(getattr(cfg, "name", None) or tid),
                "track": str(getattr(cfg, "track", "") or ""),
                "next_cost": next_cost,
            }
            if str(getattr(cfg, "track", "") or "") == "crafting":
                craft_opts.append(item)
            tech_opts.append(item)
        # 徒弟请学：仅师傅已掌握（level≥1）的功法
        master_tech_rows = (
            await self._session.execute(
                select(CharacterTechnique).where(
                    CharacterTechnique.character_id == master.id,
                    CharacterTechnique.level >= 1,
                ),
            )
        ).scalars().all()
        study_opts: list[dict[str, Any]] = []
        for mrow in master_tech_rows:
            tid = str(mrow.technique_id)
            cfg = tech_cfg.get(tid)
            study_opts.append(
                {
                    "technique_id": tid,
                    "name": str(getattr(cfg, "name", None) or tid) if cfg else tid,
                    "track": str(getattr(cfg, "track", "") or "") if cfg else "",
                    "master_level": int(mrow.level or 0),
                    "next_cost": await self._technique_next_cost(apprentice, tid),
                },
            )
        recipes: list[dict[str, Any]] = []
        craft = get_game_config().craft_recipes
        teach_cfg = dict(self._cfg().teach or {})
        for rid, rdef in (craft.recipes or {}).items():
            raw = {
                "name": getattr(rdef, "name", rid),
                "branch": getattr(rdef, "branch", ""),
                "teach_tier": getattr(rdef, "teach_tier", None),
                "teach_sessions": getattr(rdef, "teach_sessions", None),
            }
            sessions = teach_sessions_required(
                item_kind="recipe",
                item_meta=raw,
                teach_cfg=teach_cfg,
            )
            recipes.append(
                {
                    "recipe_id": rid,
                    "name": str(raw.get("name") or rid),
                    "branch": str(raw.get("branch") or ""),
                    "required_sessions": sessions,
                },
            )
        spirit_need = self._apprentice_spirit_breakthrough_need(apprentice)
        from app.domain.body_temper import current_progress_required

        body_need = int(current_progress_required(apprentice))
        lesson_cfg = dict(self._cfg().daily_lesson or {})
        return {
            "dao": {
                "spirit": {
                    "apprentice_need": spirit_need,
                    "master_pool": int(master.cultivation_points or 0),
                    "preview_amount": lesson_transfer_amount(
                        apprentice_need=spirit_need,
                        master_pool=int(master.cultivation_points or 0),
                        need_ratio=float(lesson_cfg.get("apprentice_need_ratio") or 1.0),
                        pool_ratio=float(lesson_cfg.get("master_pool_ratio") or 0.1),
                    ),
                },
                "body": {
                    "apprentice_need": body_need,
                    "master_pool": int(master.body_tempering_points or 0),
                    "preview_amount": lesson_transfer_amount(
                        apprentice_need=body_need,
                        master_pool=int(master.body_tempering_points or 0),
                        need_ratio=float(lesson_cfg.get("apprentice_need_ratio") or 1.0),
                        pool_ratio=float(lesson_cfg.get("master_pool_ratio") or 0.1),
                    ),
                },
            },
            "craft_techniques": craft_opts,
            "techniques": tech_opts,
            "study_techniques": study_opts,
            "recipes": recipes,
            "master_crafting_exp": int(master.crafting_exp or 0),
        }

    async def _transmissions_public(self, bond: MentorBond) -> list[dict[str, Any]]:
        rows = (
            await self._session.execute(
                select(MentorTransmission)
                .where(MentorTransmission.bond_id == bond.id)
                .order_by(MentorTransmission.id.desc()),
            )
        ).scalars().all()
        out: list[dict[str, Any]] = []
        for row in rows:
            meta, label = self._resolve_teach_meta(
                row.item_kind,
                row.item_id,
                master=None,
                allow_missing=True,
            )
            out.append(
                {
                    "item_kind": row.item_kind,
                    "item_id": row.item_id,
                    "name": label,
                    "progress": int(row.progress),
                    "required_sessions": int(row.required_sessions),
                    "status": row.status,
                    "meta": meta,
                },
            )
        return out

    def _apprentice_spirit_breakthrough_need(self, apprentice: Character) -> int:
        major = get_major_realm(str(apprentice.major_realm or ""))
        if major is None:
            return 0
        stage = major.stage_by_number(int(apprentice.realm_stage or 1))
        if stage is None:
            return 0
        return max(0, int(stage.cultivation_required))

    async def _technique_next_cost(self, character: Character, technique_id: str) -> int:
        cfg = get_game_config().techniques.get(technique_id)
        if cfg is None:
            return 0
        row = (
            await self._session.execute(
                select(CharacterTechnique).where(
                    CharacterTechnique.character_id == character.id,
                    CharacterTechnique.technique_id == technique_id,
                ),
            )
        ).scalar_one_or_none()
        level = int(row.level) if row is not None else 0
        costs = list(getattr(cfg, "cost_per_level", None) or [])
        if level >= int(getattr(cfg, "max_level", 0) or 0):
            return 0
        if level >= len(costs):
            return 0
        return max(0, int(costs[level]))

    async def _invest_technique_points(
        self,
        character: Character,
        technique_id: str,
        amount: int,
    ) -> int:
        """Spend points into technique levels; returns levels gained."""
        cfg = get_game_config().techniques.get(technique_id)
        if cfg is None:
            raise AppError(code=40000, message="未知功法", http_status=404)
        row = (
            await self._session.execute(
                select(CharacterTechnique).where(
                    CharacterTechnique.character_id == character.id,
                    CharacterTechnique.technique_id == technique_id,
                ),
            )
        ).scalar_one_or_none()
        if row is None:
            row = CharacterTechnique(
                character_id=character.id,
                technique_id=technique_id,
                level=0,
            )
            self._session.add(row)
            await self._session.flush()
        remaining = max(0, int(amount))
        levels = 0
        costs = list(getattr(cfg, "cost_per_level", None) or [])
        max_level = int(getattr(cfg, "max_level", 0) or 0)
        while remaining > 0 and int(row.level) < max_level:
            idx = int(row.level)
            if idx >= len(costs):
                break
            need = int(costs[idx])
            if remaining < need:
                break
            remaining -= need
            row.level = int(row.level) + 1
            levels += 1
        await self._session.flush()
        return levels

    def _resolve_teach_meta(
        self,
        item_kind: str,
        item_id: str,
        *,
        master: Character | None,
        allow_missing: bool = False,
    ) -> tuple[dict[str, Any], str]:
        if item_kind == "technique":
            cfg = get_game_config().techniques.get(item_id)
            if cfg is None:
                if allow_missing:
                    return {}, item_id
                raise AppError(code=40000, message="未知功法", http_status=404)
            if master is not None:
                # 师傅须自身已学该功法且等级>0，或至少拥有条目
                pass
            return (
                {
                    "name": getattr(cfg, "name", item_id),
                    "track": getattr(cfg, "track", ""),
                    "teach_tier": getattr(cfg, "teach_tier", None),
                    "teach_sessions": getattr(cfg, "teach_sessions", None),
                },
                str(getattr(cfg, "name", None) or item_id),
            )
        craft = get_game_config().craft_recipes
        recipes = craft.recipes or {}
        rdef = recipes.get(item_id)
        if rdef is None:
            if allow_missing:
                return {}, item_id
            raise AppError(code=40000, message="未知配方/图纸", http_status=404)
        raw = {
            "name": getattr(rdef, "name", item_id),
            "branch": getattr(rdef, "branch", ""),
            "teach_tier": getattr(rdef, "teach_tier", None),
            "teach_sessions": getattr(rdef, "teach_sessions", None),
        }
        return raw, str(raw.get("name") or item_id)

    async def _apply_teach_complete(
        self,
        *,
        master: Character,
        apprentice: Character,
        item_kind: str,
        item_id: str,
        teach_cfg: dict[str, Any],
    ) -> None:
        if item_kind == "recipe":
            exists = (
                await self._session.execute(
                    select(CharacterCraftKnowledge.id).where(
                        CharacterCraftKnowledge.character_id == apprentice.id,
                        CharacterCraftKnowledge.recipe_id == item_id,
                    ),
                )
            ).scalar_one_or_none()
            if exists is None:
                self._session.add(
                    CharacterCraftKnowledge(
                        character_id=apprentice.id,
                        recipe_id=item_id,
                        source="mentor",
                    ),
                )
            return
        gain = int(teach_cfg.get("technique_complete_level_gain") or 1)
        row = (
            await self._session.execute(
                select(CharacterTechnique).where(
                    CharacterTechnique.character_id == apprentice.id,
                    CharacterTechnique.technique_id == item_id,
                ),
            )
        ).scalar_one_or_none()
        if row is None:
            row = CharacterTechnique(
                character_id=apprentice.id,
                technique_id=item_id,
                level=0,
            )
            self._session.add(row)
            await self._session.flush()
        master_row = (
            await self._session.execute(
                select(CharacterTechnique).where(
                    CharacterTechnique.character_id == master.id,
                    CharacterTechnique.technique_id == item_id,
                ),
            )
        ).scalar_one_or_none()
        master_lv = int(master_row.level) if master_row is not None else 0
        cfg = get_game_config().techniques.get(item_id)
        max_level = int(getattr(cfg, "max_level", 99) or 99) if cfg else 99
        # 弟子至少提升 gain 级，且不超过师傅等级与功法上限
        target = min(max_level, int(row.level) + max(1, gain))
        if master_lv > 0:
            target = min(target, master_lv)
        row.level = max(int(row.level), target)
        await self._session.flush()


def _lesson_label(kind: str | None) -> str:
    return {
        "dao": "传道",
        "craft": "授业",
        "technique": "解惑",
    }.get(str(kind or ""), str(kind or ""))
