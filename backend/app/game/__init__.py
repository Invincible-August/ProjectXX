"""
游戏实体 OOP 层（ARCH-R01）。

养成门面与契约；战斗纯度仍在 ``app.domain.autochess``。
配置读取经 ``app.game.content_store``（测试 YAML / 正式可 DB）。
"""

from __future__ import annotations

from app.game.ability import AbilityDef, AbilityInstance, SimpleGrantSource, expand_grants
from app.game.battle import BattleUnitSeed
from app.game.character import (
    AvatarCharacter,
    Character,
    CultivatorCharacter,
    DivineSenseConsumer,
    MonsterCharacter,
    NpcCharacter,
    PetCharacter,
    PlayerCharacter,
    PlayerNpcCharacter,
    PuppetCharacter,
    SenseMinionCharacter,
)
from app.game.content_store import ContentStore, load_domain
from app.game.item import EquipmentItem, GenericItem, PuppetItem
from app.game.taxonomy import (
    ContentEntity,
    EnvironmentEntity,
    LawEntity,
    OrganizationEntity,
)

__all__ = [
    "Character",
    "CultivatorCharacter",
    "PlayerNpcCharacter",
    "PlayerCharacter",
    "NpcCharacter",
    "DivineSenseConsumer",
    "SenseMinionCharacter",
    "AvatarCharacter",
    "PetCharacter",
    "PuppetCharacter",
    "MonsterCharacter",
    "EquipmentItem",
    "GenericItem",
    "PuppetItem",
    "AbilityDef",
    "AbilityInstance",
    "SimpleGrantSource",
    "expand_grants",
    "BattleUnitSeed",
    "ContentStore",
    "load_domain",
    "ContentEntity",
    "LawEntity",
    "EnvironmentEntity",
    "OrganizationEntity",
]
