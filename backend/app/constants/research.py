"""
Research session protocol constants (M8 R2).
"""

from __future__ import annotations

from typing import Final

RESEARCH_KIND_TECHNIQUE: Final[str] = "technique"
RESEARCH_KIND_FORMATION: Final[str] = "formation"
RESEARCH_KIND_TALISMAN: Final[str] = "talisman"

RESEARCH_KINDS: Final[tuple[str, ...]] = (
    RESEARCH_KIND_TECHNIQUE,
    RESEARCH_KIND_FORMATION,
    RESEARCH_KIND_TALISMAN,
)

RESEARCH_KIND_LABELS_ZH: Final[dict[str, str]] = {
    RESEARCH_KIND_TECHNIQUE: "功法",
    RESEARCH_KIND_FORMATION: "阵法",
    RESEARCH_KIND_TALISMAN: "符箓",
}

RESEARCH_PHASE_DRAFTING: Final[str] = "drafting"
RESEARCH_PHASE_PREVIEWED: Final[str] = "previewed"
RESEARCH_PHASE_FINALIZED: Final[str] = "finalized"
RESEARCH_PHASE_CANCELLED: Final[str] = "cancelled"
RESEARCH_PHASE_EXPIRED: Final[str] = "expired"

RESEARCH_PHASE_LABELS_ZH: Final[dict[str, str]] = {
    RESEARCH_PHASE_DRAFTING: "起草",
    RESEARCH_PHASE_PREVIEWED: "已预览",
    RESEARCH_PHASE_FINALIZED: "已定稿",
    RESEARCH_PHASE_CANCELLED: "已取消",
    RESEARCH_PHASE_EXPIRED: "已过期",
}

RESEARCH_SOURCE_CUSTOM: Final[str] = "custom"
RESEARCH_SOURCE_OFFICIAL: Final[str] = "official"
SOURCE_LABEL_CUSTOM_ZH: Final[str] = "自研"
SOURCE_LABEL_OFFICIAL_ZH: Final[str] = "官方样本"

PRIVATE_ID_PREFIX: Final[str] = "custom"

DICE_PURPOSE_RESEARCH_TECHNIQUE: Final[str] = "research_technique"
DICE_PURPOSE_RESEARCH_FORMATION: Final[str] = "research_formation"
DICE_PURPOSE_RESEARCH_TALISMAN: Final[str] = "research_talisman"

ERR_RESEARCH_MATERIALS: Final[int] = 40200
ERR_RESEARCH_SESSION: Final[int] = 40201
ERR_RESEARCH_VALIDATE: Final[int] = 40202
ERR_RESEARCH_THRESHOLD: Final[int] = 40203
ERR_RESEARCH_WHITELIST: Final[int] = 40204
ERR_RESEARCH_FROZEN: Final[int] = 40206
ERR_RESEARCH_OWNER: Final[int] = 40207
ERR_RESEARCH_AFFIX_SLOTS: Final[int] = 40208
ERR_RESEARCH_REVIEW_CLOSED: Final[int] = 40210
ERR_RESEARCH_MUTEX: Final[int] = 40211

TALISMAN_TRIGGER_FIRST_HIT: Final[str] = "first_hit"
TALISMAN_TRIGGER_BATTLE_START: Final[str] = "battle_start"
TALISMAN_TRIGGER_ON_ATTACK: Final[str] = "on_attack"
TALISMAN_TRIGGERS: Final[frozenset[str]] = frozenset(
    {
        TALISMAN_TRIGGER_FIRST_HIT,
        TALISMAN_TRIGGER_BATTLE_START,
        TALISMAN_TRIGGER_ON_ATTACK,
    },
)

# 符箓效果功能类（talisman_effects.kind；工坊筛选镜像）
TALISMAN_KIND_BUFF: Final[str] = "buff"  # 增益
TALISMAN_KIND_OFFENSIVE: Final[str] = "offensive"  # 攻击
TALISMAN_KIND_CURSE: Final[str] = "curse"  # 诅咒
TALISMAN_KINDS: Final[frozenset[str]] = frozenset(
    {
        TALISMAN_KIND_BUFF,
        TALISMAN_KIND_OFFENSIVE,
        TALISMAN_KIND_CURSE,
    },
)
TALISMAN_KIND_LABELS_ZH: Final[dict[str, str]] = {
    TALISMAN_KIND_BUFF: "增益",
    TALISMAN_KIND_OFFENSIVE: "攻击",
    TALISMAN_KIND_CURSE: "诅咒",
}
