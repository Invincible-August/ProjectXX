"""配置字典深度合并（覆盖层优先）。"""

from __future__ import annotations

from collections.abc import Collection
from copy import deepcopy
from typing import Any

# 目录类字段：覆盖层出现该键时整段替换（支持网格批量删除 YAML 底表条目）
# 与「物种增量合并」不同；list 本身已是整段替换，无需登记。
OVERLAY_REPLACE_KEYS: dict[str, frozenset[str]] = {
    "dao": frozenset({"entries", "labels"}),
}


def deep_merge(
    base: dict[str, Any],
    overlay: dict[str, Any],
    *,
    replace_keys: Collection[str] | None = None,
) -> dict[str, Any]:
    """
    深度合并两个 mapping；``overlay`` 覆盖 ``base`` 同名键。

    嵌套 dict 默认递归合并；list / 标量整段替换。
    ``replace_keys`` 中的顶层键若出现在 overlay，则整段替换（不递归），
    便于道目录等表格删除底表行后能真正从生效配置消失。

    Args:
        base: YAML 底表解析结果。
        overlay: 已发布或草稿覆盖层。
        replace_keys: 须整段替换的顶层键集合。

    Returns:
        dict[str, Any]: 新字典（不修改入参）。
    """
    replace = frozenset(replace_keys) if replace_keys else frozenset()
    result: dict[str, Any] = deepcopy(base)
    for key, overlay_value in overlay.items():
        # 目录表：整键替换，删除行才能盖过 YAML
        if key in replace:
            result[key] = deepcopy(overlay_value)
            continue
        base_value = result.get(key)
        # 两侧均为 dict 时递归，便于只覆盖 species 中新增一项
        if isinstance(base_value, dict) and isinstance(overlay_value, dict):
            result[key] = deep_merge(base_value, overlay_value)
        else:
            result[key] = deepcopy(overlay_value)
    return result


def merge_domain_overlay(
    domain_id: str,
    base: dict[str, Any],
    overlay: dict[str, Any],
) -> dict[str, Any]:
    """
    按域策略合并 YAML 底表与覆盖层。

    存储形态：磁盘 YAML + DB 草稿/发布 overlay（将来整域迁库仍走同一合并入口）。

    Args:
        domain_id: 内容域 ID（如 dao）。
        base: YAML 或已生效底。
        overlay: 草稿或已发布覆盖。

    Returns:
        合并后的配置 dict。
    """
    return deep_merge(
        base,
        overlay,
        replace_keys=OVERLAY_REPLACE_KEYS.get(domain_id),
    )
