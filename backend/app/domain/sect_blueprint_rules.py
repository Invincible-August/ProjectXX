"""宗门图纸类型契约（M8 R5 / M7-D06）：manual + manual_kind，不发明战斗属性。"""

from __future__ import annotations

from typing import Final

from app.constants.inventory import ItemType, ManualKind

# 工坊分支 → 可捐赠/兑换的 manual_kind
WORKSHOP_BRANCH_MANUAL_KIND: Final[dict[str, str]] = {
    "smithing": ManualKind.FORGE_BLUEPRINT,
    "alchemy": ManualKind.ALCHEMY_FORMULA,
    "talisman": ManualKind.TALISMAN_BLUEPRINT,
    "array": ManualKind.FORMATION_BLUEPRINT,
    "puppet": ManualKind.PUPPET_BLUEPRINT,
}

# 配方 branch → 工坊 branch（puppet 归服务工坊 talisman 页时仍用 puppet_blueprint 种类）
CRAFT_BRANCH_TO_WORKSHOP: Final[dict[str, str]] = {
    "smithing": "smithing",
    "alchemy": "alchemy",
    "talisman": "talisman",
    "array": "array",
    "puppet": "talisman",
}

MANUAL_KIND_LABELS_ZH: Final[dict[str, str]] = {
    ManualKind.FORGE_BLUEPRINT: "锻造图纸",
    ManualKind.TALISMAN_BLUEPRINT: "符箓图纸",
    ManualKind.ALCHEMY_FORMULA: "丹方",
    ManualKind.PUPPET_BLUEPRINT: "傀儡图纸",
    ManualKind.FORMATION_BLUEPRINT: "阵盘图纸",
    ManualKind.TECHNIQUE: "功法秘籍",
    ManualKind.SKILL_BOOK: "技能书",
}


def blueprint_catalog_item_id(recipe_id: str) -> str:
    """官方兑换图纸在 inventory 中的 item_id 约定。"""
    return f"bp_{recipe_id}"


def workshop_manual_kind(branch: str) -> str | None:
    """工坊分支期望的 manual_kind；未知分支返回 None。"""
    return WORKSHOP_BRANCH_MANUAL_KIND.get(str(branch))


def recipe_branch_matches_workshop(recipe_branch: str, workshop_branch: str) -> bool:
    """配方 branch 是否可上缴到该工坊页。"""
    mapped = CRAFT_BRANCH_TO_WORKSHOP.get(str(recipe_branch), str(recipe_branch))
    return mapped == str(workshop_branch)


def manual_kind_matches_workshop(manual_kind: str, workshop_branch: str) -> bool:
    """背包图纸种类是否匹配工坊分支。"""
    expected = workshop_manual_kind(workshop_branch)
    if expected is None:
        return False
    kind = str(manual_kind)
    # 服务工坊同时接受符箓图纸与傀儡图纸
    if workshop_branch == "talisman":
        return kind in {ManualKind.TALISMAN_BLUEPRINT, ManualKind.PUPPET_BLUEPRINT}
    return kind == expected


def deposit_forbidden(
    *,
    item_type: str,
    forbidden: list[str],
    manual_kind: str | None = None,
) -> bool:
    """
    藏宝阁禁止入柜判定。

    ``forbidden`` 登记的是图纸 **manual_kind 别名**（及遗留假 item_type）；
    真背包大类为 ``manual`` 时，按 ``manual_kind`` 比对。
    """
    forbidden_set = {str(x) for x in forbidden}
    raw_type = str(item_type)
    if raw_type in forbidden_set:
        return True
    if raw_type == ItemType.MANUAL and manual_kind and str(manual_kind) in forbidden_set:
        return True
    return False
