"""
宗门领域纯规则（M7 L1 · 无 IO）。

含：建宗费用校验、拜入境界门槛、祖师功能解锁、兑宠白名单。
"""

from __future__ import annotations

from typing import Any

from app.domain.reincarnation_rules import meets_min_major_realm

# 功能键中文名（玩家可见；§0.0.2）
FEATURE_LABEL_ZH: dict[str, str] = {
    "shop_basic": "基础贡献商店",
    "quests_basic": "基础宗门任务",
    "pet_exchange": "宗门兑宠",
    "secret_realm_hook": "秘境任务钩子（占位）",
}

# 成员职位中文
ROLE_LABEL_ZH: dict[str, str] = {
    "founder": "祖师",
    "leader": "宗主",
    "elder": "长老",
    "member": "弟子",
}


def feature_label_zh(feature_id: str) -> str:
    """
    将功能键译为中文展示名。

    Args:
        feature_id: 机读功能键。

    Returns:
        str: 中文名；未知键原样返回键名（避免空白）。
    """
    return FEATURE_LABEL_ZH.get(feature_id, feature_id)


def role_label_zh(role: str) -> str:
    """
    将职位键译为中文。

    Args:
        role: founder/leader/elder/member。

    Returns:
        str: 中文职位。
    """
    return ROLE_LABEL_ZH.get(role, role)


def unlocked_features_for_founder_realm(
    founder_major_realm: str,
    features_by_founder_realm: dict[str, list[str]],
    *,
    realm_chain: list[str],
) -> list[str]:
    """
    按祖师大境界累计解锁功能（取链上已达最高档并集）。

    为何并集：配置按境界档列出该档起可用功能；祖师升境后应继承低档功能。

    Args:
        founder_major_realm: 祖师当前大境界键。
        features_by_founder_realm: YAML ``features_by_founder_realm``。
        realm_chain: 大境界有序键列表（低→高）。

    Returns:
        list[str]: 去重后的功能键列表（稳定排序）。
    """
    collected: set[str] = set()
    for major_key in realm_chain:
        for feature_id in features_by_founder_realm.get(major_key, []) or []:
            collected.add(str(feature_id))
        if major_key == founder_major_realm:
            break
        # 若祖师境界不在链中，仍累计到链末（防御）
    # 祖师境界不在链上时：仅返回精确命中档
    if founder_major_realm not in realm_chain:
        for feature_id in features_by_founder_realm.get(founder_major_realm, []) or []:
            collected.add(str(feature_id))
    return sorted(collected)


def can_join_npc_sect(
    *,
    character_major_realm: str,
    join_min_realm: str,
) -> tuple[bool, str | None]:
    """
    校验拜入 NPC 宗门的境界门槛。

    Args:
        character_major_realm: 角色大境界。
        join_min_realm: 配置最低大境界。

    Returns:
        tuple: (是否可拜入, 拒绝原因中文；可拜入时原因为 None)。
    """
    if not join_min_realm:
        return True, None
    if meets_min_major_realm(character_major_realm, join_min_realm):
        return True, None
    return False, f"境界不足：须达「{join_min_realm}」方可拜入"


def can_create_sect(
    *,
    spirit_stones: int,
    create_cost: int,
) -> tuple[bool, str | None]:
    """
    校验自建宗门灵石（D2：有钱即可，无修为门槛）。

    Args:
        spirit_stones: 当前灵石。
        create_cost: 建宗费用。

    Returns:
        tuple: (是否可建, 拒绝原因)。
    """
    if int(spirit_stones) < int(create_cost):
        return False, f"灵石不足：建宗需 {create_cost} 灵石"
    return True, None


def validate_sect_name(name: str, *, max_len: int) -> tuple[bool, str | None]:
    """
    校验宗门名（中文可见；长度与非空）。

    Args:
        name: 玩家输入名。
        max_len: 最大字符数。

    Returns:
        tuple: (合法, 原因)。
    """
    cleaned = (name or "").strip()
    if not cleaned:
        return False, "宗门名不可为空"
    if len(cleaned) > max_len:
        return False, f"宗门名过长（最多 {max_len} 字）"
    return True, None


def species_allowed_for_exchange(
    species_id: str,
    whitelist: list[str],
) -> bool:
    """
    兑宠物种是否在白名单。

    Args:
        species_id: 物种 id。
        whitelist: 配置白名单。

    Returns:
        bool: 允许则为 True。
    """
    return str(species_id) in {str(x) for x in whitelist}


def shop_item_visible(item: dict[str, Any], unlocked_features: set[str]) -> bool:
    """
    商店条目是否因功能锁而可见。

    Args:
        item: 商店项配置。
        unlocked_features: 当前已解锁功能集合。

    Returns:
        bool: 可见。
    """
    require = item.get("require_feature")
    if not require:
        return True
    return str(require) in unlocked_features


def quest_assignee_allowed(quest: dict[str, Any], assignee: str) -> bool:
    """
    任务是否允许指定接取方（body / avatar）。

    Args:
        quest: 任务配置。
        assignee: ``body`` 或 ``avatar``。

    Returns:
        bool: 允许。
    """
    modes = quest.get("assignee_modes") or ["body"]
    return str(assignee) in {str(m) for m in modes}
