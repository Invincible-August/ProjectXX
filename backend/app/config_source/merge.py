"""配置字典深度合并（覆盖层优先）。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """
    深度合并两个 mapping；``overlay`` 覆盖 ``base`` 同名键。

    嵌套 dict 递归合并；list / 标量整段替换（不做 list 元素级 merge）。

    Args:
        base: YAML 底表解析结果。
        overlay: 已发布或草稿覆盖层。

    Returns:
        dict[str, Any]: 新字典（不修改入参）。
    """
    result: dict[str, Any] = deepcopy(base)
    for key, overlay_value in overlay.items():
        base_value = result.get(key)
        # 两侧均为 dict 时递归，便于只覆盖 species 中新增一项
        if isinstance(base_value, dict) and isinstance(overlay_value, dict):
            result[key] = deep_merge(base_value, overlay_value)
        else:
            result[key] = deepcopy(overlay_value)
    return result
