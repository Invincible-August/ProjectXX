"""Ability 作用域 / 形态枚举（与 abilities 配置对齐）。"""

from __future__ import annotations

from enum import StrEnum


class AbilityDomain(StrEnum):
    """能力作用域：决定由哪条运行时消费。"""

    COMBAT = "combat"  # 战斗内
    IDLE = "idle"  # 挂机
    CRAFT = "craft"  # 工坊
    DICE = "dice"  # 检定骰
    PRIVILEGE = "privilege"  # 玩法权限
    PANEL = "panel"  # 仅面板展示


class AbilityKind(StrEnum):
    """能力形态。"""

    STAT_MOD = "stat_mod"  # 静态属性修正
    PASSIVE_MOD = "passive_mod"  # 改技能规则
    TRIGGER = "trigger"  # 事件触发
    ACTIVE = "active"  # 主动释放
    AURA = "aura"  # 光环
    PRIVILEGE = "privilege"  # 特权开关


ABILITY_DOMAINS: frozenset[str] = frozenset(m.value for m in AbilityDomain)  # 合法 domain 集合
ABILITY_KINDS: frozenset[str] = frozenset(m.value for m in AbilityKind)  # 合法 kind 集合
