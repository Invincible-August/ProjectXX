"""
战力领域：境界底 × 品阶倍 × 功法/体质加算。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CombatStats:
    """最终战力与面板摘要组件。"""

    atk: int
    hp: int


class CombatCalculator:
    """
    战力纯计算器（无 DB IO）。

    调用方负责查询品阶倍率与功法/体质加算后再传入。
    """

    @staticmethod
    def compute(
        *,
        base_atk: int,
        base_hp: int,
        grade_atk_mul: float = 1.0,
        grade_hp_mul: float = 1.0,
        technique_atk: int = 0,
        technique_hp: int = 0,
        constitution_atk: int = 0,
        constitution_hp: int = 0,
    ) -> CombatStats:
        """
        计算含品阶/功法/体质修正后的 atk/hp。

        品阶倍率先作用于境界底数，再叠加算。

        Args:
            base_atk: 境界基础攻击。
            base_hp: 境界基础生命。
            grade_atk_mul: 品阶攻击倍率。
            grade_hp_mul: 品阶生命倍率。
            technique_atk: 功法攻击加算。
            technique_hp: 功法生命加算。
            constitution_atk: 体质攻击加算。
            constitution_hp: 体质生命加算。

        Returns:
            CombatStats: 最终 atk / hp。
        """
        graded_atk = int(base_atk * grade_atk_mul)
        graded_hp = int(base_hp * grade_hp_mul)
        return CombatStats(
            atk=graded_atk + technique_atk + constitution_atk,
            hp=graded_hp + technique_hp + constitution_hp,
        )
