"""
身份核验 Provider A（国标 18 位身份证格式校验位）单元测试。

测试号均为满足 GB 11643 校验位算法的合成号码或公开教学用测试号，
不涉及任何真实自然人身份信息。
"""

from __future__ import annotations

import pytest

from app.schemas.common import AppError
from app.services.verification.id_card_util import hash_id_card, mask_id_card, normalize_id_card
from app.services.verification.providers.id_format import validate_id_card_format

# 公开教学用合法测试号：地址码 110101（北京东城区）+ 出生日期 19900307 + 顺序码 447 + 校验位 7
_VALID_ID_CARD = "110101199003074477"


def test_id_card_checksum_valid() -> None:
    """合法校验位的身份证号应通过校验，不抛出异常。"""
    # 若不抛出异常即视为通过
    validate_id_card_format(_VALID_ID_CARD)


def test_id_card_checksum_invalid() -> None:
    """篡改最后一位校验码后应被判定为非法，抛出 AppError(40014)。"""
    tampered_id_card = _VALID_ID_CARD[:-1] + (
        "0" if _VALID_ID_CARD[-1] != "0" else "1"
    )
    with pytest.raises(AppError) as exc_info:
        validate_id_card_format(tampered_id_card)
    assert exc_info.value.code == 40014


@pytest.mark.parametrize(
    "invalid_id_card",
    [
        "",
        "12345",  # 长度不足
        "1101011990030744AA",  # 末位非法字符
        "01010119900307447X",  # 首位为 0，地址码不合法
        "110101199099074477",  # 出生月份非法（99 月）
        "110101199013074477",  # 出生月份非法（13 月）
    ],
)
def test_id_card_format_rejects_invalid_inputs(invalid_id_card: str) -> None:
    """明显不合法的格式应统一抛出 AppError(40014)。"""
    with pytest.raises(AppError) as exc_info:
        validate_id_card_format(invalid_id_card)
    assert exc_info.value.code == 40014


def test_id_card_checksum_x_suffix() -> None:
    """校验位为 X 的号码应支持大小写并正确通过校验。"""
    # 前 17 位 11010119900307002 加权和对 11 取余为 2，对应校验码 X
    first_seventeen_digits = "11010119900307002"
    upper_x_id_card = first_seventeen_digits + "X"
    lower_x_id_card = first_seventeen_digits + "x"
    validate_id_card_format(upper_x_id_card)
    validate_id_card_format(lower_x_id_card)


def test_normalize_id_card_strip_and_uppercase_x() -> None:
    """服务层规范化应与 Schema 一致：去空白、末位 x 转大写 X。"""
    first_seventeen_digits = "11010119900307002"
    with_spaces = f"  {first_seventeen_digits}x  "
    assert normalize_id_card(with_spaces) == first_seventeen_digits + "X"
    assert normalize_id_card(first_seventeen_digits + "X") == first_seventeen_digits + "X"


def test_hash_id_card_treats_lowercase_x_as_uppercase() -> None:
    """哈希前规范化：带空格/小写 x 的输入应与规范形式产生相同哈希。"""
    first_seventeen_digits = "11010119900307002"
    canonical = first_seventeen_digits + "X"
    variants = [
        f"  {first_seventeen_digits}x  ",
        first_seventeen_digits + "x",
        canonical,
    ]
    hashes = [hash_id_card(value) for value in variants]
    assert hashes[0] == hashes[1] == hashes[2]


def test_hash_id_card_is_deterministic_and_not_plaintext() -> None:
    """哈希结果应稳定可复现，且不等于原文、长度为 SHA-256 的 64 位十六进制串。"""
    hash_result_1 = hash_id_card(_VALID_ID_CARD)
    hash_result_2 = hash_id_card(_VALID_ID_CARD)
    assert hash_result_1 == hash_result_2
    assert hash_result_1 != _VALID_ID_CARD
    assert len(hash_result_1) == 64


def test_mask_id_card_pattern() -> None:
    """脱敏结果应保留首 3 位与末 4 位，中间以 * 填充，总长度不变。"""
    masked = mask_id_card(_VALID_ID_CARD)
    assert masked == "110***********4477"
    assert len(masked) == len(_VALID_ID_CARD)
