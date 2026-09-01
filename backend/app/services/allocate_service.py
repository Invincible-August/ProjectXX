"""
资源池手动分配到境界进度或功法等级（M2）。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.character import Character
from app.db.models.research import PrivateTechnique
from app.db.models.technique import CharacterTechnique
from app.db.models.user import User
from app.domain.technique_craft import CULTIVABLE_MAX_LEVEL
from app.schemas.common import AppError
from app.services import character_service
from app.services.play_gate import PlayGate
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _TechniqueAllocateTarget:
    """Resolved allocate target for catalog or private cultivable techniques."""

    name: str
    track: str
    cultivable: bool
    cost_per_level: tuple[int, ...]
    perfection_cost: int
    max_level: int


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

    async def _resolve_technique_target(
        self,
        character: Character,
        target_id: str,
    ) -> _TechniqueAllocateTarget:
        """
        Resolve catalog or private technique allocate rules.

        Raises:
            AppError: ``40033`` if technique is missing or not owned.
        """
        cfg = get_game_config()
        tech_cfg = cfg.techniques.get(target_id)
        if tech_cfg is not None:
            return _TechniqueAllocateTarget(
                name=tech_cfg.name,
                track=tech_cfg.track,
                cultivable=bool(tech_cfg.cultivable),
                cost_per_level=tuple(int(x) for x in tech_cfg.cost_per_level),
                perfection_cost=int(tech_cfg.perfection_cost or 0),
                max_level=int(tech_cfg.max_level),
            )

        result = await self._session.execute(
            select(PrivateTechnique).where(
                PrivateTechnique.character_id == character.id,
                PrivateTechnique.technique_id == target_id,
            ).limit(1),
        )
        private = result.scalar_one_or_none()
        if private is None:
            raise AppError(code=40033, message="功法不存在", http_status=400)
        payload: dict[str, Any] = {}
        try:
            raw = json.loads(private.payload_json or "{}")
            if isinstance(raw, dict):
                payload = raw
        except json.JSONDecodeError:
            payload = {}
        craft = cfg.research.technique_craft
        tech_branch = cfg.research.technique
        cultivable = bool(
            payload["cultivable"]
            if "cultivable" in payload
            else craft.default_cultivable
        )
        costs = tuple(int(x) for x in tech_branch.cost_per_level)
        perfection = int(
            payload.get("perfection_cost")
            if payload.get("perfection_cost") is not None
            else (
                tech_branch.perfection_cost
                or craft.perfection_cost
                or 0
            )
        )
        return _TechniqueAllocateTarget(
            name=str(private.label_zh),
            track=str(private.track or tech_branch.track or "spirit"),
            cultivable=cultivable,
            cost_per_level=costs,
            perfection_cost=perfection,
            max_level=CULTIVABLE_MAX_LEVEL,
        )

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
        elif target_type == "body_temper":
            from app.domain.body_temper import apply_body_temper_progress

            pool = int(character.body_tempering_points)
            if pool < amount:
                raise AppError(code=40032, message="淬体度池不足", http_status=400)
            apply_body_temper_progress(character, amount)
            character.body_tempering_points = pool - amount
            allocated = amount
            levels_gained = 0
            message = f"已向淬体进度投入 {amount} 点淬体度"
        elif target_type == "technique":
            if not target_id:
                raise AppError(code=40033, message="须指定功法 id", http_status=400)
            target = await self._resolve_technique_target(character, target_id)
            if not target.cultivable:
                raise AppError(code=40033, message="该功法不可修炼", http_status=400)

            result = await self._session.execute(
                select(CharacterTechnique).where(
                    CharacterTechnique.character_id == character.id,
                    CharacterTechnique.technique_id == target_id,
                ),
            )
            row = result.scalar_one_or_none()
            if row is None:
                raise AppError(code=40033, message="功法未解锁", http_status=400)
            if bool(getattr(row, "perfected", False)):
                raise AppError(code=40033, message="已大圆满", http_status=400)

            pool_field, pool_balance = self._pool_for_track(character, target.track)
            pool_label = {
                "spirit": "修为池",
                "body": "淬体度池",
                "crafting": "制造业经验池",
            }.get(target.track, "资源池")
            if pool_balance < amount:
                raise AppError(
                    code=40032,
                    message=f"{pool_label}不足",
                    http_status=400,
                )

            remaining = amount
            levels_gained = 0
            perfected_now = False
            layer_cap = min(int(target.max_level), CULTIVABLE_MAX_LEVEL)

            while remaining > 0:
                if bool(getattr(row, "perfected", False)):
                    break
                if int(row.level) < layer_cap:
                    cost_index = int(row.level)
                    if cost_index >= len(target.cost_per_level):
                        break
                    level_cost = int(target.cost_per_level[cost_index])
                    if remaining < level_cost:
                        break
                    remaining -= level_cost
                    row.level = int(row.level) + 1
                    levels_gained += 1
                    continue
                # level == layer_cap：下一投入走大圆满
                perf_cost = int(target.perfection_cost or 0)
                if perf_cost <= 0 or remaining < perf_cost:
                    break
                remaining -= perf_cost
                row.perfected = True
                perfected_now = True
                levels_gained += 1
                break

            spent = amount - remaining
            if spent <= 0:
                raise AppError(
                    code=40032,
                    message="投入点数不足以升级（请按 cost_per_level / 大圆满消耗投入）",
                    http_status=400,
                )

            setattr(character, pool_field, pool_balance - spent)
            allocated = spent
            if perfected_now:
                message = f"{target.name} 已大圆满（扣{pool_label}）"
            elif levels_gained > 0:
                message = f"{target.name} 升至 {row.level} 层（扣{pool_label}）"
            else:
                message = f"已向 {target.name} 投入 {spent} 点（未升级，扣{pool_label}）"
        else:
            raise AppError(
                code=40000,
                message="无效分配目标类型（realm|body_temper|technique）",
                http_status=400,
            )

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


async def allocate_resources(
    session: AsyncSession,
    user: User,
    *,
    target_type: str,
    target_id: str | None,
    amount: int,
) -> dict:
    """Module wrapper for tests and legacy callers."""
    return await AllocateService(session).allocate_resources(
        user,
        target_type=target_type,
        target_id=target_id,
        amount=amount,
    )
