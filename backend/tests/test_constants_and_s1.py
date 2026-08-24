"""常量包与 ARCH S1 组装烟雾测试。"""

from __future__ import annotations

from app.constants.battle import (
    BATTLE_SIDE_ATTACKER,
    MIN_COMBAT_STAT,
    PIECE_KIND_MAIN,
    PIECE_KIND_PUPPET,
)
from app.constants.m4 import IdleDirection
from app.db.models.character import Character, CharacterRow
from app.game.battle.assemble import scale_atk_hp, seed_to_engine_unit
from app.game.character import PlayerCharacter
from app.game.character.components.grants import TechniqueGrantSource


def test_m4_constants_package_authority() -> None:
    """M4 枚举权威在 app.constants.m4（S1-6 已删 domain shim）。"""
    assert IdleDirection.SPIRIT.value == "spirit"


def test_character_row_alias() -> None:
    """ORM CharacterRow 与 Character 为同一类（表名不改）。"""
    assert CharacterRow is Character


def test_scale_atk_hp_floor() -> None:
    atk, hp = scale_atk_hp(0, 0, atk_ratio=0.5, hp_ratio=0.5)
    assert atk == MIN_COMBAT_STAT
    assert hp == MIN_COMBAT_STAT


def test_seed_to_engine_unit_attacker_prefix() -> None:
    class _Row:
        id = 1
        name = "甲"
        status = "idle"

    pc = PlayerCharacter.from_orm(
        _Row(),
        attr_block={"combat": {"final": {"hp": 50, "phys_atk": 9, "speed": 11, "mp": 0}}},
        grant_sources=[TechniqueGrantSource(source_id="t1", ability_ids=[])],
    )
    assert list(pc.iter_grant_sources())[0].source_type == "technique"
    seed = pc.on_battle_enter(unit_uid="main", side="attacker", x=1, y=2)
    defaults = type(
        "D",
        (),
        {"speed": 10, "attack_range": 1, "attack_kind": "melee", "can_fly": False},
    )()
    row = seed_to_engine_unit(seed, defaults=defaults, side=BATTLE_SIDE_ATTACKER)
    assert row["uid"] == "a_main"
    assert row["kind"] == PIECE_KIND_MAIN
    assert row["atk"] == 9
    assert row["side"] == BATTLE_SIDE_ATTACKER


def test_piece_kind_puppet_constant() -> None:
    assert PIECE_KIND_PUPPET == "puppet"


def test_is_trial_puppet_uid_suffix_digits_only() -> None:
    """真傀 item_uid（puppet_wood_v1_*）不得被当成试炼木傀。"""
    from app.game.battle.assemble import is_trial_puppet_uid

    assert is_trial_puppet_uid("puppet_1") is True
    assert is_trial_puppet_uid("puppet_12") is True
    assert is_trial_puppet_uid("puppet_wood_v1_ab12") is False
    assert is_trial_puppet_uid("main") is False
