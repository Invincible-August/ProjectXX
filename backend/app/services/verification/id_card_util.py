"""
身份证号工具函数：哈希与脱敏展示。

身份证号原文严禁落库、严禁写入日志：数据库只保存 ``hash_id_card`` 的结果用于唯一性比对，
展示给前端时使用 ``mask_id_card`` 的脱敏结果。
"""

from __future__ import annotations

import hashlib

from app.core.config import get_settings

# 掩码规则保留的首尾位数：如 110***********1234（首 3 位 + 末 4 位）
_MASK_PREFIX_LEN = 3
_MASK_SUFFIX_LEN = 4


def normalize_id_card(id_card: str) -> str:
    """
    规范化身份证号：去掉首尾空白；末位 ``x`` 统一为大写 ``X``。

    与 ``IdSubmitRequest.normalize_id_card`` Schema 校验规则一致，
    服务层哈希/比对前应统一调用，避免「已发票但注册 target 不匹配」。

    Args:
        id_card: 用户提交的身份证号原文。

    Returns:
        str: 规范化后的身份证号。
    """
    normalized = id_card.strip()
    # 校验位 X 大小写不敏感，入库哈希统一用大写末位
    if normalized and normalized[-1] in ("x", "X"):
        return normalized[:-1] + "X"
    return normalized


def hash_id_card(id_card: str) -> str:
    """
    计算「盐 + 身份证号」的 SHA-256 哈希，供入库唯一性校验使用。

    Args:
        id_card: 18 位身份证号原文（内部会先 ``normalize_id_card``）。

    Returns:
        str: 64 位十六进制哈希字符串。
    """
    settings = get_settings()
    normalized = normalize_id_card(id_card)
    # 加盐防止彩虹表反查；盐值来自环境变量，禁止硬编码
    salted_value = f"{settings.id_card_hash_salt}{normalized}"
    return hashlib.sha256(salted_value.encode("utf-8")).hexdigest()


def mask_id_card(id_card: str) -> str:
    """
    对身份证号做脱敏展示：保留前 3 位与后 4 位，中间以 ``*`` 填充。

    Args:
        id_card: 18 位身份证号原文（内部会先 ``normalize_id_card``）。

    Returns:
        str: 形如 ``110***********1234`` 的脱敏字符串；若长度不足首尾位数之和，
        则整串替换为等长的 ``*``，避免越界截取。
    """
    normalized = normalize_id_card(id_card)
    if len(normalized) < _MASK_PREFIX_LEN + _MASK_SUFFIX_LEN:
        return "*" * len(normalized)
    star_count = len(normalized) - _MASK_PREFIX_LEN - _MASK_SUFFIX_LEN
    return (
        normalized[:_MASK_PREFIX_LEN]
        + "*" * star_count
        + normalized[-_MASK_SUFFIX_LEN:]
    )
