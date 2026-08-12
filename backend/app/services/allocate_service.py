"""
资源池手动分配到境界进度或功法等级（M2）。
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.character import Character
from app.db.models.technique import CharacterTechnique
from app.db.models.user import User
from app.schemas.common import AppError
from app.services import character_service
from app.services.play_gate import PlayGate
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)


class AllocateService:
    """
    Application service for manual resource pool allocation (M2).

    Supports allocating cultivation/body/crafting pools to realm progress or
    technique levels according to configured cost tables.

    Attributes:
        _session: Request-scoped async SQLAlchemy session.
        _gate: Cross-play precondition gate.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize allocate service dependencies.

        Args:
            session: Async SQLAlchemy session bound to the current request.
        """
        self._session = session
        self._gate = PlayGate(session)

    @staticmethod
    def _pool_for_track(character: Character, track: str) -> tuple[str, int]:
        """
        Resolve pool field name and balance for a technique track.

        Args:
            character: Character entity.
            track: Technique track key (``spirit`` / ``body`` / ``crafting``).

        Returns:
            tuple[str, int]: ORM field name and current balance.

        Raises:
            AppError: ``40033`` for unknown track.
        """
        if track == "spirit":
            return "cultivation_points", int(character.cultivation_points)
        if track == "body":
            return "body_tempering_points", int(character.body_tempering_points)
        if track == "crafting":
            return "crafting_exp", int(character.crafting_exp)
        raise AppError(code=40033, message="未知功法 track", http_status=400)

    async def allocate_resources(
        self,
        user: User,
        *,
        target_type: str,
        target_id: str | None,
        amount: int,
    ) -> dict:
        """
        Allocate pool resources to realm progress or technique levels.

        Args:
            user: Authenticated user.
            target_type: ``realm`` or ``technique``.
            target_id: Technique id when target_type is ``technique``; optional for realm.
            amount: Points to invest (must meet minimum unit).

        Returns:
            dict: allocated, levels_gained, message, character.

        Raises:
            AppError: ``40032`` insufficient pool; ``40033`` invalid target.
        """
        min_unit = get_settings().allocate_min_unit
        if amount < min_unit or amount != int(amount):
            raise AppError(code=40032, message="分配数量须为正整数", http_status=400)

        character = await self._gate.require_character(user)
        auto_claimed = await self._gate.resolve_pending_before_play(character)

        if target_type == "realm":
            if int(character.cultivation_points) < amount:
                raise AppError(code=40032, message="修为池不足", http_status=400)
            character.cultivation_points = int(character.cultivation_points) - amount
            character.realm_progress = int(character.realm_progress) + amount
            message = f"已向境界进度投入 {amount} 点修为"
            levels_gained = 0
            allocated = amount
        elif target_type == "technique":
            if not target_id:
                raise AppError(code=40033, message="须指定功法 id", http_status=400)
            cfg = get_game_config()
            tech_cfg = cfg.techniques.get(target_id)
            if tech_cfg is None:
                raise AppError(code=40033, message="功法不存在", http_status=400)

            result = await self._session.execute(
                select(CharacterTechnique).where(
                    CharacterTechnique.character_id == character.id,
                    CharacterTechnique.technique_id == target_id,
                ),
            )
            row = result.scalar_one_or_none()
            if row is None:
                raise AppError(code=40033, message="功法未解锁", http_status=400)
            if row.level >= tech_cfg.max_level:
                raise AppError(code=40033, message="功法已满级", http_status=400)

            pool_field, pool_balance = self._pool_for_track(character, tech_cfg.track)
            if pool_balance < amount:
                raise AppError(code=40032, message="对应资源池不足", http_status=400)

            remaining = amount
            levels_gained = 0
            while remaining > 0 and row.level < tech_cfg.max_level:
                cost_index = row.level
                if cost_index >= len(tech_cfg.cost_per_level):
                    break
                level_cost = tech_cfg.cost_per_level[cost_index]
                if remaining < level_cost:
                    break
                remaining -= level_cost
                row.level += 1
                levels_gained += 1

            spent = amount - remaining
            if spent <= 0:
                raise AppError(
                    code=40032,
                    message="投入点数不足以升级（请按 cost_per_level 投入）",
                    http_status=400,
                )

            setattr(character, pool_field, pool_balance - spent)
            allocated = spent
            if levels_gained > 0:
                message = f"{tech_cfg.name} 升至 {row.level} 级"
            else:
                message = f"已向 {tech_cfg.name} 投入 {spent} 点（未升级）"
        else:
            raise AppError(code=40000, message="无效分配目标类型", http_status=400)

        await self._session.flush()
        await self._session.refresh(character)
        logger.info(
            "allocate character_id=%s target=%s/%s amount=%s levels=%s",
            character.id,
            target_type,
            target_id,
            amount,
            levels_gained if target_type == "technique" else 0,
        )

        public = await character_service.enrich_character_public(self._session, character)
        payload: dict = {
            "allocated": allocated,
            "levels_gained": levels_gained if target_type == "technique" else 0,
            "message": message,
            "character": character_service.character_public_to_dict(public),
        }
        if auto_claimed is not None:
            payload["auto_claimed_offline"] = auto_claimed
        return payload


# ---------------------------------------------------------------------------
# Module-level wrappers (backward-compatible for tests and legacy imports)
# ---------------------------------------------------------------------------


async def allocate_resources(
    session: AsyncSession,
    user: User,
    *,
    target_type: str,
    target_id: str | None,
    amount: int,
) -> dict:
    """Module wrapper delegating to ``AllocateService.allocate_resources``."""
    return await AllocateService(session).allocate_resources(
        user,
        target_type=target_type,
        target_id=target_id,
        amount=amount,
    )
