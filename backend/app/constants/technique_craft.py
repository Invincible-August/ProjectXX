"""功法自研卡片协议：效能、卡阶段、错误码与灵根→元素映射。"""

from __future__ import annotations

from typing import Final

from app.constants.technique import (
    ELEMENT_EARTH,
    ELEMENT_FIRE,
    ELEMENT_METAL,
    ELEMENT_THUNDER,
    ELEMENT_WATER,
    ELEMENT_WIND,
    ELEMENT_WOOD,
)

ERR_CRAFT_CARD: Final[int] = 40220
ERR_CRAFT_EMBED: Final[int] = 40221
ERR_CRAFT_FINALIZE: Final[int] = 40222
ERR_CRAFT_CULTIVATE: Final[int] = 40223
ERR_CRAFT_EQUIP_ROLE: Final[int] = 40224
ERR_CRAFT_MANUAL: Final[int] = 40225
ERR_CRAFT_LEARN: Final[int] = 40226
ERR_SCRIPTURE_DONATE: Final[int] = 40227
ERR_CRAFT_ABOLISH: Final[int] = 40228

DRAFT_PHASE_EMBEDDING: Final[str] = "embedding"
DRAFT_PHASE_ABANDONED: Final[str] = "abandoned"
DRAFT_PHASE_FINALIZED: Final[str] = "finalized"

# 自研功法初始阶：一律最低阶，须逐步突破；不与人物当前大境界对齐
CRAFT_INITIAL_RANK: Final[str] = "body_tempering"

# 词条稀有度：灰→红；权重/倍率在 research.yaml technique_craft.affix_rarities（后台域 research）
AFFIX_RARITY_GRAY: Final[str] = "gray"
AFFIX_RARITY_WHITE: Final[str] = "white"
AFFIX_RARITY_GREEN: Final[str] = "green"
AFFIX_RARITY_BLUE: Final[str] = "blue"
AFFIX_RARITY_PURPLE: Final[str] = "purple"
AFFIX_RARITY_ORANGE: Final[str] = "orange"
AFFIX_RARITY_RED: Final[str] = "red"
AFFIX_RARITY_IDS: Final[tuple[str, ...]] = (
    AFFIX_RARITY_GRAY,
    AFFIX_RARITY_WHITE,
    AFFIX_RARITY_GREEN,
    AFFIX_RARITY_BLUE,
    AFFIX_RARITY_PURPLE,
    AFFIX_RARITY_ORANGE,
    AFFIX_RARITY_RED,
)
AFFIX_RARITY_DEFAULT: Final[str] = AFFIX_RARITY_WHITE

EFFICACY_SPELL_ATTACK: Final[str] = "spell_attack"
EFFICACY_SPELL_BUFF: Final[str] = "spell_buff"
EFFICACY_MARTIAL_ATTACK: Final[str] = "martial_attack"
EFFICACY_MARTIAL_BUFF: Final[str] = "martial_buff"
EFFICACY_IDLE_SPIRIT: Final[str] = "idle_spirit"
EFFICACY_IDLE_BODY: Final[str] = "idle_body"
EFFICACY_IDS: Final[tuple[str, ...]] = (
    EFFICACY_SPELL_ATTACK,
    EFFICACY_SPELL_BUFF,
    EFFICACY_MARTIAL_ATTACK,
    EFFICACY_MARTIAL_BUFF,
    EFFICACY_IDLE_SPIRIT,
    EFFICACY_IDLE_BODY,
)
IDLE_EFFICACIES: Final[frozenset[str]] = frozenset({EFFICACY_IDLE_SPIRIT, EFFICACY_IDLE_BODY})
SPELL_EFFICACIES: Final[frozenset[str]] = frozenset(
    {EFFICACY_SPELL_ATTACK, EFFICACY_SPELL_BUFF, EFFICACY_IDLE_SPIRIT},
)
MARTIAL_EFFICACIES: Final[frozenset[str]] = frozenset(
    {EFFICACY_MARTIAL_ATTACK, EFFICACY_MARTIAL_BUFF, EFFICACY_IDLE_BODY},
)
ATTACK_EFFICACIES: Final[frozenset[str]] = frozenset({EFFICACY_SPELL_ATTACK, EFFICACY_MARTIAL_ATTACK})

