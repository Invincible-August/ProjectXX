"""
突破领域：预览结构与进阶类型判定辅助（纯规则片段）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BreakthroughPreview:
    """突破只读预览结果。"""

    can_attempt: bool
    reason: str
    required_cultivation: int
    current_cultivation: int
    spirit_stone_cost: int
    success_rate: float
    advance_type: str | None
    next_realm_display: str | None
    grade_preview: str | None

    def to_dict(self) -> dict:
        """转为 API 兼容 dict。"""
        return {
            "can_attempt": self.can_attempt,
            "reason": self.reason,
            "required_cultivation": self.required_cultivation,
            "current_cultivation": self.current_cultivation,
            "spirit_stone_cost": self.spirit_stone_cost,
            "success_rate": self.success_rate,
            "advance_type": self.advance_type,
            "next_realm_display": self.next_realm_display,
            "grade_preview": self.grade_preview,
        }
