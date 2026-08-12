"""
M4 领域常量与枚举：挂机方向、工坊状态、棋子执行者。

字符串值与数据库 / API 协议保持一致；业务代码应引用本模块，避免魔法字面量漂移。
"""

from __future__ import annotations

from enum import StrEnum


class IdleDirection(StrEnum):
    """挂机三选一方向（本体与化身共用子集）。"""

    NONE = "none"  # 未挂机
    SPIRIT = "spirit"  # 修灵 → 涨 cultivation_points
    BODY = "body"  # 炼体 → 涨 body_tempering_points
    CRAFTING = "crafting"  # 制造业 → 涨 crafting_exp


class AvatarStatus(StrEnum):
    """化身状态（渡劫等可置为 disabled）。"""

    IDLE = "idle"  # 空闲（可挂机）
    CRAFTING = "crafting"  # 执行工坊任务中
    DISABLED = "disabled"  # 禁用（渡劫禁上阵等）


class CraftActor(StrEnum):
    """工坊队列执行者。"""

    MAIN = "main"  # 本体执行
    AVATAR = "avatar"  # 化身执行


class AvatarFeature(StrEnum):
    """
    化身功能 id（注册表；禁止业务散落魔法字符串）。

    解锁由本体大境界与 avatar.yaml feature_unlocks 比较得出。
    """

    IDLE_SPIRIT = "idle_spirit"
    IDLE_BODY = "idle_body"
    IDLE_CRAFTING = "idle_crafting"
    WORKSHOP_ACTOR = "workshop_actor"
    DEPLOY_WITH_MAIN = "deploy_with_main"
    STAMINA = "stamina"
    SOLO_BATTLE = "solo_battle"
    FRIEND_ASSIST = "friend_assist"
    EXPLORE_PROXY = "explore_proxy"
    QUEST_NPC = "quest_npc"
    QUEST_SECT = "quest_sect"
    TRANSFER_CULTIVATION = "transfer_cultivation"


# 挂机方向 → 对应功能 id（none 无需功能；采矿复用修灵挂机解锁）
IDLE_DIRECTION_FEATURE: dict[str, str] = {
    IdleDirection.SPIRIT: AvatarFeature.IDLE_SPIRIT,
    IdleDirection.BODY: AvatarFeature.IDLE_BODY,
    IdleDirection.CRAFTING: AvatarFeature.IDLE_CRAFTING,
    "sect_mining": AvatarFeature.IDLE_SPIRIT,
}


class CraftJobStatus(StrEnum):
    """工坊任务生命周期状态。"""

    RUNNING = "running"  # 进行中（未到 finish_at）
    READY = "ready"  # 已完成待领取
    CLAIMED = "claimed"  # 已领取入背包/阵法
    FAILED = "failed"  # 失败（材料/环境等）


# 可产出资源的挂机方向（不含 none）
PRODUCTIVE_IDLE_DIRECTIONS: frozenset[str] = frozenset(
    {
        IdleDirection.SPIRIT,
        IdleDirection.BODY,
        IdleDirection.CRAFTING,
    },
)

# 工坊队列占用槽位的状态（已满判定用）
CRAFT_ACTIVE_STATUSES: frozenset[str] = frozenset(
    {
        CraftJobStatus.RUNNING,
        CraftJobStatus.READY,
    },
)
