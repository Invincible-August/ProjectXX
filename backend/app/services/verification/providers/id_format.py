"""
身份核验 Provider A：国标 GB 11643-1999 十八位身份证号格式与校验位。

本 Provider 完全在本地执行，不依赖任何第三方服务，可在生产环境直接使用。
"""

from __future__ import annotations

import re
from datetime import date

from app.schemas.common import AppError

# GB 11643 规定的前 17 位加权因子（第 18 位为校验位，不参与加权）
_CHECKSUM_WEIGHTS: tuple[int, ...] = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
# 加权和对 11 取余后，按余数 0~10 顺序对应的校验码（Z10 对应字符 'X'）
_CHECK_CODE_BY_REMAINDER: str = "10X98765432"

# 前 17 位必须为数字，末位允许数字或大小写 X（历史遗留身份证末位校验码可能为 X）
_ID_CARD_PATTERN = re.compile(r"^\d{17}[0-9Xx]$")


def _compute_check_code(first_seventeen_digits: str) -> str:
    """
    按 GB 11643 加权算法，由前 17 位数字计算出应有的第 18 位校验码。

    Args:
        first_seventeen_digits: 身份证号的前 17 位数字字符串。

    Returns:
        str: 计算得到的校验码字符（``0``-``9`` 或 ``X``）。
    """
    weighted_sum = sum(
        int(digit_char) * weight
        for digit_char, weight in zip(first_seventeen_digits, _CHECKSUM_WEIGHTS, strict=True)
    )
    return _CHECK_CODE_BY_REMAINDER[weighted_sum % 11]


def validate_id_card_format(id_card: str) -> None:
    """
    校验 18 位身份证号的格式、地址码粗检、出生日期与校验位。

    Args:
        id_card: 待校验的身份证号原文。

    Raises:
        AppError: 任一校验项不通过时抛出，业务错误码固定为 ``40014``。
    """
    if not id_card or not _ID_CARD_PATTERN.match(id_card):
        raise AppError(
            40014,
            "身份证号格式不合法：应为 18 位，末位可为数字或 X",
            http_status=400,
        )

    # 地址码粗检：仅要求省级代码非 0，不校验具体行政区划是否真实存在
    if id_card[0] == "0":
        raise AppError(40014, "身份证号地址码不合法", http_status=400)

    # 出生日期需为合法日历日期，且不能是未来日期
    birth_digits = id_card[6:14]
    try:
        birth_date = date(
            int(birth_digits[0:4]),
            int(birth_digits[4:6]),
            int(birth_digits[6:8]),
        )
    except ValueError as exc:
        raise AppError(40014, "身份证号出生日期不合法", http_status=400) from exc
    if birth_date > date.today():
        raise AppError(40014, "身份证号出生日期不合法：晚于当前日期", http_status=400)

    expected_check_code = _compute_check_code(id_card[:17])
    actual_check_code = id_card[17].upper()
    if actual_check_code != expected_check_code:
        raise AppError(40014, "身份证号校验位不匹配", http_status=400)


class FormatIdentityProvider:
    """
    Identity provider A: local GB 11643 ID-card format and checksum validation.
    """

    async def verify(
        self,
        *,
        real_name: str,
        id_card: str,
        face_token: str | None = None,
    ) -> None:
        """
        Verify ID-card format locally (real_name / face_token ignored).

        Args:
            real_name: Legal name (unused for format-only checks).
            id_card: 18-digit ID card number.
            face_token: Ignored in format mode.

        Raises:
            AppError: Format validation failure (code ``40014``).
        """
        _ = real_name, face_token
        validate_id_card_format(id_card)


_default_provider = FormatIdentityProvider()
