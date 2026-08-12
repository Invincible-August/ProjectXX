"""
活动互斥状态机（Activity Mutex）。

设计对齐 ``开发计划.md`` §0.7 / 用户约定：
- 修炼中（``idle_direction != none``）须先停止，才能开战 / 工坊 / 突破 / 渡劫等；
- 再进入修炼前，须无进行中工坊、非渡劫/引渡；战斗为同步 HTTP 无持久态；秘境预留钩子。

不把「挂机」升成 ``Character.status``，保持两轴：
``status``（生命周期）+ ``idle_direction``（挂机意图）+ 派生 busy（工坊 running 等）。
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from app.schemas.common import AppError


class Activity(str, Enum):
    """需要互斥校验的积极活动。"""

    ENTER_IDLE = "enter_idle"
    """将本体挂机切到 productive（spirit/body/crafting）。"""

    STOP_IDLE = "stop_idle"
    """将本体挂机切到 none（通常允许）。"""

    START_BATTLE = "start_battle"
    """开战（PVE/试炼等）；须先停修炼且状态允许。"""

    START_CRAFT = "start_craft"
    """工坊开工；须先停修炼。"""

    BREAKTHROUGH = "breakthrough"
    """突破 attempt；须先停修炼且非渡劫/引渡。"""

    START_TRIBULATION = "start_tribulation"
    """开渡劫会话；开渡时清空 idle_direction。"""

    # 秘境等未落地玩法预留
    ENTER_SECRET_REALM = "enter_secret_realm"
    """秘境入口占位（未落地）。"""


# 错误码：活动互斥专用（与既有 40022/40060/40061 并存，文案更明确）
ERR_STOP_IDLE_FIRST = 40074  # 须先停止修炼
ERR_FINISH_CRAFT_FIRST = 40075  # 须先完成/领取工坊
ERR_STATUS_BLOCKS = 40076  # 当前 status 阻断该活动
ERR_SECRET_REALM = 40077  # 秘境占用（占位）


def is_productive_idle(idle_direction: str | None) -> bool:
    """
    是否处于本体修炼中。

    Args:
        idle_direction: 角色挂机方向。

    Returns:
        True 表示 spirit/body/crafting。
    """
    return (idle_direction or "none") in {"spirit", "body", "crafting"}


def assert_can_perform(
    *,
    status: str,
    idle_direction: str | None,
    activity: Activity,
    craft_running: int = 0,
    in_secret_realm: bool = False,
) -> None:
    """
    校验角色当前态是否允许执行 ``activity``；不允许则抛 ``AppError``。

    Args:
        status: Character.status。
        idle_direction: Character.idle_direction。
        activity: 目标活动。
        craft_running: 工坊 RUNNING 任务数（settle 后统计）。
        in_secret_realm: 未来秘境会话占位；当前恒 False。

    Raises:
        AppError: 40074/40075/40076/40077 或复用 40060/40061 语义的明确文案。
    """
    status = status or "normal"
    idle = idle_direction or "none"
    crafting = int(craft_running or 0)

    # —— 停修炼：仅生命周期拦截（渡劫中仍禁改方向由调用方/本函数 ENTER 对称处理）——
    if activity == Activity.STOP_IDLE:
        if status == "tribulation":
            raise AppError(
                code=40061,
                message="渡劫中禁止改本体挂机方向",
                http_status=409,
            )
        if status in ("awaiting_ferry", "reincarnating"):
            raise AppError(
                code=40060,
                message="当前状态不可切换挂机方向",
                http_status=409,
            )
        return

    # —— 进入修炼 ——
    if activity == Activity.ENTER_IDLE:
        if status != "normal":
            raise AppError(
                code=ERR_STATUS_BLOCKS,
                message=_status_block_message(status, "进入修炼"),
                http_status=409,
            )
        if crafting > 0:
            raise AppError(
                code=ERR_FINISH_CRAFT_FIRST,
                message="工坊仍有进行中的炼丹/炼器任务，请先完成或等待结束后再修炼",
                http_status=409,
            )
        if in_secret_realm:
            raise AppError(
                code=ERR_SECRET_REALM,
                message="仍在秘境中，请先离开秘境再修炼",
                http_status=409,
            )
        return

    # —— 其它积极玩法：须 normal + 未修炼 ——
    if status != "normal":
        # 渡劫/引渡用既有码，便于前端旧分支
        if status == "tribulation":
            raise AppError(
                code=40060,
                message="渡劫中不可进行该操作",
                http_status=409,
            )
        if status in ("awaiting_ferry", "reincarnating"):
            raise AppError(
                code=40060,
                message="待引渡/轮回中不可进行该操作",
                http_status=409,
            )
        if status == "breaking_through":
            raise AppError(
                code=40022,
                message="进阶中不可进行该操作",
                http_status=409,
            )
        raise AppError(
            code=ERR_STATUS_BLOCKS,
            message=_status_block_message(status, _activity_label(activity)),
            http_status=409,
        )

    if is_productive_idle(idle):
        raise AppError(
            code=ERR_STOP_IDLE_FIRST,
            message=f"修炼中不可{_activity_label(activity)}，请先停止修炼",
            http_status=409,
        )

    if activity == Activity.ENTER_SECRET_REALM and in_secret_realm:
        raise AppError(
            code=ERR_SECRET_REALM,
            message="已在秘境中",
            http_status=409,
        )


def _activity_label(activity: Activity) -> str:
    """活动中文名（错误文案用）。"""
    labels = {
        Activity.START_BATTLE: "开战",
        Activity.START_CRAFT: "开工坊炼丹/炼器",
        Activity.BREAKTHROUGH: "突破",
        Activity.START_TRIBULATION: "进入渡劫",
        Activity.ENTER_SECRET_REALM: "进入秘境",
        Activity.ENTER_IDLE: "进入修炼",
        Activity.STOP_IDLE: "停止修炼",
    }
    return labels.get(activity, activity.value)


def _status_block_message(status: str, action: str) -> str:
    """生命周期状态拦截文案。"""
    names = {
        "breaking_through": "进阶中",
        "tribulation": "渡劫中",
        "awaiting_ferry": "待引渡",
        "reincarnating": "轮回中",
    }
    return f"{names.get(status, status)}不可{action}"


def build_activity_snapshot(
    *,
    status: str,
    idle_direction: str | None,
    craft_running: int = 0,
    in_secret_realm: bool = False,
) -> dict[str, Any]:
    """
    构建玩家可见的活动态摘要（显性设计：界面可展示当前占用与拦截原因）。

    Args:
        status: 生命周期状态。
        idle_direction: 挂机方向。
        craft_running: 工坊进行中数量。
        in_secret_realm: 秘境占位。

    Returns:
        可嵌入 CharacterPublic.activity 的 dict。
    """
    status = status or "normal"
    idle = idle_direction or "none"
    crafting = int(craft_running or 0)
    productive = is_productive_idle(idle)

    if status == "tribulation":
        mode = "tribulation"
        mode_label = "渡劫中"
    elif status == "awaiting_ferry":
        mode = "awaiting_ferry"
        mode_label = "待引渡"
    elif status == "reincarnating":
        mode = "reincarnating"
        mode_label = "轮回中"
    elif status == "breaking_through":
        mode = "breaking_through"
        mode_label = "进阶中"
    elif productive:
        mode = "idle"
        mode_label = {"spirit": "修灵中", "body": "炼体中", "crafting": "制造业挂机中"}.get(
            idle, "修炼中",
        )
    elif crafting > 0:
        mode = "craft"
        mode_label = f"工坊进行中（{crafting}）"
    elif in_secret_realm:
        mode = "secret_realm"
        mode_label = "秘境中"
    else:
        mode = "free"
        mode_label = "空闲"

    def _probe(activity: Activity) -> tuple[bool, str | None]:
        try:
            assert_can_perform(
                status=status,
                idle_direction=idle,
                activity=activity,
                craft_running=crafting,
                in_secret_realm=in_secret_realm,
            )
            return True, None
        except AppError as exc:
            return False, str(exc.message)

    can_enter_idle, block_enter_idle = _probe(Activity.ENTER_IDLE)
    can_start_craft, block_craft = _probe(Activity.START_CRAFT)
    can_start_battle, block_battle = _probe(Activity.START_BATTLE)
    can_breakthrough, block_bt = _probe(Activity.BREAKTHROUGH)
    can_tribulation, block_trib = _probe(Activity.START_TRIBULATION)

    return {
        "mode": mode,
        "mode_label": mode_label,
        "status": status,
        "idle_direction": idle,
        "craft_running": crafting,
        "in_secret_realm": in_secret_realm,
        "can_enter_idle": can_enter_idle,
        "can_start_craft": can_start_craft,
        "can_start_battle": can_start_battle,
        "can_breakthrough": can_breakthrough,
        "can_start_tribulation": can_tribulation,
        "blockers": {
            "enter_idle": block_enter_idle,
            "start_craft": block_craft,
            "start_battle": block_battle,
            "breakthrough": block_bt,
            "start_tribulation": block_trib,
        },
    }
