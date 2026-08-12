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
from app.db.models.mentor import MentorBond, MentorPassDaily, MentorQuestProgress
from app.domain.channel_membership import build_mentor_ref
from app.domain.mentor_rules import master_realm_ok
from app.schemas.common import AppError
from app.services.currency_ledger_service import CurrencyLedgerService
from app.services.play_gate import PlayGate
from app.services.realm_config import get_game_config

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
        """名录、申请、任务。"""
        require_mentor_enabled()
        character = await self._gate.require_character(user)
        await self._expire_stale()
        active = await self.get_active_bond_for(character.id)
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
        return {
            "bond": bond_public,
            "incoming": [await self._bond_public(b, viewer_id=character.id) for b in pending_in],
            "outgoing": [await self._bond_public(b, viewer_id=character.id) for b in pending_out],
            "quests": quests,
            "channel_ref": bond_public["channel_ref"] if bond_public else None,
            "config": {
                "max_apprentices": int(self._cfg().max_apprentices),
                "min_realm_gap": int(self._cfg().min_realm_gap),
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
        """传功：师傅耗灵石，徒弟加修为池；并推进 first_lesson。"""
        require_mentor_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        bond = await self.get_active_bond_for(character.id)
        if bond is None:
            raise AppError(code=40150, message="无活跃师徒关系", http_status=400)
        if character.id != bond.master_character_id:
            raise AppError(code=40150, message="仅师傅可传功", http_status=403)
        pass_cfg = dict(self._cfg().pass_cultivation or {})
        day_key = now_utc().strftime("%Y-%m-%d")
        daily = (
            await self._session.execute(
                select(MentorPassDaily).where(
                    MentorPassDaily.bond_id == bond.id,
                    MentorPassDaily.day_key == day_key,
                ),
            )
        ).scalar_one_or_none()
        if daily is None:
            daily = MentorPassDaily(bond_id=bond.id, day_key=day_key, pass_count=0)
            self._session.add(daily)
            await self._session.flush()
        cap = int(pass_cfg.get("daily_cap_per_bond") or 3)
        if int(daily.pass_count) >= cap:
            raise AppError(code=40000, message="今日传功次数已达上限", http_status=400)
        cost = int(pass_cfg.get("master_spirit_stone_cost") or 20)
        await self._ledger.adjust_spirit_stones(
            character,
            delta=-cost,
            reason="mentor_pass",
            note_zh="传功",
            ref_type="mentor",
            ref_id=str(bond.id),
        )
        apprentice = await self._session.get(Character, bond.apprentice_character_id)
        gain = int(pass_cfg.get("apprentice_spirit_pool_gain") or 30)
        if apprentice is not None and gain > 0:
            apprentice.cultivation_points = int(apprentice.cultivation_points or 0) + gain
        daily.pass_count = int(daily.pass_count) + 1
        await self._session.flush()
        # 推进样本任务
        if "first_lesson" in (self._cfg().quests or {}):
            await self.progress_quest(user, "first_lesson", amount=1)
        return {
            "message": f"传功成功，徒弟修为池 +{gain}",
            "pass_count_today": daily.pass_count,
            "quests": await self._quests_public(bond),
            "character": await self._character_public(character),
        }

    async def graduate(self, user: User) -> dict[str, Any]:
        """出师（须完成 required 任务）。"""
        require_mentor_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        bond = await self.get_active_bond_for(character.id)
        if bond is None:
            raise AppError(code=40150, message="无活跃师徒关系", http_status=400)
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
        grad = dict(self._cfg().graduate or {})
        apprentice = await self._session.get(Character, bond.apprentice_character_id)
        master = await self._session.get(Character, bond.master_character_id)
        ap_gain = int(grad.get("apprentice_spirit_pool") or 0)
        if apprentice is not None and ap_gain > 0:
            apprentice.cultivation_points = int(apprentice.cultivation_points or 0) + ap_gain
        m_stone = int(grad.get("master_spirit_stones") or 0)
        if master is not None and m_stone > 0:
            await self._ledger.adjust_spirit_stones(
                master,
                delta=m_stone,
                reason="mentor_graduate",
                note_zh="出师奖励",
                ref_type="mentor",
                ref_id=str(bond.id),
            )
        bond.status = "graduated"
        bond.closed_at = now_utc()
        await self._session.flush()
        return {
            "message": "出师成功，师徒缘已圆满",
            "bond": await self._bond_public(bond, viewer_id=character.id),
        }

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
