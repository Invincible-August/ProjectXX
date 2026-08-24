"""ATTR 属性键序与主键列表（自 domain.combat 抽离，权威在此）。"""

from __future__ import annotations

# 战斗 final 核心键（含抗性）；别名另附
COMBAT_FINAL_KEYS: tuple[str, ...] = (
    "hp",  # 生命
    "phys_atk",  # 物理攻击
    "phys_def",  # 物理防御
    "magic_atk",  # 法术攻击
    "magic_def",  # 法术防御
    "speed",  # 速度
    "mp",  # 法力
    "hit",  # 命中
    "dodge",  # 闪避
    "resist_metal",  # 金抗
    "resist_wood",  # 木抗
    "resist_water",  # 水抗
    "resist_fire",  # 火抗
    "resist_earth",  # 土抗
    "resist_wind",  # 风抗
    "resist_thunder",  # 雷抗
    "resist_ailment",  # 异常状态抗性
    "resist_dark",  # 暗抗（诅咒）
)

# 对外摘要（道友卡/列表）子集；禁止 mag_atk 等缩写分叉
PUBLIC_COMBAT_SUMMARY_KEYS: tuple[str, ...] = (
    "phys_atk",  # 物攻摘要
    "magic_atk",  # 法攻摘要
    "hp",  # 生命摘要
    "phys_def",  # 物防摘要
    "magic_def",  # 法防摘要
    "speed",  # 速度摘要
)

# 引擎当前消费的核心键（物法未拆前 atk←phys_atk）
ENGINE_CORE_KEYS: tuple[str, ...] = (
    "hp",  # 引擎生命
    "phys_atk",  # 引擎物攻（映射旧 atk）
    "speed",  # 引擎速度
    "mp",  # 引擎法力
)

# 主键（力敏智悟根）
PRIMARY_KEYS: tuple[str, ...] = (
    "strength",  # 力量
    "agility",  # 敏捷
    "intelligence",  # 智力
    "comprehension",  # 悟性
    "bone_root",  # 根骨
)

# 生活属性键（LifeAttrBlock）
LIFE_KEYS: tuple[str, ...] = (
    "comprehension",  # 悟性（生活栏亦可展示）
    "stamina",  # 体力
    "resist_heart_demon",  # 心魔抗性
    "resist_tribulation",  # 天劫抗性
    "breath_efficiency",  # 吐纳效率
    "endurance",  # 耐力
    "craft_dexterity",  # 炼器灵巧
    "precision",  # 精密
    "temperament",  # 心性
)

# 叠层后下限（hp/speed 至少 1；攻防等 ≥ 0）
FLOOR_MINS: dict[str, int] = {
    "hp": 1,  # 生命下限
    "speed": 1,  # 速度下限
}

# 默认迁移期别名（可被 YAML aliases 覆盖）
DEFAULT_ALIASES: dict[str, str] = {
    "atk": "phys_atk",  # 旧物攻键 → phys_atk
    "defense": "phys_def",  # 旧防御键 → phys_def
}

# AdditiveSource 常用 source_id
ATTR_SOURCE_TECHNIQUE: str = "technique"  # 功法加算来源 id
ATTR_SOURCE_CONSTITUTION: str = "constitution"  # 体质加算来源 id

# 体质 YAML 基础点（非 CombatAttr 键；创角样本 vitality/defense）
CONSTITUTION_BASE_ATTR_KEYS: frozenset[str] = frozenset(
    {
        "vitality",  # 气血点（体质本体）
        "defense",  # 防御点（体质本体；与 ATTR 别名 defense→phys_def 分轨）
        *PRIMARY_KEYS,
    },
)
# 体质词条 effects 遗留键（尚未迁入 ATTR 注册表；扩表不得再发明新键）
CONSTITUTION_LEGACY_EFFECT_KEYS: frozenset[str] = frozenset(
    {
        "hp_bonus",  # 生命加算（体质公式）
        "atk_bonus",  # 攻击加算（体质公式）
        "idle_mult",  # 挂机乘区钩子
    },
)
ATTR_SOURCE_EQUIPMENT: str = "equipment"  # 装备加算来源 id（通道可关）
