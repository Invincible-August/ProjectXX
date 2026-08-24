"""
后台「角色管理」协议常量（开发计划 §0.6.3 / §0.0.1）。

角色运营与账号管理同属「玩家管理」；仙缘不在此改（账号绑定）。
"""

from __future__ import annotations

from typing import Any

from app.constants.character import (
    CHARACTER_STATUS_ADMIN_CHOICES,
    CHARACTER_STATUS_LABEL_ZH,
    CRAFT_BRANCH_LABEL_ZH,
    CRAFT_BRANCHES,
)
from app.constants.combat_attrs import LIFE_KEYS, PRIMARY_KEYS
from app.services.admin_field_schema import FieldMeta, SheetMeta

# 角色列表 / 明细分页
CHARACTER_PAGE_SIZES: tuple[int, ...] = (10, 20, 50, 100)
CHARACTER_DEFAULT_PAGE_SIZE = 20

# 审计 domain_id
AUDIT_DOMAIN_PLAYER_CHARACTERS = "player_characters"

# 角色侧可改货币（不含仙缘 fate_luck）
CURRENCY_SPIRIT_STONES = "spirit_stones"  # 灵石
CURRENCY_TIANDAO_POINTS = "tiandao_points"  # 天道点（角色字段）
CURRENCY_REINCARNATION_POINTS = "reincarnation_points"  # 轮回点

# API / 流水币种键（天道点流水用 tiandao_point）
CHARACTER_CURRENCY_DEFS: tuple[dict[str, str], ...] = (
    {
        "key": CURRENCY_SPIRIT_STONES,
        "ledger_key": "spirit_stones",
        "label_zh": "灵石",
        "help_zh": "characters.spirit_stones；整数 ≥ 0",
    },
    {
        "key": CURRENCY_TIANDAO_POINTS,
        "ledger_key": "tiandao_point",
        "label_zh": "天道点",
        "help_zh": "characters.tiandao_points；整数 ≥ 0",
    },
    {
        "key": CURRENCY_REINCARNATION_POINTS,
        "ledger_key": "reincarnation_point",
        "label_zh": "轮回点",
        "help_zh": "characters.reincarnation_points；整数 ≥ 0",
    },
)

# 运营可改的基础属性键（growth_attrs / 主键；不含功法装备加算）
BASE_ATTR_EDIT_KEYS: tuple[str, ...] = PRIMARY_KEYS + (
    "physique",
    "resist_heart_demon",
    "resist_tribulation",
    "breath_efficiency",
    "endurance",
    "craft_dexterity",
    "precision",
    "temperament",
)

BASE_ATTR_LABEL_ZH: dict[str, str] = {
    "strength": "力量",
    "agility": "敏捷",
    "intelligence": "智力",
    "comprehension": "悟性",
    "bone_root": "根骨",
    "physique": "体魄",
    "resist_heart_demon": "心魔抗性",
    "resist_tribulation": "天劫抗性",
    "breath_efficiency": "吐纳效率",
    "endurance": "耐力",
    "craft_dexterity": "炼器灵巧",
    "precision": "精密",
    "temperament": "心性",
}

# 列表网格列
CHARACTER_LIST_COLUMNS: tuple[FieldMeta, ...] = (
    FieldMeta("id", "角色ID", "characters 表自增主键", "int"),
    FieldMeta("name", "道号", "全服唯一道号", "string"),
    FieldMeta("user_db_id", "账号数据库ID", "users.id", "int"),
    FieldMeta("user_id", "user_id", "对外账号号 M/P/T/G+7位", "string"),
    FieldMeta("major_realm", "大境界", "修为大道境界机读键", "string"),
    FieldMeta("realm_stage", "小境界", "当前层/期序号", "int"),
    FieldMeta("body_temper_stage", "炼体大境", "炼体大道机读键", "string"),
    FieldMeta("status", "状态", "条件状态或待引渡等系统态", "string"),
    FieldMeta("status_label_zh", "状态中文", "状态中文展示", "string"),
    FieldMeta("spirit_stones", "灵石", "持有灵石", "int"),
    FieldMeta("is_active", "是否有效", "False=软删", "bool"),
)

# 给予道具表单
GRANT_ITEM_FIELDS: tuple[FieldMeta, ...] = (
    FieldMeta(
        "item_id",
        "物品种类ID",
        "配置表 item_id（种类）；领取后生成独立实例 uid",
        "string",
    ),
    FieldMeta("quantity", "数量", "正整数；唯一物强制为 1", "int"),
    FieldMeta("note", "备注", "可选；写入邮件正文", "null_str"),
)


def build_character_ops_schema() -> dict[str, Any]:
    """
    角色运营中文字段契约。

    Returns:
        dict: 供 ``GET /admin/ops/characters/schema`` 返回。
    """
    status_options = [
        {
            "value": key,
            "label_zh": CHARACTER_STATUS_LABEL_ZH.get(key, key),
        }
        for key in CHARACTER_STATUS_ADMIN_CHOICES
    ]
    craft_branches = [
        {
            "value": b,
            "label_zh": CRAFT_BRANCH_LABEL_ZH.get(b, b),
        }
        for b in CRAFT_BRANCHES
    ]
    base_attrs = [
        {
            "key": k,
            "label_zh": BASE_ATTR_LABEL_ZH.get(k, k),
            "help_zh": "基础值（不含功法/装备加算）；写入 growth_attrs_json",
            "value_type": "number",
        }
        for k in BASE_ATTR_EDIT_KEYS
    ]
    sheets = (
        SheetMeta(
            sheet_id="characters",
            title_zh="角色列表",
            description_zh="玩家角色检索网格",
            columns=CHARACTER_LIST_COLUMNS,
            primary_keys=("id",),
        ),
    )
    return {
        "module_id": "player_characters",
        "title_zh": "玩家管理 · 角色管理",
        "description_zh": (
            "运行时角色干预（非配置 Overlay）。"
            "通用：删除(软删)/死亡(待引渡)/轮回/修为突破/炼体突破/给予；"
            "独立：属性/状态/背包/功法/境界/制造业/货币/体质。"
            "仙缘在账号管理派发，本页不改。"
        ),
        "page_sizes": list(CHARACTER_PAGE_SIZES),
        "default_page_size": CHARACTER_DEFAULT_PAGE_SIZE,
        "status_options": status_options,
        "craft_branches": craft_branches,
        "currencies": list(CHARACTER_CURRENCY_DEFS),
        "base_attr_fields": base_attrs,
        "life_attr_keys": list(LIFE_KEYS),
        "forms": {
            "grant_item": [f.to_dict() for f in GRANT_ITEM_FIELDS],
        },
        "sheets": [s.to_dict() for s in sheets],
        "note_zh": (
            "删除将 is_active 置为 false（非物理删除）；"
            "死亡写入 awaiting_ferry；给予经系统邮件投递物品种类 id。"
        ),
    }
