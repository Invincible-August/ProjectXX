"""ARCH-R01：实体 ABC / Ability / ContentStore 契约单测。"""

from __future__ import annotations

import pytest

from app.game.ability import AbilityDef, SimpleGrantSource, expand_grants
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
from app.game.content_store import ContentStore
from app.game.item import EquipmentItem, PuppetItem


def test_character_abc_cannot_instantiate() -> None:
    """Character 为抽象类，不可直接实例化。"""
    with pytest.raises(TypeError):
        Character()  # type: ignore[abstract,call-arg]


def test_cultivator_abc_cannot_instantiate() -> None:
    """CultivatorCharacter 为修士子基类，不可直接实例化。"""
    with pytest.raises(TypeError):
        CultivatorCharacter()  # type: ignore[abstract,call-arg]


def test_player_character_battle_seed() -> None:
    """PlayerCharacter.on_battle_enter 产出兼容 setup 的种子。"""

    class _Row:
        id = 7
        name = "测道友"
        status = "idle"

    pc = PlayerCharacter.from_orm(
        _Row(),
        attr_block={
            "combat": {
                "final": {"hp": 100, "phys_atk": 12, "speed": 15, "mp": 0},
            },
        },
    )
    assert pc.get_entity_kind() == "player"
    assert pc.get_piece_kind() == "main"
    assert pc.phys_atk == 12
    assert pc.hp == 100
    assert pc.mp == 0
    assert isinstance(pc, PlayerNpcCharacter)
    assert isinstance(pc, CultivatorCharacter)
    assert pc.can_enter_dao_lordship() is True
    assert pc.can_enter_reincarnation_realm() is True
    assert pc.divine_sense_capacity == 0
    assert pc.can_be_deployed() is True
    seed = pc.on_battle_enter(unit_uid="u1", side="attacker", x=1, y=2)
    assert isinstance(seed, BattleUnitSeed)
    unit = seed.to_setup_unit()
    assert unit["unit_kind"] == "main"
    assert unit["phys_atk"] == 12
    assert unit["x"] == 1


def test_pet_avatar_puppet_monster_kinds() -> None:
    """各行动体 piece/entity kind 对齐布阵约定。"""

    class _Pet:
        id = 3
        species_id = "fox"
        nickname = "小狐"

    pet = PetCharacter.from_orm(
        _Pet(),
        stats={"hp": 20, "phys_atk": 5, "speed": 8, "mp": 4},
        divine_sense_cost=3,
    )
    assert pet.get_piece_kind() == "pet"
    assert pet.display_name == "小狐"
    assert isinstance(pet, SenseMinionCharacter)
    assert pet.divine_sense_cost == 3
    assert pet.mp == 4

    puppet = PuppetCharacter(
        def_id="puppet_wood_v1",
        stats={"hp": 10, "atk": 3, "mp": 0},
        ephemeral=True,
    )
    assert puppet.get_entity_kind() == "puppet"
    assert puppet.ephemeral is True
    assert puppet.phys_atk == 3
    assert isinstance(puppet, SenseMinionCharacter)
    assert puppet.divine_sense_cost == 0

    live_puppet = PuppetCharacter(
        def_id="puppet_wood_v1",
        stats={"hp": 10, "atk": 3},
        ephemeral=False,
        divine_sense_cost=2,
    )
    assert live_puppet.divine_sense_cost == 2

    mon = MonsterCharacter.from_template(
        "wolf_1",
        {"label_zh": "野狼", "stats": {"hp": 30, "phys_atk": 8, "mp": 2}},
    )
    assert mon.display_name == "野狼"
    assert mon.mp == 2
    assert not isinstance(mon, PlayerNpcCharacter)
    assert mon.on_battle_enter(unit_uid="m1", side="defender", x=0, y=0).unit_kind == "monster"


def test_player_npc_sense_pool_from_minions() -> None:
    """玩家/NPC 继承神识池；上阵化身/宠/傀累加占用。"""

    class _Row:
        id = 1
        name = "宿主"
        status = "idle"

    class _Avatar:
        id = 9
        name = "分身"
        status = "idle"
        major_realm = "jindan"
        realm_stage = 1
        realm_progress = 0

    class _Pet:
        id = 3
        species_id = "fox"
        nickname = "小狐"

    host = PlayerCharacter.from_orm(_Row(), divine_sense_capacity=12)
    npc = NpcCharacter.from_template(
        "npc_1",
        {
            "label_zh": "执事",
            "stats": {"hp": 40, "phys_atk": 6},
            "divine_sense_capacity": 8,
            "spirit_root_tags": ["water_root"],
        },
    )
    assert isinstance(npc, PlayerNpcCharacter)
    assert not isinstance(npc, MonsterCharacter)
    assert npc.divine_sense_capacity == 8
    assert npc.mp == 0
    assert npc.spirit_root_tags == ["water_root"]

    avatar = AvatarCharacter.from_orm(_Avatar(), stats={"hp": 10}, divine_sense_cost=5)
    pet = PetCharacter.from_orm(_Pet(), stats={"hp": 8}, divine_sense_cost=3)
    puppet = PuppetCharacter(def_id="p1", stats={"hp": 6}, divine_sense_cost=2)
    assert isinstance(avatar, CultivatorCharacter)
    assert isinstance(avatar, DivineSenseConsumer)
    assert not isinstance(avatar, SenseMinionCharacter)
    assert not isinstance(avatar, PlayerNpcCharacter)
    assert avatar.can_enter_dao_lordship() is False
    assert avatar.can_enter_reincarnation_realm() is False
    assert avatar.get_major_realm() == "jindan"
    host.bind_deployed_minions([avatar, pet, puppet])
    assert host.divine_sense_capacity == 12
    assert host.divine_sense_load == 10


def test_expand_grants_dedup_default() -> None:
    """同 ability_id 默认不叠。"""
    a = SimpleGrantSource("equipment", "sword", ["fire_a", "shared"])
    b = SimpleGrantSource("set", "ember_2", ["shared", "set_bonus"])
    inst = expand_grants([a, b])
    ids = [i.ability_id for i in inst]
    assert ids == ["fire_a", "shared", "set_bonus"]


def test_ability_def_rejects_bad_domain() -> None:
    with pytest.raises(ValueError):
        AbilityDef.from_mapping("x", {"domain": "nope", "kind": "stat_mod"})


def test_equipment_and_puppet_item() -> None:
    eq = EquipmentItem(
        def_id="sword_ember",
        raw={"slot": "weapon_1", "stats": {"strength": 8}, "grants": ["eq_proc"]},
    )
    assert eq.slot == "weapon_1"
    src = eq.as_grant_source()
    assert src is not None
    assert src.list_ability_ids() == ["eq_proc"]

    pup = PuppetItem(def_id="puppet_wood_v1", raw={"actor_def_id": "actor_wood"})
    assert pup.actor_def_id == "actor_wood"


def test_content_store_loads_registered_domain() -> None:
    """ContentStore 能加载已登记域（YAML 底表）。"""
    assert "combat_attrs" in ContentStore.list_domains() or "realms" in ContentStore.list_domains()
    # realms 必在 registry
    raw = ContentStore.load("realms")
    assert isinstance(raw, dict)
    assert raw  # 非空底表
