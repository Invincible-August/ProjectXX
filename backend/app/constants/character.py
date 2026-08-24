"""角色状态、制造业分支等养成侧协议常量（开发计划 §0.6.3）。"""

from __future__ import annotations

# —— 运营可改的「状态」条件（非渡劫/引渡等生命周期）——
CHARACTER_STATUS_NORMAL: str = "normal"  # 正常
CHARACTER_STATUS_EPIPHANY: str = "epiphany"  # 顿悟
CHARACTER_STATUS_WEAK: str = "weak"  # 虚弱
CHARACTER_STATUS_POISONED: str = "poisoned"  # 中毒
CHARACTER_STATUS_DEMONIC: str = "demonic"  # 入魔
CHARACTER_STATUS_CONFUSED: str = "confused"  # 混乱
CHARACTER_STATUS_FATIGUED: str = "fatigued"  # 疲劳

# 运营状态下拉可选集合（不含待引渡等系统态）
CHARACTER_STATUS_ADMIN_CHOICES: tuple[str, ...] = (
    CHARACTER_STATUS_NORMAL,
    CHARACTER_STATUS_EPIPHANY,
    CHARACTER_STATUS_WEAK,
    CHARACTER_STATUS_POISONED,
    CHARACTER_STATUS_DEMONIC,
    CHARACTER_STATUS_CONFUSED,
    CHARACTER_STATUS_FATIGUED,
)

# 中文展示（运营 / 面板）
CHARACTER_STATUS_LABEL_ZH: dict[str, str] = {
    CHARACTER_STATUS_NORMAL: "正常",
    CHARACTER_STATUS_EPIPHANY: "顿悟",
    CHARACTER_STATUS_WEAK: "虚弱",
    CHARACTER_STATUS_POISONED: "中毒",
    CHARACTER_STATUS_DEMONIC: "入魔",
    CHARACTER_STATUS_CONFUSED: "混乱",
    CHARACTER_STATUS_FATIGUED: "疲劳",
    # 系统生命周期态（死亡→待引渡等；不在运营「状态」下拉内）
    "awaiting_ferry": "待引渡",
    "tribulation": "渡劫中",
    "reincarnating": "轮回中",
    "breaking_through": "突破中",
    "idle": "空闲",  # 兼容旧常量
    "pending_ferry": "待引渡",  # 兼容旧键 → 运行时仍写 awaiting_ferry
    "dead": "死亡",  # 兼容占位；正式死亡走 awaiting_ferry
}

# —— 系统生命周期（与运营条件下拉分离）——
CHARACTER_STATUS_AWAITING_FERRY: str = "awaiting_ferry"  # 待引渡（死亡入口）
CHARACTER_STATUS_TRIBULATION: str = "tribulation"  # 渡劫中
CHARACTER_STATUS_REINCARNATING: str = "reincarnating"  # 轮回中
CHARACTER_STATUS_BREAKING_THROUGH: str = "breaking_through"  # 突破读条中

# 兼容旧命名（ARCH / 早期常量）
CHARACTER_STATUS_IDLE: str = CHARACTER_STATUS_NORMAL  # 空闲可玩 ≈ 正常
CHARACTER_STATUS_PENDING_FERRY: str = CHARACTER_STATUS_AWAITING_FERRY  # 待引渡
CHARACTER_STATUS_DEAD: str = "dead"  # 死亡占位（运营「死亡」写 awaiting_ferry）

# —— GrantSource（能力授予来源）——
GRANT_SOURCE_TECHNIQUE: str = "technique"  # 功法
GRANT_SOURCE_CONSTITUTION: str = "constitution"  # 体质
GRANT_SOURCE_EQUIPMENT: str = "equipment"  # 装备
GRANT_SOURCE_SET: str = "set"  # 套装
GRANT_SOURCE_DAO_LORD: str = "dao_lord"  # 道主席位特权

# —— 制造业分支（craft_recipes.branch）——
CRAFT_BRANCH_ALCHEMY: str = "alchemy"  # 炼丹
CRAFT_BRANCH_SMITHING: str = "smithing"  # 炼器
CRAFT_BRANCH_TALISMAN: str = "talisman"  # 制符
CRAFT_BRANCH_ARRAY: str = "array"  # 阵法
CRAFT_BRANCH_PUPPET: str = "puppet"  # 傀儡

CRAFT_BRANCHES: tuple[str, ...] = (
    CRAFT_BRANCH_ALCHEMY,
    CRAFT_BRANCH_SMITHING,
    CRAFT_BRANCH_TALISMAN,
    CRAFT_BRANCH_ARRAY,
    CRAFT_BRANCH_PUPPET,
)

# 工坊可开工的制造业分支；阵法属于布阵/自研，不进工坊
CRAFT_WORKSHOP_BRANCHES: tuple[str, ...] = (
    CRAFT_BRANCH_ALCHEMY,
    CRAFT_BRANCH_SMITHING,
    CRAFT_BRANCH_TALISMAN,
    CRAFT_BRANCH_PUPPET,
)

CRAFT_BRANCH_LABEL_ZH: dict[str, str] = {
    CRAFT_BRANCH_ALCHEMY: "炼丹",
    CRAFT_BRANCH_SMITHING: "炼器",
    CRAFT_BRANCH_TALISMAN: "制符",
    CRAFT_BRANCH_ARRAY: "阵法",
    CRAFT_BRANCH_PUPPET: "傀儡",
}

# 角色属性面板用的等级栏名
CRAFT_BRANCH_LEVEL_LABEL_ZH: dict[str, str] = {
    CRAFT_BRANCH_ALCHEMY: "炼丹等级",
    CRAFT_BRANCH_SMITHING: "炼器等级",
    CRAFT_BRANCH_TALISMAN: "制符等级",
    CRAFT_BRANCH_ARRAY: "阵法等级",
    CRAFT_BRANCH_PUPPET: "傀儡制作等级",
}

# growth_attrs_json 内制造业等级字典键
GROWTH_ATTR_CRAFT_LEVELS_KEY: str = "craft_levels"
