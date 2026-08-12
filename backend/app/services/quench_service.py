"""
炼体淬体应用服务（与修为突破分立；无渡劫，有成功率）。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import now_utc
from app.db.models import User
from app.domain.activity_mutex import Activity
from app.domain.body_temper import attempt_quench, quench_readiness
from app.schemas.common import AppError
from app.services.character_service import CharacterService
from app.services.idle_service import settle_idle
from app.services.play_gate import PlayGate

logger = logging.getLogger(__name__)


class QuenchService:
    """炼体淬体：预览与同步 attempt。"""

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: 请求级异步会话。
        """
        self._session = session
        self._characters = CharacterService(session)
        self._gate = PlayGate(session)

    async def preview_quench(self, user: User) -> dict[str, Any]:
        """
        淬体预览（先 settle 挂机再读进度 / 成功率）。

        Args:
            user: 当前用户。

        Returns:
            dict: 预览字段 + character。
        """
        character = await self._gate.require_character(user)
        await self._gate.resolve_pending_before_play(character)
        settle_idle(character)
        await self._session.flush()
        ready = quench_readiness(character)
        public = await self._characters.enrich_public(character)
        return {
            **ready,
            "character": CharacterService.public_to_dict(public),
        }

    async def attempt_quench(self, user: User) -> dict[str, Any]:
        """
        发起淬体：有成功率；失败回退进度仍返回结果（不抛 400）；条件不足才抛错。

        Args:
            user: 当前用户。

        Returns:
            dict: success / message / character / from/to / advance_type。

        Raises:
            AppError: 互斥阻断或条件不足（不可尝试）。
        """
        character = await self._gate.require_character(user)
        await self._gate.resolve_pending_before_play(character)
        settle_idle(character)
        await self._gate.assert_activity(character, Activity.QUENCH)

        ready = quench_readiness(character)
        if not ready.get("can_quench"):
            raise AppError(
                code=40080,
                message=str(ready.get("reason") or "不可淬体"),
                http_status=400,
            )

        result = attempt_quench(character)
        character.updated_at = now_utc()
        await self._session.flush()
        public = await self._characters.enrich_public(character)

        logger.info(
            "quench character_id=%s success=%s %s -> %s roll=%s",
            character.id,
            result.get("success"),
            result.get("from_display"),
            result.get("to_display"),
            result.get("rolled"),
        )
        return {
            "success": bool(result.get("success")),
            "message": result["message"],
            "advance_type": result.get("advance_type"),
            "success_rate": result.get("success_rate"),
            "from_stage": result.get("from_stage"),
            "from_stage_name": result.get("from_stage_name"),
            "from_display": result.get("from_display"),
            "to_stage": result.get("to_stage"),
            "to_stage_name": result.get("to_stage_name"),
            "to_display": result.get("to_display"),
            "needs_tribulation": False,
            "character": CharacterService.public_to_dict(public),
        }
