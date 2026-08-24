"""
玩家对外账号号（public_uid）协议常量（§0.6.3）。

格式：``前缀 + 7 位数字``，共 8 字符。数据库主键 ``users.id`` 仍由库自增生成。
"""

from __future__ import annotations

# 邮箱注册前缀
USER_ID_PREFIX_EMAIL = "M"
# 手机注册前缀
USER_ID_PREFIX_PHONE = "P"
# 测试环境统一前缀
USER_ID_PREFIX_TEST = "T"
# GM 账号前缀（运营可设；GM 功能暂未开放）
USER_ID_PREFIX_GM = "G"

# public_uid 总长度（1 前缀 + 7 数字）
PUBLIC_UID_LENGTH = 8
# 数字段位数
PUBLIC_UID_DIGIT_LEN = 7

# 合法前缀集合
USER_ID_PREFIXES: frozenset[str] = frozenset(
    {
        USER_ID_PREFIX_EMAIL,
        USER_ID_PREFIX_PHONE,
        USER_ID_PREFIX_TEST,
        USER_ID_PREFIX_GM,
    },
)
