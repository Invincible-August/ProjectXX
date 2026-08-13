"""
非负整型校验（灵石、炉鼎小时等货币/时限字段）。

禁止布尔、小数、非整数字符串；允许整型与「整值」浮点（如 3.0）。
"""

from __future__ import annotations

from typing import Any


def require_non_negative_int(value: Any, *, field_zh: str = "数值") -> int:
    """
    解析并校验非负整数。

    Args:
        value: 原始输入。
        field_zh: 字段中文名（用于报错）。

    Returns:
        int: ``>= 0`` 的整数。

    Raises:
        ValueError: 类型非法或小于 0。
    """
    if value is None:
        raise ValueError(f"{field_zh}须为整数且 ≥ 0")
    if isinstance(value, bool):
        raise ValueError(f"{field_zh}须为整数，不可为布尔值")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"{field_zh}须为整数，不可含小数")
        parsed = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text or not text.isdigit():
            # 仅允许无符号纯数字（≥0）
            if text.startswith("-") and text[1:].isdigit():
                raise ValueError(f"{field_zh}须 ≥ 0")
            raise ValueError(f"{field_zh}须为整数")
        parsed = int(text)
    else:
        raise ValueError(f"{field_zh}须为整数")
    if parsed < 0:
        raise ValueError(f"{field_zh}须 ≥ 0")
    return parsed


def coerce_non_negative_int_or_app_error(
    value: Any,
    *,
    field_zh: str = "数值",
) -> int:
    """
    同 ``require_non_negative_int``，失败时抛 ``AppError``。

    Args:
        value: 原始输入。
        field_zh: 字段中文名。

    Returns:
        int: 非负整数。
    """
    from app.schemas.common import AppError

    try:
        return require_non_negative_int(value, field_zh=field_zh)
    except ValueError as exc:
        raise AppError(code=40000, message=str(exc), http_status=400) from exc
