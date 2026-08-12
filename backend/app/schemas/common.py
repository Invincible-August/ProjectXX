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
