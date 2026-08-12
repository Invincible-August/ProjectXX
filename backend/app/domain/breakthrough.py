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
    advance_type_label_zh: str | None = None

    def to_dict(self) -> dict:
        """转为 API 兼容 dict。"""
        from app.domain.display_labels import ADVANCE_TYPE_LABEL_ZH

        type_zh = self.advance_type_label_zh
        if type_zh is None and self.advance_type:
            type_zh = ADVANCE_TYPE_LABEL_ZH.get(self.advance_type)
        return {
            "can_attempt": self.can_attempt,
            "reason": self.reason,
            "required_cultivation": self.required_cultivation,
            "current_cultivation": self.current_cultivation,
            "spirit_stone_cost": self.spirit_stone_cost,
            "success_rate": self.success_rate,
            "advance_type": self.advance_type,
            "advance_type_label_zh": type_zh,
            "next_realm_display": self.next_realm_display,
            "grade_preview": self.grade_preview,
        }
