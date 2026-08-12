"""
修为骰子应用服务：聚合角色境界/功法/气运等，解析区间并掷骰。

权威入口；突破与战斗组装应调用本服务，禁止散落裸 random。
"""

from __future__ import annotations

import logging
import random
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.character import Character
from app.db.models.technique import CharacterTechnique
from app.domain.dice_rules import (
    DiceBounds,
    DiceModContribution,
    body_realm_mod,
    breakthrough_success,
    chance,
    damage_dice_factor,
    fate_luck_mod,
    lookup_realm_bounds,
    resolve_bounds,
    roll_bounds,
    technique_mod_for_level,
    weighted_pick,
)
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)


class DiceService:
    """
    修为骰子用例：解析 bounds、掷骰、概率/权重门面。

    属性:
        _session: 异步会话（加载功法等级等）。
    """

    def __init__(self, session: AsyncSession | None = None) -> None:
        """
        参数:
            session: 可选；无会话时只能做纯配置解析（怪默认等）。
        """
        self._session = session

    @staticmethod
    def make_rng(seed: int | None = None) -> random.Random:
        """
        构造可注入随机源。

        参数:
            seed: 可选种子；None 则非确定。

        返回:
            Random 实例。
        """
        if seed is not None:
            return random.Random(int(seed))
        return random.Random()

    def monster_bounds(self, *, purpose: str = "combat_damage") -> DiceBounds:
        """
        怪物默认区间（无角色上下文）。

        参数:
            purpose: 用途。

        返回:
            DiceBounds。
        """
        dice = get_game_config().dice
        return resolve_bounds(
            purpose=purpose,
            base_min=dice.monster_min,
            base_max=dice.monster_max,
            contributions=(),
            absolute_min=dice.absolute_min,
            absolute_max=dice.absolute_max,
        )

    def bounds_for_realm(
        self,
        *,
        major_realm: str,
        stage: int,
        purpose: str = "generic",
        contributions: Sequence[DiceModContribution] = (),
    ) -> DiceBounds:
        """
        仅按境界查表 + 外部传入修正（同步、无 DB）。

        参数:
            major_realm: 大境界。
            stage: 小境界。
            purpose: 用途。
            contributions: 额外修正。

        返回:
            DiceBounds。
        """
        dice = get_game_config().dice
        base_min, base_max = lookup_realm_bounds(
            dice.realm_bounds,
            major_realm=major_realm,
            stage=stage,
            fallback_min=dice.fallback_min,
            fallback_max=dice.fallback_max,
        )
        return resolve_bounds(
            purpose=purpose,
            base_min=base_min,
            base_max=base_max,
            contributions=contributions,
            absolute_min=dice.absolute_min,
            absolute_max=dice.absolute_max,
        )

    async def resolve_for_character(
        self,
        character: Character,
        *,
        purpose: str = "generic",
        include_body_track: bool | None = None,
    ) -> DiceBounds:
        """
        解析角色实际掷骰区间（含功法/体修/气运）。

        参数:
            character: 角色行。
            purpose: 用途。
            include_body_track: 是否叠体修道修正；None 时对 body 相关 purpose 自动 True。

        返回:
            DiceBounds。
        """
        dice = get_game_config().dice
        techniques_cfg = get_game_config().techniques
        major = str(character.major_realm)
        stage = int(character.realm_stage)

        base_min, base_max = lookup_realm_bounds(
            dice.realm_bounds,
            major_realm=major,
            stage=stage,
            fallback_min=dice.fallback_min,
            fallback_max=dice.fallback_max,
        )

        contributions: list[DiceModContribution] = []

        # —— 功法通道 ——
        if dice.channel_enabled("technique") and self._session is not None:
            rows = (
                await self._session.execute(
                    select(CharacterTechnique).where(
                        CharacterTechnique.character_id == character.id,
                    ),
                )
            ).scalars().all()
            for row in rows:
                tech = techniques_cfg.get(str(row.technique_id))
                if tech is None or not tech.dice_mods:
                    continue
                level = int(row.level)
                min_b, max_b = technique_mod_for_level(tech.dice_mods, level)
                if min_b == 0 and max_b == 0:
                    continue
                contributions.append(
                    DiceModContribution(
                        source="technique",
                        id=tech.technique_id,
                        label=f"{tech.name}·{level}级",
                        min_bonus=min_b,
                        max_bonus=max_b,
                    ),
                )

        # —— 体修道通道 ——
        apply_body = include_body_track
        if apply_body is None:
            apply_body = purpose in (
                "combat_initiative",
                "combat_damage",
                "formation",
                "breakthrough",
                "generic",
            )
        if apply_body and dice.channel_enabled("body_track"):
            # 体修功法修正已在 technique 通道计入；此处加 body_realm_bonus
            min_b, max_b = body_realm_mod(
                dice.body_realm_bonus,
                major_realm=major,
                stage=stage,
            )
            if min_b or max_b:
                contributions.append(
                    DiceModContribution(
                        source="body_track",
                        id=f"{major}:{stage}",
                        label="体修境界附加",
                        min_bonus=min_b,
                        max_bonus=max_b,
                    ),
                )

        # —— 气运 ——
        if dice.channel_enabled("fate_luck"):
            luck = int(getattr(character, "fate_luck", 0) or 0)
            min_b, max_b = fate_luck_mod(dice.fate_luck_tiers, luck)
            if min_b or max_b:
                contributions.append(
                    DiceModContribution(
                        source="fate_luck",
                        id=str(luck),
                        label=f"气运{luck}",
                        min_bonus=min_b,
                        max_bonus=max_b,
                    ),
                )

        # item / equipment 通道本期无实例（enabled=false）

        bounds = resolve_bounds(
            purpose=purpose,
            base_min=base_min,
            base_max=base_max,
            contributions=contributions,
            absolute_min=dice.absolute_min,
            absolute_max=dice.absolute_max,
        )
        logger.debug(
            "dice_bounds character_id=%s purpose=%s lo=%s hi=%s base=%s-%s",
            character.id,
            purpose,
            bounds.lo,
            bounds.hi,
            bounds.base_min,
            bounds.base_max,
        )
        return bounds

    async def roll_for_character(
        self,
        character: Character,
        *,
        purpose: str,
        rng: random.Random | None = None,
    ) -> tuple[int, DiceBounds]:
        """
        解析区间并掷一骰。

        参数:
            character: 角色。
            purpose: 用途。
            rng: 可选随机源。

        返回:
            (出目, bounds)。
        """
        bounds = await self.resolve_for_character(character, purpose=purpose)
        value = roll_bounds(bounds, rng=rng)
        return value, bounds

    async def roll_breakthrough(
        self,
        character: Character,
        *,
        success_rate: float,
        rng: random.Random | None = None,
    ) -> dict[str, Any]:
        """
        突破检定：掷区间骰并与 success_rate 映射阈值比较。

        参数:
            character: 角色。
            success_rate: breakthrough.yaml 成功率。
            rng: 可选随机源。

        返回:
            dict: success / roll / threshold / lo / hi / bounds 摘要。
        """
        dice_cfg = get_game_config().dice
        roll_value, bounds = await self.roll_for_character(
            character,
            purpose="breakthrough",
            rng=rng,
        )
        if dice_cfg.use_legacy_success_rate:
            ok, threshold = breakthrough_success(
                roll_value,
                bounds.lo,
                bounds.hi,
                success_rate,
            )
        else:
            # 无映射时：掷到上半区算成功（占位）
            threshold = bounds.lo + (bounds.span + 1) // 2
            ok = roll_value >= threshold
        return {
            "success": ok,
            "roll": roll_value,
            "threshold": threshold,
            "lo": bounds.lo,
            "hi": bounds.hi,
            "base_min": bounds.base_min,
            "base_max": bounds.base_max,
            "success_rate": float(success_rate),
        }

    @staticmethod
    def chance(probability: float, *, rng: random.Random | None = None) -> bool:
        """伯努利门面。"""
        return chance(probability, rng=rng)

    @staticmethod
    def weighted_pick(
        weights: dict[str, float | int],
        *,
        rng: random.Random | None = None,
    ) -> str | None:
        """权重抽取门面。"""
        return weighted_pick(weights, rng=rng)

    @staticmethod
    def unit_dice_payload(bounds: DiceBounds) -> dict[str, int]:
        """
        写入战斗单位的 dice_lo / dice_hi。

        参数:
            bounds: 已解析区间。

        返回:
            dict。
        """
        return {"dice_lo": int(bounds.lo), "dice_hi": int(bounds.hi)}

    @staticmethod
    def damage_factor(roll: int, bounds: DiceBounds, *, legacy_normalizer: float = 10.0) -> float:
        """伤害因子。"""
        dice = get_game_config().dice
        return damage_dice_factor(
            roll,
            bounds,
            use_midpoint=dice.use_midpoint_normalizer,
            legacy_normalizer=legacy_normalizer,
        )
