"""请求校验错误须输出中文，禁止 Field required 原文。"""

from __future__ import annotations

from app.schemas.common import player_validation_message


def test_missing_field_is_chinese() -> None:
    """缺 body.kind 时给出中文，不含 Field required。"""
    msg = player_validation_message(
        {
            "type": "missing",
            "loc": ("body", "kind"),
            "msg": "Field required",
        },
    )
    assert "Field required" not in msg
    assert "缺少必填字段" in msg
    assert "运用场景" in msg
