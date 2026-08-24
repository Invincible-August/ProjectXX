"""战斗异常 / 诅咒协议常量（设计冻结；引擎完整链仍挂 M3-D03）。"""

from __future__ import annotations

from typing import Final

STATUS_POISON: Final[str] = "poison"  # 中毒：回合伤害
STATUS_BURN: Final[str] = "burn"  # 灼烧：回合伤害
STATUS_DROWN: Final[str] = "drown"  # 溺水：异常；回合细则待战斗专栏
STATUS_PARALYZE: Final[str] = "paralyze"  # 麻痹：异常；回合细则待战斗专栏
STATUS_ATK_DOWN: Final[str] = "atk_down"  # 减攻：诅咒，直接生效
STATUS_DEF_DOWN: Final[str] = "def_down"  # 减防：诅咒，直接生效
STATUS_COMA: Final[str] = "coma"  # 昏迷：无法行动，被打不醒
STATUS_STUN: Final[str] = "stun"  # 眩晕：每回合仅 1 次行动，被打不醒
STATUS_SLEEP: Final[str] = "sleep"  # 睡眠：无法行动，被打会醒
STATUS_CHARM: Final[str] = "charm"  # 魅惑：可行动但打友方，友方不可打该目标，被打会醒

# 异常状态：吃 resist_ailment（公式未开）
STATUS_AILMENT: Final[frozenset[str]] = frozenset(
    {
        STATUS_POISON,
        STATUS_BURN,
        STATUS_DROWN,
        STATUS_PARALYZE,
        STATUS_SLEEP,
        STATUS_CHARM,
        STATUS_STUN,
        STATUS_COMA,
    },
)
# 诅咒：降低战斗属性的效果，吃 resist_dark（公式未开）
STATUS_CURSE: Final[frozenset[str]] = frozenset({STATUS_ATK_DOWN, STATUS_DEF_DOWN})

STATUS_DOT: Final[frozenset[str]] = frozenset({STATUS_POISON, STATUS_BURN})
STATUS_STAT_MOD: Final[frozenset[str]] = STATUS_CURSE
STATUS_CC: Final[frozenset[str]] = frozenset(
    {STATUS_COMA, STATUS_STUN, STATUS_SLEEP, STATUS_CHARM},
)

STATUS_LABEL_ZH: Final[dict[str, str]] = {
    STATUS_POISON: "中毒",
    STATUS_BURN: "灼烧",
    STATUS_DROWN: "溺水",
    STATUS_PARALYZE: "麻痹",
    STATUS_ATK_DOWN: "减攻",
    STATUS_DEF_DOWN: "减防",
    STATUS_COMA: "昏迷",
    STATUS_STUN: "眩晕",
    STATUS_SLEEP: "睡眠",
    STATUS_CHARM: "魅惑",
}

# 被攻击是否解除
STATUS_WAKE_ON_HIT: Final[dict[str, bool]] = {
    STATUS_COMA: False,
    STATUS_STUN: False,
    STATUS_SLEEP: True,
    STATUS_CHARM: True,
}
