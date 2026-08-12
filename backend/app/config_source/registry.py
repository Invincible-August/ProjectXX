"""
内容域 ↔ YAML 文件名注册表（后台域清单权威）。

新增玩法配置域须先在此登记，禁止玩家代码写死枚举当内容源。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# 风险等级：content=内容编辑；balance=数值平衡（需更高角色）；facility=设施开关
RiskLevel = Literal["content", "balance", "facility"]


@dataclass(frozen=True)
class DomainMeta:
    """单一可后台管理内容域的元数据。"""

    domain_id: str
    """域 ID（与 Admin API 路径一致）。"""

    filename: str
    """相对 ``config_data/`` 的 YAML 文件名。"""

    title: str
    """后台 UI 展示名。"""

    risk: RiskLevel
    """编辑风险；balance 需 editor_balance 或 admin。"""

    description: str
    """一句话说明。"""

    enabled: bool = True
    """是否对本环境开放编辑（未开的域只读摘要）。"""

    category_id: str = "misc"
    """侧栏类目 ID（同组折叠）。"""

    category_title_zh: str = "其它"
    """侧栏类目中文名。"""

    category_order: int = 90
    """类目排序（越小越靠前）。"""


# 首版域清单：与《后台管理系统开发计划》§5 对齐；sects/map/activity 等占位后开
DOMAIN_REGISTRY: dict[str, DomainMeta] = {
    "pets": DomainMeta(
        domain_id="pets",
        filename="pets.yaml",
        title="灵宠",
        risk="content",
        description="物种、种族、品阶、持有上限、升阶费用",
        category_id="pet",
        category_title_zh="灵宠",
        category_order=20,
    ),
    "pet_affixes": DomainMeta(
        domain_id="pet_affixes",
        filename="pet_affixes.yaml",
        title="灵宠词条",
        risk="content",
        description="词条类型库、品级区间、数值洗炼费用（与体质分表）",
        category_id="pet",
        category_title_zh="灵宠",
        category_order=20,
    ),
    "pet_skills": DomainMeta(
        domain_id="pet_skills",
        filename="pet_skills.yaml",
        title="灵宠技能",
        risk="content",
        description="主动技能与物种技能池（装备最多 4）",
        category_id="pet",
        category_title_zh="灵宠",
        category_order=20,
    ),
    "pet_skill_books": DomainMeta(
        domain_id="pet_skill_books",
        filename="pet_skill_books.yaml",
        title="灵宠技能书",
        risk="content",
        description="技能书 scope：universal/race/species",
        category_id="pet",
        category_title_zh="灵宠",
        category_order=20,
    ),
    "pet_duel": DomainMeta(
        domain_id="pet_duel",
        filename="pet_duel.yaml",
        title="灵宠对战",
        risk="content",
        description="回合制对战规则与 NPC 模板（非自走棋）",
        category_id="pet",
        category_title_zh="灵宠",
        category_order=20,
    ),
    "pet_passives": DomainMeta(
        domain_id="pet_passives",
        filename="pet_passives.yaml",
        title="灵宠被动",
        risk="content",
        description="种族天赋与独立被动池（PET-D03）",
        category_id="pet",
        category_title_zh="灵宠",
        category_order=20,
    ),
    "pet_feed": DomainMeta(
        domain_id="pet_feed",
        filename="pet_feed.yaml",
        title="灵宠喂养",
        risk="content",
        description="兽丹效果与喂养上限（PET-D04）",
        category_id="pet",
        category_title_zh="灵宠",
        category_order=20,
    ),
    "pet_eggs": DomainMeta(
        domain_id="pet_eggs",
        filename="pet_eggs.yaml",
        title="灵兽蛋",
        risk="content",
        description="孵化蛋表：物种/耗时/费用（N5）",
        category_id="pet",
        category_title_zh="灵宠",
        category_order=20,
    ),
    "pet_encounter": DomainMeta(
        domain_id="pet_encounter",
        filename="pet_encounter.yaml",
        title="灵宠遭遇",
        risk="content",
        description="野外遭遇表 region×时辰×天气（M4-D04c）",
        category_id="pet",
        category_title_zh="灵宠",
        category_order=20,
    ),
    "pet_capture": DomainMeta(
        domain_id="pet_capture",
        filename="pet_capture.yaml",
        title="灵宠捕获",
        risk="content",
        description="捕获检定因子与诱灵草/袋（M4-D04c）",
        category_id="pet",
        category_title_zh="灵宠",
        category_order=20,
    ),
    "items": DomainMeta(
        domain_id="items",
        filename="inventory.yaml",
        title="道具",
        risk="content",
        description="背包物品、堆叠规则、物品类型",
        category_id="content",
        category_title_zh="内容与设施",
        category_order=60,
    ),
    "techniques": DomainMeta(
        domain_id="techniques",
        filename="techniques.yaml",
        title="功法",
        risk="content",
        description="功法表、环境标签、骰子修正",
        category_id="content",
        category_title_zh="内容与设施",
        category_order=60,
    ),
    "weather": DomainMeta(
        domain_id="weather",
        filename="weather.yaml",
        title="天气",
        risk="content",
        description="天气 catalog / modifiers / tag_modifiers",
        category_id="env",
        category_title_zh="环境历法",
        category_order=50,
    ),
    "calendar": DomainMeta(
        domain_id="calendar",
        filename="calendar.yaml",
        title="历法六时",
        risk="content",
        description="时辰、slot、环境乘区与说明",
        category_id="env",
        category_title_zh="环境历法",
        category_order=50,
    ),
    "monsters": DomainMeta(
        domain_id="monsters",
        filename="pve_monsters.yaml",
        title="怪物",
        risk="content",
        description="PVE 敌人模板",
        category_id="battle",
        category_title_zh="战斗",
        category_order=30,
    ),
    "formations": DomainMeta(
        domain_id="formations",
        filename="formations.yaml",
        title="阵法",
        risk="content",
        description="阵法与四象样本",
        category_id="battle",
        category_title_zh="战斗",
        category_order=30,
    ),
    "taunt_auras": DomainMeta(
        domain_id="taunt_auras",
        filename="taunt_auras.yaml",
        title="嘲讽光环",
        risk="content",
        description="嘲讽光环形状与展示；单位用 taunt_aura_id 引用（M3-D06）",
        enabled=True,
        category_id="battle",
        category_title_zh="战斗",
        category_order=30,
    ),
    "combat_attrs": DomainMeta(
        domain_id="combat_attrs",
        filename="combat_attrs.yaml",
        title="战斗属性注册表",
        risk="balance",
        description="统一 Combat/Life 属性键、别名、主键映射与通道开关（ATTR-D01）",
        category_id="combat",
        category_title_zh="战斗",
        category_order=30,
    ),
    "realms": DomainMeta(
        domain_id="realms",
        filename="realms.yaml",
        title="境界",
        risk="balance",
        description="大境界与档位（高危）",
        category_id="growth",
        category_title_zh="成长数值",
        category_order=40,
    ),
    "idle": DomainMeta(
        domain_id="idle",
        filename="idle.yaml",
        title="挂机速率",
        risk="balance",
        description="挂机 tick / 境界基础表（高危）",
        category_id="growth",
        category_title_zh="成长数值",
        category_order=40,
    ),
    "dice": DomainMeta(
        domain_id="dice",
        filename="dice.yaml",
        title="修为骰",
        risk="balance",
        description="修为检定上下限表（高危）",
        category_id="growth",
        category_title_zh="成长数值",
        category_order=40,
    ),
    "breakthrough": DomainMeta(
        domain_id="breakthrough",
        filename="breakthrough.yaml",
        title="突破",
        risk="balance",
        description="层/跨境成功率、灵石、失败惩罚、异步真读条时长（高危）",
        category_id="growth",
        category_title_zh="成长数值",
        category_order=40,
    ),
    "sects": DomainMeta(
        domain_id="sects",
        filename="sects.yaml",
        title="宗门与设施",
        risk="facility",
        description="宗门模板 + 设施开关（M7 L1）",
        enabled=True,
        category_id="content",
        category_title_zh="内容与设施",
        category_order=60,
    ),
    "friends": DomainMeta(
        domain_id="friends",
        filename="friends.yaml",
        title="道友",
        risk="content",
        description="道友上限与申请过期（M7 L2）",
        enabled=True,
        category_id="social",
        category_title_zh="社交经济",
        category_order=55,
    ),
    "trade": DomainMeta(
        domain_id="trade",
        filename="trade.yaml",
        title="交易与坊市",
        risk="balance",
        description="一口价/拍卖/面交手续费 + NPC 坊市货架（M7 L2）",
        enabled=True,
        category_id="social",
        category_title_zh="社交经济",
        category_order=55,
    ),
    "mail": DomainMeta(
        domain_id="mail",
        filename="mail.yaml",
        title="邮件与赠送",
        risk="balance",
        description="保留/过期/赠送日限（M7 L3）",
        enabled=True,
        category_id="social",
        category_title_zh="社交经济",
        category_order=55,
    ),
    "chat": DomainMeta(
        domain_id="chat",
        filename="chat.yaml",
        title="聊天频道",
        risk="content",
        description="五频道限速/敏感词/历史（M7 L4）",
        enabled=True,
        category_id="social",
        category_title_zh="社交经济",
        category_order=55,
    ),
    "chat_heritage": DomainMeta(
        domain_id="chat_heritage",
        filename="chat_heritage.yaml",
        title="聊天机缘",
        risk="balance",
        description="份数/过期/日限/拆分（M7 L5）",
        enabled=True,
        category_id="social",
        category_title_zh="社交经济",
        category_order=55,
    ),
    "mentor": DomainMeta(
        domain_id="mentor",
        filename="mentor.yaml",
        title="师徒",
        risk="content",
        description="境界差/名额/任务/传功/出师（M7 L6）",
        enabled=True,
        category_id="social",
        category_title_zh="社交经济",
        category_order=55,
    ),
    "dual_cultivation": DomainMeta(
        domain_id="dual_cultivation",
        filename="dual_cultivation.yaml",
        title="双修",
        risk="balance",
        description="功法双增/传修为、掷骰档、四榜（M7 L7）",
        enabled=True,
        category_id="social",
        category_title_zh="社交经济",
        category_order=55,
    ),
    "currencies": DomainMeta(
        domain_id="currencies",
        filename="currencies.yaml",
        title="币种目录",
        risk="content",
        description="六币种展示与禁转（M7 L8）",
        enabled=True,
        category_id="social",
        category_title_zh="社交经济",
        category_order=55,
    ),
    "commerce": DomainMeta(
        domain_id="commerce",
        filename="commerce.yaml",
        title="商业化",
        risk="balance",
        description="会员档/天道商店/沙盒（M7 L8）",
        enabled=True,
        category_id="social",
        category_title_zh="社交经济",
        category_order=55,
    ),
    "map": DomainMeta(
        domain_id="map",
        filename="map.yaml",
        title="地图区域",
        risk="content",
        description="区域占位（对齐 M9）；遭遇 region_id 外键",
        enabled=True,
        category_id="content",
        category_title_zh="内容与设施",
        category_order=60,
    ),
    "activity": DomainMeta(
        domain_id="activity",
        filename="activity.yaml",
        title="活动开关",
        risk="facility",
        description="限时活动占位开关（ADM-10 最小）",
        enabled=True,
        category_id="content",
        category_title_zh="内容与设施",
        category_order=60,
    ),
    "avatar": DomainMeta(
        domain_id="avatar",
        filename="avatar.yaml",
        title="化身",
        risk="balance",
        description="单化身功能解锁、互传折扣、体力/日行动、挂机速率",
        enabled=True,
        category_id="growth",
        category_title_zh="成长数值",
        category_order=40,
    ),
    "dao": DomainMeta(
        domain_id="dao",
        filename="dao.yaml",
        title="大道",
        risk="content",
        description="道目录样本、开道门槛、道值曲线与运用占位",
        enabled=True,
        category_id="dao",
        category_title_zh="大道与道主",
        category_order=10,
    ),
    "dao_restraint": DomainMeta(
        domain_id="dao_restraint",
        filename="dao_restraint.yaml",
        title="大道克制",
        risk="balance",
        description="上位克制样本矩阵",
        enabled=True,
        category_id="dao",
        category_title_zh="大道与道主",
        category_order=10,
    ),
    "dao_lord": DomainMeta(
        domain_id="dao_lord",
        filename="dao_lord.yaml",
        title="道主",
        risk="balance",
        description="道主门槛、冷却、特权与道主之争赛会日程（报名/开打时刻）",
        enabled=True,
        category_id="dao",
        category_title_zh="大道与道主",
        category_order=10,
    ),
    "world_events": DomainMeta(
        domain_id="world_events",
        filename="world_events.yaml",
        title="世界事件",
        risk="facility",
        description="世界 Boss / 秘境开窗骨架",
        enabled=True,
        category_id="dao",
        category_title_zh="大道与道主",
        category_order=10,
    ),
}


def list_domains(*, include_disabled: bool = True) -> list[DomainMeta]:
    """
    列出已登记内容域。

    Args:
        include_disabled: 是否包含尚未落地 YAML 的占位域。

    Returns:
        list[DomainMeta]: 域元数据列表。
    """
    items = list(DOMAIN_REGISTRY.values())
    if not include_disabled:
        items = [item for item in items if item.enabled]
    return items


def get_domain_meta(domain_id: str) -> DomainMeta | None:
    """按域 ID 取元数据；不存在返回 None。"""
    return DOMAIN_REGISTRY.get(domain_id)


def filename_for_domain(domain_id: str) -> str | None:
    """域 ID → YAML 文件名。"""
    meta = get_domain_meta(domain_id)
    return meta.filename if meta else None


def domain_id_for_filename(filename: str) -> str | None:
    """
    YAML 文件名 → 域 ID（供 ``realm_config`` 合并覆盖层）。

    Args:
        filename: 如 ``pets.yaml``。

    Returns:
        str | None: 域 ID；未登记则 None（仅 YAML，无覆盖）。
    """
    for meta in DOMAIN_REGISTRY.values():
        if meta.filename == filename:
            return meta.domain_id
    return None
