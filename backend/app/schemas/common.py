"""
统一响应包与业务错误（M0 §4.2 / §4.3）。
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """返回给前端的统一信封结构。"""

    code: int = Field(description="0 表示成功；非 0 为业务错误码")
    message: str = Field(description="可读提示信息")
    data: T | None = None


class AppError(Exception):
    """
    可映射为统一信封的业务异常。

    Attributes:
        code: M0 业务错误码。
        message: 给客户端看的说明。
        http_status: 对应的 HTTP 状态码。
    """

    def __init__(self, code: int, message: str, http_status: int = 400) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


def success(data: Any = None, message: str = "ok") -> dict[str, Any]:
    """构造成功响应字典。"""
    return {"code": 0, "message": message, "data": data}


def failure(code: int, message: str) -> dict[str, Any]:
    """构造失败响应字典。"""
    return {"code": code, "message": message, "data": None}


# Pydantic v2 缺字段时的英文 msg；禁止原样甩给玩家（§0.0.2）
_PYDANTIC_FIELD_REQUIRED: str = "Field required"
_FIELD_LABEL_ZH: dict[str, str] = {
    "kind": "运用场景",
    "recipe_id": "配方",
    "actor": "执行者",
    "dao_id": "大道",
    "session_id": "会话",
}


def player_validation_message(err: dict[str, Any]) -> str:
    """
    把 FastAPI / Pydantic 校验错误译成玩家可见中文。

    Args:
        err: ``RequestValidationError.errors()`` 的单项。

    Returns:
        中文提示；缺字段时带上字段名，避免界面出现 Field required。
    """
    loc = err.get("loc") or ()
    field = loc[-1] if loc else ""
    if isinstance(field, int):
        field = loc[-2] if len(loc) >= 2 else str(field)
    raw_msg = str(err.get("msg") or "请求参数非法")
    missing = err.get("type") == "missing" or raw_msg.lower() == _PYDANTIC_FIELD_REQUIRED.lower()
    if missing:
        if field:
            label = _FIELD_LABEL_ZH.get(str(field), str(field))
            return f"缺少必填字段：{label}"
        return "缺少必填字段"
    return f"请求参数非法：{raw_msg}"
