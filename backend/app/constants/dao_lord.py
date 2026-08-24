"""道主特权 / Ability 投影常量（S1-5）。"""

from __future__ import annotations

# privileges_json 布尔键（兼容旧客户端）
PRIVILEGE_FLAG_HEAVENLY_SKILL: str = "heavenly_skill_unlocked"  # 天道技能位解锁
PRIVILEGE_FLAG_OPEN_SECRET_REALM: str = "can_open_secret_realm"  # 可开辟秘境

# privileges_json 中 grants 列表键
PRIVILEGE_GRANTS_KEY: str = "grants"  # Ability id 列表字段名

# 与布尔旗标对应的 privilege Ability id
ABILITY_LORD_HEAVENLY_SKILL_SLOT: str = "lord_heavenly_skill_slot"  # 天道技能位
ABILITY_LORD_OPEN_SECRET_REALM: str = "lord_open_secret_realm"  # 开辟秘境

# 布尔旗标 → Ability id
PRIVILEGE_FLAG_TO_ABILITY: dict[str, str] = {
    PRIVILEGE_FLAG_HEAVENLY_SKILL: ABILITY_LORD_HEAVENLY_SKILL_SLOT,  # 天道技
    PRIVILEGE_FLAG_OPEN_SECRET_REALM: ABILITY_LORD_OPEN_SECRET_REALM,  # 秘境
}

# Ability id → 布尔旗标（逆映射）
PRIVILEGE_ABILITY_TO_FLAG: dict[str, str] = {
    v: k for k, v in PRIVILEGE_FLAG_TO_ABILITY.items()
}
