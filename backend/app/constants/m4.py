"""
M4 领域常量与枚举：挂机方向、工坊状态、棋子执行者、化身功能。

权威入口：``app.constants.m4``（S1-6 已删除 ``domain.m4_constants`` shim）。
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

    IDLE_SPIRIT = "idle_spirit"  # 化身修灵挂机
    IDLE_BODY = "idle_body"  # 化身炼体挂机
    IDLE_CRAFTING = "idle_crafting"  # 化身制造业挂机
    WORKSHOP_ACTOR = "workshop_actor"  # 化身可当工坊执行者
    DEPLOY_WITH_MAIN = "deploy_with_main"  # 可与本体同阵
    STAMINA = "stamina"  # 化身体力槽
    # SOLO_BATTLE 已取消（v1.3）：编成永久必须含本体
    FRIEND_ASSIST = "friend_assist"  # 道友化身助战
    EXPLORE_PROXY = "explore_proxy"  # 探索代理
    QUEST_NPC = "quest_npc"  # NPC 任务
    QUEST_SECT = "quest_sect"  # 宗门任务
    TRANSFER_CULTIVATION = "transfer_cultivation"  # 互传修为


# 挂机方向 → 对应功能 id（none 无需功能；采矿复用修灵挂机解锁）
IDLE_DIRECTION_FEATURE: dict[str, str] = {
    IdleDirection.SPIRIT: AvatarFeature.IDLE_SPIRIT,  # 修灵方向需 idle_spirit
    IdleDirection.BODY: AvatarFeature.IDLE_BODY,  # 炼体方向需 idle_body
    IdleDirection.CRAFTING: AvatarFeature.IDLE_CRAFTING,  # 制造业方向需 idle_crafting
    "sect_mining": AvatarFeature.IDLE_SPIRIT,  # 宗门采矿复用修灵解锁
}

# 宗门采矿挂机方向字面量（非 IdleDirection 枚举成员，协议兼容）
IDLE_DIRECTION_SECT_MINING: str = "sect_mining"  # 宗门矿脉挂机方向 id


class CraftJobStatus(StrEnum):
    """工坊任务生命周期状态。"""

    RUNNING = "running"  # 进行中（未到 finish_at）
    READY = "ready"  # 已完成待领取
    CLAIMED = "claimed"  # 已领取入背包/阵法
    FAILED = "failed"  # 失败（材料/环境等）


# 可产出资源的挂机方向（不含 none）
PRODUCTIVE_IDLE_DIRECTIONS: frozenset[str] = frozenset(
    {
        IdleDirection.SPIRIT,  # 修灵
        IdleDirection.BODY,  # 炼体
        IdleDirection.CRAFTING,  # 制造业
    },
)

# 工坊队列占用槽位的状态（已满判定用）
CRAFT_ACTIVE_STATUSES: frozenset[str] = frozenset(
    {
        CraftJobStatus.RUNNING,  # 进行中占槽
        CraftJobStatus.READY,  # 待领取仍占槽
    },
)