AFFIX_ROLE_ATTACK: Final[str] = "attack"
AFFIX_ROLE_BUFF: Final[str] = "buff"
AFFIX_ROLE_IDLE: Final[str] = "idle"
AFFIX_ROLE_DEFENSE: Final[str] = "defense"
AFFIX_ROLES: Final[frozenset[str]] = frozenset(
    {AFFIX_ROLE_ATTACK, AFFIX_ROLE_BUFF, AFFIX_ROLE_IDLE, AFFIX_ROLE_DEFENSE},
)

CARD_BLANK_ID: Final[str] = "tech_card_blank"
CARD_TYPE_ELEMENT_ID: Final[str] = "tech_card_type_element"
CARD_TYPE_EFFICACY_ID: Final[str] = "tech_card_type_efficacy"
CARD_FORMAL_ELEMENT_ID: Final[str] = "tech_card_formal_element"
CARD_FORMAL_EFFICACY_ID: Final[str] = "tech_card_formal_efficacy"
# 运营后台发放：镶嵌不消耗，固定内容
CARD_FORMAL_ELEMENT_INF_ID: Final[str] = "tech_card_formal_element_inf"
CARD_FORMAL_EFFICACY_INF_ID: Final[str] = "tech_card_formal_efficacy_inf"
CARD_MANUAL_ID: Final[str] = "tech_manual"

FORMAL_ELEMENT_CARD_IDS: Final[frozenset[str]] = frozenset(
    {CARD_FORMAL_ELEMENT_ID, CARD_FORMAL_ELEMENT_INF_ID},
)
FORMAL_EFFICACY_CARD_IDS: Final[frozenset[str]] = frozenset(
    {CARD_FORMAL_EFFICACY_ID, CARD_FORMAL_EFFICACY_INF_ID},
)
INFINITE_FORMAL_CARD_IDS: Final[frozenset[str]] = frozenset(
    {CARD_FORMAL_ELEMENT_INF_ID, CARD_FORMAL_EFFICACY_INF_ID},
)

# 管理后台「发放自研测试卡」默认内容（镶嵌不消耗）
INF_ELEMENT_CARD_META: Final[dict[str, object]] = {
    "elements": [
        ELEMENT_METAL,
        ELEMENT_WOOD,
        ELEMENT_WATER,
        ELEMENT_FIRE,
        ELEMENT_EARTH,
        ELEMENT_WIND,
        ELEMENT_THUNDER,
    ],
    "infinite_use": True,
}
INF_EFFICACY_CARD_META: Final[dict[str, object]] = {
    "efficacy": EFFICACY_IDLE_SPIRIT,
    "infinite_use": True,
}

WEAPON_LIMITS: Final[tuple[str, ...]] = (
    "sword",
    "saber",
    "spear",
    "gauntlet",
    "bow",
    "puppet",
    "avatar",
)

ROOT_TAG_TO_ELEMENTS: Final[dict[str, tuple[str, ...]]] = {
    "metal_root": (ELEMENT_METAL,),
    "wood_root": (ELEMENT_WOOD,),
    "water_root": (ELEMENT_WATER,),
    "fire_root": (ELEMENT_FIRE,),
    "earth_root": (ELEMENT_EARTH,),
    "thunder_root": (ELEMENT_THUNDER,),
    "wind_root": (ELEMENT_WIND,),
    "mixed_root": (ELEMENT_METAL, ELEMENT_WOOD, ELEMENT_WATER, ELEMENT_FIRE, ELEMENT_EARTH),
}


def element_ids_from_spirit_root_tags(tags: list[str]) -> list[str]:
    """Expand spirit-root tags into ordered unique technique element ids."""
    ordered: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        for el in ROOT_TAG_TO_ELEMENTS.get(str(tag), ()):
            if el not in seen:
                seen.add(el)
                ordered.append(el)
    return ordered
