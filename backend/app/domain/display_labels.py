"""
玩家可见中文标签映射（开发计划 §0.0.2）。

机读 id 存英文；展示层经本模块或配置 ``label_zh`` / ``labels`` 译出。
禁止把裸英文 id 直接作为玩家正文。
"""

from __future__ import annotations

from typing import Mapping

# 挂机方向 id → 中文
IDLE_DIRECTION_LABEL_ZH: dict[str, str] = {
    "none": "停止",
    "spirit": "修炼",
    "body": "淬体",
    "crafting": "制造业修炼",
    "sect_mining": "采矿",
}

# 渡劫会话 phase → 中文
TRIBULATION_PHASE_LABEL_ZH: dict[str, str] = {
    "preparing": "准备中",
    "committed": "已确认",
    "running": "渡劫中",
    "won": "渡劫成功",
    "failed": "渡劫失败",
    "fallen": "陨落",
}

# 突破进阶类型（玩家可见文案，避免「层进阶」难懂）
ADVANCE_TYPE_LABEL_ZH: dict[str, str] = {
    "layer": "同境升层/升期",
    "major": "跨入下一大境",
}


def label_zh_or_unknown(
    content_id: str | None,
    labels: Mapping[str, str] | None = None,
    *,
    unknown: str = "未知",
) -> str:
    """
    Resolve a display label; never return a bare English id as the sole body text.

    Args:
        content_id: Machine id (may be None/empty).
        labels: Optional id → Chinese map (config catalog / YAML labels).
        unknown: Placeholder when id missing or unmapped.

    Returns:
        str: Chinese label, or ``未知(id)`` when unmapped (id only in parentheses).
    """
    if not content_id:
        return unknown
    key = str(content_id)
    if labels and key in labels and labels[key]:
        return str(labels[key])
    return f"{unknown}({key})"


def idle_direction_label_zh(direction: str | None) -> str:
    """
    Map idle direction id to Chinese.

    Args:
        direction: ``none`` / ``spirit`` / ``body`` / ``crafting``.

    Returns:
        str: Chinese label.
    """
    if not direction:
        return IDLE_DIRECTION_LABEL_ZH["none"]
    return IDLE_DIRECTION_LABEL_ZH.get(str(direction), f"未知({direction})")


def tribulation_phase_label_zh(phase: str | None) -> str:
    """
    Map tribulation session phase to Chinese.

    Args:
        phase: Session phase id.

    Returns:
        str: Chinese label.
    """
    if not phase:
        return "未知"
    return TRIBULATION_PHASE_LABEL_ZH.get(str(phase), f"未知({phase})")


def advance_type_label_zh(advance_type: str | None) -> str:
    """
    Map breakthrough advance type to Chinese.

    Args:
        advance_type: ``layer`` or ``major``.

    Returns:
        str: Chinese label.
    """
    if not advance_type:
        return "未知"
    return ADVANCE_TYPE_LABEL_ZH.get(str(advance_type), f"未知({advance_type})")
