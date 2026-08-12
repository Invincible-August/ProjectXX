"""
跨境品阶掷骰与槽位推导（M2）。

品阶权重可读体质镶嵌修正；测试可通过 ``GRADE_RNG_SEED`` 注入。
"""

from __future__ import annotations

import logging
import random
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.breakthrough_grade import BreakthroughGradeHistory
from app.db.models.character import Character
from app.db.models.constitution import ConstitutionItem, ConstitutionSlot
from app.services.realm_config import GradeConfig, GradesConfig, get_game_config

logger = logging.getLogger(__name__)

# 良品及以上品阶 id（权重修正目标）
_GOOD_PLUS_GRADES = frozenset({"good", "superior", "peerless", "immortal", "heavenly"})


class GradeService:
    """
    Application service for cross-realm breakthrough grade rolling and history.

    Aggregates constitution bonuses, adjusts grade weights, rolls outcomes,
    and persists grade history rows.

    Attributes:
        _session: Request-scoped async SQLAlchemy session.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize grade service with a database session.

        Args:
            session: Async SQLAlchemy session bound to the current request.
        """
        self._session = session

    @staticmethod
    def _rng() -> random.Random:
        """
        Construct grade RNG; tests may inject seed via ``GRADE_RNG_SEED``.

        Returns:
            random.Random: Isolated RNG instance.
        """
        settings = get_settings()
        if settings.grade_rng_seed is not None:
            return random.Random(settings.grade_rng_seed)
        return random.Random()

    @staticmethod
    def grade_name_map() -> dict[str, str]:
        """
        Build grade id to localized display name mapping.

        Returns:
            dict[str, str]: e.g. ``{"mortal": "凡品"}``.
        """
        cfg = get_game_config().grades
        return {item.grade_id: item.name for item in cfg.grades}

    @staticmethod
    def get_grade_config(grade_id: str) -> GradeConfig | None:
        """
        Look up grade configuration by id.

        Args:
            grade_id: Grade identifier from game config.

        Returns:
            GradeConfig | None: Matching config or None if unknown.
        """
        return get_game_config().grades.grade_by_id(grade_id)

    async def aggregate_constitution_bonuses(
        self,
        character_id: int,
    ) -> dict[str, Any]:
        """
        Aggregate equipped constitution bonuses affecting grade weights and combat.

        Args:
            character_id: Character primary key.

        Returns:
            dict: ``main_affix_count``, ``vitality``, ``atk_bonus``, ``hp_bonus``, etc.
        """
        cfg = get_game_config()
        result = await self._session.execute(
            select(ConstitutionSlot, ConstitutionItem)
            .outerjoin(
                ConstitutionItem,
                ConstitutionSlot.item_instance_id == ConstitutionItem.id,
            )
            .where(ConstitutionSlot.character_id == character_id),
        )
        main_affix_count = 0
        vitality = 0
        atk_bonus = 0
        hp_bonus = 0
        for slot, item in result.all():
            if item is None:
                continue
            item_def = cfg.constitution.items.get(item.def_id)
            if item_def is None:
                continue
            if item_def.kind == "main":
                main_affix_count += 1
            for key, value in item_def.base_attrs.items():
                if key == "vitality":
                    vitality += int(value)
            for key, value in item_def.effects.items():
                if key == "atk_bonus":
                    atk_bonus += int(value)
                elif key == "hp_bonus":
                    hp_bonus += int(value)

        return {
            "main_affix_count": main_affix_count,
            "vitality": vitality,
            "atk_bonus": atk_bonus,
            "hp_bonus": hp_bonus,
        }

    @staticmethod
    def _build_adjusted_weights(
        grades_cfg: GradesConfig,
        constitution_bonus: dict[str, Any],
    ) -> list[tuple[GradeConfig, float]]:
        """
        Build weighted grade list with constitution placeholder adjustments.

        Args:
            grades_cfg: Global grades configuration.
            constitution_bonus: Output of ``aggregate_constitution_bonuses``.

        Returns:
            list[tuple[GradeConfig, float]]: Grade config paired with effective weight.
        """
        main_count = int(constitution_bonus.get("main_affix_count", 0))
        vitality = int(constitution_bonus.get("vitality", 0))
        extra = (
            main_count * grades_cfg.per_main_affix_bonus
            + vitality * grades_cfg.per_base_attr_point_bonus
        )
        weighted: list[tuple[GradeConfig, float]] = []
        for grade in grades_cfg.grades:
            weight = float(grade.weight)
            if grade.grade_id in _GOOD_PLUS_GRADES and extra > 0:
                weight += extra
            weighted.append((grade, weight))
        return weighted

    @staticmethod
    def roll_grade_with_weights(
        weighted: list[tuple[GradeConfig, float]],
        rng: random.Random | None = None,
    ) -> GradeConfig:
        """
        Roll a grade by weighted random selection.

        Args:
            weighted: Grade config and weight pairs.
            rng: Optional RNG; uses seeded instance when None.

        Returns:
            GradeConfig: Selected grade configuration.
        """
        roll_rng = rng or GradeService._rng()
        # 权重抽取走修为骰子系统门面（语义仍为权重抽，非区间骰）
        from app.domain.dice_rules import weighted_pick

        weight_map = {g.grade_id: float(w) for g, w in weighted}
        picked_id = weighted_pick(weight_map, rng=roll_rng)
        if picked_id is None:
            return weighted[0][0]
        for grade, _weight in weighted:
            if grade.grade_id == picked_id:
                return grade
        return weighted[-1][0]

    async def roll_breakthrough_grade(
        self,
        character: Character,
    ) -> GradeConfig:
        """
        Roll breakthrough grade for a successful major-realm advance.

        Args:
            character: Character entity (used for constitution bonus lookup).

        Returns:
            GradeConfig: Rolled grade configuration.
        """
        grades_cfg = get_game_config().grades
        bonus = await self.aggregate_constitution_bonuses(character.id)
        weighted = self._build_adjusted_weights(grades_cfg, bonus)
        grade = self.roll_grade_with_weights(weighted)
        logger.info(
            "grade rolled character_id=%s grade=%s main_affix=%s vitality=%s",
            character.id,
            grade.grade_id,
            bonus.get("main_affix_count"),
            bonus.get("vitality"),
        )
        return grade

    async def write_grade_history(
        self,
        character: Character,
        *,
        from_display: str,
        to_display: str,
        grade_id: str,
    ) -> BreakthroughGradeHistory:
        """
        Persist a cross-realm grade history row.

        Args:
            character: Character entity.
            from_display: Pre-breakthrough realm display string.
            to_display: Post-breakthrough realm display string.
            grade_id: Rolled grade identifier.

        Returns:
            BreakthroughGradeHistory: Newly created history row.
        """
        row = BreakthroughGradeHistory(
            character_id=character.id,
            from_realm_display=from_display,
            to_realm_display=to_display,
            grade=grade_id,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    @staticmethod
    def grade_preview_text() -> str:
        """
        Build preview text explaining grade weight rules (no pre-roll).

        Returns:
            str: Brief Chinese explanation for UI preview.
        """
        names = [g.name for g in get_game_config().grades.grades]
        return f"跨境成功将按配置权重掷出品阶（{' / '.join(names)}）；镶嵌主词条可提升高品阶概率。"


# ---------------------------------------------------------------------------
# Module-level wrappers (backward-compatible for tests and legacy imports)
# ---------------------------------------------------------------------------


def grade_name_map() -> dict[str, str]:
    """Module wrapper delegating to ``GradeService.grade_name_map``."""
    return GradeService.grade_name_map()


def get_grade_config(grade_id: str) -> GradeConfig | None:
    """Module wrapper delegating to ``GradeService.get_grade_config``."""
    return GradeService.get_grade_config(grade_id)


def _build_adjusted_weights(
    grades_cfg: GradesConfig,
    constitution_bonus: dict[str, Any],
) -> list[tuple[GradeConfig, float]]:
    """Module wrapper for tests/legacy: ``GradeService._build_adjusted_weights``."""
    return GradeService._build_adjusted_weights(grades_cfg, constitution_bonus)


async def aggregate_constitution_bonuses(
    session: AsyncSession,
    character_id: int,
) -> dict[str, Any]:
    """Module wrapper delegating to ``GradeService.aggregate_constitution_bonuses``."""
    return await GradeService(session).aggregate_constitution_bonuses(character_id)


def roll_grade_with_weights(
    weighted: list[tuple[GradeConfig, float]],
    rng: random.Random | None = None,
) -> GradeConfig:
    """Module wrapper delegating to ``GradeService.roll_grade_with_weights``."""
    return GradeService.roll_grade_with_weights(weighted, rng=rng)


async def roll_breakthrough_grade(
    session: AsyncSession,
    character: Character,
) -> GradeConfig:
    """Module wrapper delegating to ``GradeService.roll_breakthrough_grade``."""
    return await GradeService(session).roll_breakthrough_grade(character)


async def write_grade_history(
    session: AsyncSession,
    character: Character,
    *,
    from_display: str,
    to_display: str,
    grade_id: str,
) -> BreakthroughGradeHistory:
    """Module wrapper delegating to ``GradeService.write_grade_history``."""
    return await GradeService(session).write_grade_history(
        character,
        from_display=from_display,
        to_display=to_display,
        grade_id=grade_id,
    )


def grade_preview_text() -> str:
    """Module wrapper delegating to ``GradeService.grade_preview_text``."""
    return GradeService.grade_preview_text()
