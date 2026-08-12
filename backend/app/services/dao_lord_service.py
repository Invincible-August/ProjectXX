"""
道主服务：空位就任、开窗状态、席位运营；有主更替走赛会（DaoContestService）。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import (
    Character,
    DaoChallengeSession,
    DaoLordship,
    DefenseSnapshot,
    User,
)
from app.domain.dao_lord_rules import (
    DaoLordWindowDef,
    can_challenge,
    can_claim,
    is_window_open,
)
from app.schemas.common import AppError
from app.services.dao_service import DaoService
from app.services.play_gate import PlayGate
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)

# GM 进程内强制开窗标志（非持久）
_GM_FORCE_WINDOW: bool = False


class DaoLordService:
    """道主榜 / 空位就任 / 席位运营用例（旧即时单挑已移除）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._gate = PlayGate(session)
        self._dao = DaoService(session)

    def _require_enabled(self) -> None:
        settings = get_settings()
        if not settings.dao_lord_enabled or not settings.dao_system_enabled:
            raise AppError(code=40094, message="道主挑战未开启", http_status=403)

    def _lord_cfg(self):
        return get_game_config().dao_lord

    def _windows(self) -> list[DaoLordWindowDef]:
        result = []
        for w in self._lord_cfg().windows:
            result.append(
                DaoLordWindowDef(
                    start_hour=int(w.get("start_hour") or 0),
                    end_hour=int(w.get("end_hour") or 24),
                    tz=str(w.get("tz") or "UTC"),
                    label_zh=str(w.get("label_zh") or "挑战时段"),
                    weekday=w.get("weekday"),
                ),
            )
        return result

    def window_status(self, *, now: datetime | None = None) -> dict[str, Any]:
        """当前是否开窗。"""
        global _GM_FORCE_WINDOW
        now = now or datetime.now(timezone.utc)
        settings = get_settings()
        if settings.dao_lord_force_window or _GM_FORCE_WINDOW:
            return {
                "open": True,
                "label": "GM 强制开窗",
                "next_open_at": None,
                "closes_at": None,
            }
        open_now, label = is_window_open(self._windows(), now=now)
        return {
            "open": open_now,
            "label": label,
            "next_open_at": None if open_now else None,
            "closes_at": None,
        }

    async def get_windows(self, user: User) -> dict[str, Any]:
        self._require_enabled()
        await self._gate.require_character(user)
        return self.window_status()

    async def _lordship(self, dao_id: str) -> DaoLordship | None:
        result = await self._session.execute(
            select(DaoLordship).where(DaoLordship.dao_id == dao_id),
        )
        return result.scalar_one_or_none()

    async def _abort_legacy_challenge_sessions(
        self,
        dao_id: str,
        *,
        reason: str = "admin_remove",
    ) -> int | None:
        """
        强制结束该道遗留旧单挑会话（玩家 API 已移除；仅运营清理用）。

        Args:
            dao_id: 大道 id。
            reason: 审计原因键。

        Returns:
            被 abort 的会话 id；无则 None。
        """
        result = await self._session.execute(
            select(DaoChallengeSession).where(
                DaoChallengeSession.dao_id == dao_id,
                DaoChallengeSession.phase.in_(("pending", "running")),
            ),
        )
        busy = result.scalar_one_or_none()
        if busy is None:
            return None
        aborted_id = int(busy.id)
        busy.phase = "finished"
        busy.result = "abort"
        busy.finished_at = datetime.now(timezone.utc)
        busy.battle_report_json = json.dumps(
            {"summary": "运营剔除道主，遗留挑战强制结束", "reason": reason},
            ensure_ascii=False,
        )
        await self._session.flush()
        return aborted_id

    async def get_board(self, user: User) -> dict[str, Any]:
        """各道道主榜；空位且本人达标则惰性自动就任。"""
        self._require_enabled()
        character = await self._gate.require_character(user)
        # 空位自动就任（无需手动夺位）
        auto = await self.try_auto_inaugurate(character)
        dao_row = await self._dao._get_or_create_row(character.id)
        win = self.window_status()
        seats = []
        for dao_id, entry in get_game_config().dao.entries.items():
            lord = await self._lordship(dao_id)
            lord_name = None
            lord_cid = None
            claimed_at = None
            if lord:
                lord_cid = lord.character_id
                claimed_at = lord.claimed_at.isoformat().replace("+00:00", "Z") if lord.claimed_at else None
                ch = await self._session.get(Character, lord.character_id)
                lord_name = ch.name if ch else None
            seat_occupied = lord is not None
            is_self = lord is not None and lord.character_id == character.id
            claim_ok, claim_reason = can_claim(
                fate_dao_id=dao_row.fate_dao_id,
                dao_level=int(dao_row.dao_level),
                claim_min_level=self._lord_cfg().claim_min_level,
                seat_occupied=seat_occupied,
            )
            # 本命须匹配该道才谈自动就任资格
            if claim_ok and dao_row.fate_dao_id != dao_id:
                claim_ok = False
                claim_reason = "本命道不符"
            # 对外：空位不展示「可夺位」按钮语义；仅提示自动就任条件
            can_claim_ui = False
            if not seat_occupied:
                if dao_row.fate_dao_id == dao_id and claim_ok:
                    claim_reason = "空位已自动就任（若仍虚位请刷新）"
                elif dao_row.fate_dao_id == dao_id:
                    pass  # 保留等级不足等文案
                else:
                    claim_reason = "空位：本命道达标者自动就任，无需夺位"
            chal_ok, chal_reason = can_challenge(
                fate_dao_id=dao_row.fate_dao_id,
                target_dao_id=dao_id,
                dao_level=int(dao_row.dao_level),
                challenge_min_level=self._lord_cfg().challenge_min_level,
                is_self_lord=is_self,
                cooldown_until=dao_row.challenge_cooldown_until,
                now=datetime.now(timezone.utc),
                window_open=bool(win["open"]),
                seat_occupied=seat_occupied,
            )
            seats.append(
                {
                    "dao_id": dao_id,
                    "dao_label": str(entry.get("label_zh") or dao_id),
                    "lord_character_id": lord_cid,
                    "lord_name": lord_name,
                    "claimed_at": claimed_at,
                    "can_claim": can_claim_ui,
                    "can_challenge": chal_ok,
                    "claim_block_reason": None if seat_occupied else claim_reason,
                    "challenge_block_reason": None if chal_ok else chal_reason,
                    "vacant": not seat_occupied,
                    "is_self_lord": is_self,
                },
            )
        payload: dict[str, Any] = {"seats": seats, "window": win}
        if auto:
            payload["auto_inaugurated"] = auto
        return payload

    async def try_auto_inaugurate(self, character: Character) -> dict[str, Any] | None:
        """
        空位且本命道达标 → 自动就任道主（无需手动夺位）。

        Args:
            character: 当前角色。

        Returns:
            就任摘要；不满足或已有道主则 None。
        """
        if not get_settings().dao_lord_enabled or not get_settings().dao_system_enabled:
            return None
        if character.status != "normal":
            return None
        dao_row = await self._dao._get_or_create_row(character.id)
        fate = dao_row.fate_dao_id
        if not fate:
            return None
        lord = await self._lordship(fate)
        ok, _reason = can_claim(
            fate_dao_id=fate,
            dao_level=int(dao_row.dao_level),
            claim_min_level=self._lord_cfg().claim_min_level,
            seat_occupied=lord is not None,
        )
        if not ok:
            return None
        return await self._inaugurate(character, fate)

    async def _inaugurate(self, character: Character, dao_id: str) -> dict[str, Any]:
        """写入道主席位（空位）。写入前再读一次，降低并发双写。"""
        existing = await self._lordship(dao_id)
        if existing is not None:
            if existing.character_id == character.id:
                return {
                    "dao_id": dao_id,
                    "dao_label": self._dao.label_of(dao_id),
                    "message": f"已是{self._dao.label_of(dao_id)}道主",
                    "auto": True,
                }
            raise AppError(
                code=40089,
                message="该道已有道主，请报名道主之争赛会更替",
                http_status=400,
            )
        priv = dict(self._lord_cfg().privileges_default)
        snap_id = await self._latest_snapshot_id(character.id)
        row = DaoLordship(
            dao_id=dao_id,
            character_id=character.id,
            snapshot_id=snap_id,
            privileges_json=json.dumps(priv, ensure_ascii=False),
        )
        self._session.add(row)
        await self._session.flush()
        logger.info(
            "dao lord auto inaugurated character_id=%s dao=%s",
            character.id,
            dao_id,
        )
        return {
            "dao_id": dao_id,
            "dao_label": self._dao.label_of(dao_id),
            "claimed_at": row.claimed_at.isoformat().replace("+00:00", "Z") if row.claimed_at else None,
            "privileges": priv,
            "message": f"空位自动就任：{self._dao.label_of(dao_id)}道主",
            "auto": True,
        }

    async def claim(self, user: User, *, dao_id: str | None = None) -> dict[str, Any]:
        """
        兼容旧客户端的就任入口；语义改为空位自动就任（与 try_auto 相同）。

        有道主时返回 40089，须走挑战。
        """
        self._require_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        if character.status != "normal":
            raise AppError(code=40060, message="当前状态不可就任道主", http_status=409)
        dao_row = await self._dao._get_or_create_row(character.id)
        target = dao_id or dao_row.fate_dao_id
        if not target or target != dao_row.fate_dao_id:
            raise AppError(code=40088, message="无资格：本命道不符", http_status=400)
        lord = await self._lordship(target)
        ok, reason = can_claim(
            fate_dao_id=dao_row.fate_dao_id,
            dao_level=int(dao_row.dao_level),
            claim_min_level=self._lord_cfg().claim_min_level,
            seat_occupied=lord is not None,
        )
        if not ok:
            code = 40089 if lord is not None else 40088
            raise AppError(code=code, message=reason or "不可就任", http_status=400)

        data = await self._inaugurate(character, target)
        from app.services.character_service import CharacterService

        public = await CharacterService(self._session).enrich_public(character)
        data["character"] = CharacterService.public_to_dict(public)
        data["seat"] = {
            "dao_id": target,
            "dao_label": self._dao.label_of(target),
            "lord_character_id": character.id,
            "lord_name": character.name,
            "claimed_at": data.get("claimed_at"),
            "can_claim": False,
            "can_challenge": False,
        }
        return data

    async def _latest_snapshot_id(self, character_id: int) -> int | None:
        """
        取角色防守快照引用键。

        DefenseSnapshot 以 ``character_id`` 为主键（无自增 id），
        故返回 character_id 供 ``session.get(DefenseSnapshot, key)``。
        """
        result = await self._session.execute(
            select(DefenseSnapshot)
            .where(DefenseSnapshot.character_id == character_id)
            .order_by(DefenseSnapshot.updated_at.desc())
            .limit(1),
        )
        snap = result.scalar_one_or_none()
        return int(snap.character_id) if snap else None

    async def clear_lordship_for_dao(
        self,
        dao_id: str,
        *,
        reason: str = "admin_remove",
    ) -> dict[str, Any]:
        """
        剔除某道现任道主，席位变为空缺（达标者可再自动就任）。

        遗留旧单挑会话（若有）一并强制结束为 abort，避免无主仍挂战。

        Args:
            dao_id: 大道 id。
            reason: 审计/日志原因键。

        Returns:
            剔除摘要；若本已空位则 ``removed=False``。

        Raises:
            AppError: 未知大道。
        """
        if dao_id not in get_game_config().dao.entries:
            raise AppError(code=40000, message="未知大道", http_status=400)
        # 清理遗留旧单挑会话后删席位
        aborted_challenge_id = await self._abort_legacy_challenge_sessions(
            dao_id,
            reason=reason,
        )
        lord = await self._lordship(dao_id)
        if lord is None:
            return {
                "dao_id": dao_id,
                "dao_label": self._dao.label_of(dao_id),
                "removed": False,
                "message": "该道本无道主（虚位）",
                "aborted_challenge_id": aborted_challenge_id,
            }
        former_character_id = int(lord.character_id)
        await self._session.delete(lord)
        await self._session.flush()
        logger.info(
            "dao lordship removed by ops dao=%s former_character_id=%s reason=%s",
            dao_id,
            former_character_id,
            reason,
        )
        return {
            "dao_id": dao_id,
            "dao_label": self._dao.label_of(dao_id),
            "removed": True,
            "former_character_id": former_character_id,
            "aborted_challenge_id": aborted_challenge_id,
            "message": f"已剔除{self._dao.label_of(dao_id)}道主，席位虚位以待",
        }

    async def list_lordships_board(self) -> list[dict[str, Any]]:
        """运营只读：各道现任道主一览（含虚位）。"""
        seats: list[dict[str, Any]] = []
        for dao_id, entry in get_game_config().dao.entries.items():
            lord = await self._lordship(dao_id)
            lord_name = None
            lord_cid = None
            claimed_at = None
            if lord:
                lord_cid = lord.character_id
                claimed_at = (
                    lord.claimed_at.isoformat().replace("+00:00", "Z")
                    if lord.claimed_at
                    else None
                )
                ch = await self._session.get(Character, lord.character_id)
                lord_name = ch.name if ch else None
            seats.append(
                {
                    "dao_id": dao_id,
                    "dao_label": str(entry.get("label_zh") or dao_id),
                    "lord_character_id": lord_cid,
                    "lord_name": lord_name,
                    "claimed_at": claimed_at,
                    "vacant": lord is None,
                },
            )
        return seats

    async def clear_lordship_for_character(self, character_id: int) -> list[str]:
        """轮回卸主：清空该角色所有道主席位。"""
        result = await self._session.execute(
            select(DaoLordship).where(DaoLordship.character_id == character_id),
        )
        rows = list(result.scalars().all())
        cleared = []
        for row in rows:
            cleared.append(row.dao_id)
            await self._session.delete(row)
        await self._session.flush()
        if cleared:
            logger.info("dao lordship cleared character_id=%s daos=%s", character_id, cleared)
        return cleared

    async def enrich_lord_summary(self, character: Character) -> dict[str, Any] | None:
        """CharacterPublic.dao_lord：仅当自己是某道道主。"""
        if not get_settings().dao_lord_enabled:
            return None
        result = await self._session.execute(
            select(DaoLordship).where(DaoLordship.character_id == character.id).limit(1),
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        priv = {}
        if row.privileges_json:
            try:
                priv = json.loads(row.privileges_json)
            except json.JSONDecodeError:
                priv = {}
        return {
            "dao_id": row.dao_id,
            "dao_label": self._dao.label_of(row.dao_id),
            "is_self": True,
            "privileges": priv,
        }

    async def gm_set_lord(self, character: Character, dao_id: str | None) -> dict[str, Any]:
        """GM：任命或清空道主。"""
        if dao_id is None:
            cleared = await self.clear_lordship_for_character(character.id)
            return {"cleared": cleared}
        if dao_id not in get_game_config().dao.entries:
            raise AppError(code=40000, message="未知大道", http_status=400)
        existing = await self._lordship(dao_id)
        priv = dict(self._lord_cfg().privileges_default)
        snap_id = await self._latest_snapshot_id(character.id)
        if existing:
            existing.character_id = character.id
            existing.snapshot_id = snap_id
            existing.privileges_json = json.dumps(priv, ensure_ascii=False)
            existing.claimed_at = datetime.now(timezone.utc)
        else:
            self._session.add(
                DaoLordship(
                    dao_id=dao_id,
                    character_id=character.id,
                    snapshot_id=snap_id,
                    privileges_json=json.dumps(priv, ensure_ascii=False),
                ),
            )
        await self._session.flush()
        return {"dao_id": dao_id, "character_id": character.id}
