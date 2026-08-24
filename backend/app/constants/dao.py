"""大道 / 悟道协议常量。"""

from __future__ import annotations

# 未达开道最低大境界（真仙）
ERR_DAO_REALM = 40080
# 本周目已锁定本命道
ERR_DAO_LOCKED = 40081
# 开道会话缺失或过期
ERR_DAO_SESSION = 40082
# 非法选择
ERR_DAO_BAD_CHOICE = 40083
# 道值不足
ERR_DAO_QI = 40084
# 尚未开辟本命道
ERR_DAO_NOT_OPEN = 40085
# 大道系统关闭
ERR_DAO_DISABLED = 40094
# 候选不足三次
ERR_DAO_CANDIDATES = 40095
# 已有开道会话禁止重抽
ERR_DAO_REROLL = 40096
# 开道最低大境界 id（与 dao.yaml open.min_major_realm 默认对齐）
DAO_OPEN_MIN_MAJOR_DEFAULT: str = "true_immortal"
