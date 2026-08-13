"""
ATTR-D01：统一战斗/生活属性 schema 与叠层。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import User
from app.domain.combat import (
    AdditiveSource,
    CombatAttrAssembleInput,
    CombatCalculator,
    assemble_combat_attr_block,
    assemble_life_attr_block,
    engine_unit_core_from_final,
    map_primary_deltas,
    public_combat_final_summary,
)
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.services import auth_service, character_service
from app.services.character_service import CharacterService
from app.services.realm_config import clear_game_config_cache, get_game_config
from tests.async_db import open_test_session_factory, run_async as _run


@pytest.fixture(autouse=True)
def _cfg(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    monkeypatch.setattr(settings, "app_env", "development")
    clear_game_config_cache()
    yield
    clear_game_config_cache()


async def _prepare(session: AsyncSession, email: str, name: str) -> User:
    await auth_service.register_user(
        session,
        RegisterRequest(password="password123", email=email),
    )
    await session.commit()
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    await character_service.create_character(
        session,
        user,
        CreateCharacterRequest(name=name, gender="male"),
    )
    await session.commit()
    return user


def test_combat_attrs_config_loads() -> None:
    """combat_attrs.yaml 可加载且含核心键。"""
    cfg = get_game_config().combat_attrs
    assert cfg.schema_version >= 2
    assert "phys_atk" in cfg.attrs
    assert cfg.attrs["phys_atk"].label_zh == "物理攻击"
    assert cfg.aliases.get("atk") == "phys_atk"
    assert "equipment" in cfg.channels
    assert cfg.channels["equipment"]["enabled"] is False


def test_assemble_block_matches_legacy_calculator() -> None:
    """叠层与 CombatCalculator 在主键映射为 0 时数值一致。"""
    stats = CombatCalculator.compute(
        base_atk=10,
        base_hp=100,
        grade_atk_mul=1.2,
        grade_hp_mul=1.2,
        technique_atk=2,
        technique_hp=5,
        constitution_atk=1,
        constitution_hp=3,
    )
    block = assemble_combat_attr_block(
        CombatAttrAssembleInput(
            realm_phys_atk=10,
            realm_hp=100,
            realm_speed=8,
            rein_mult=1.0,
            grade_atk_mul=1.2,
            grade_hp_mul=1.2,
            technique_phys_atk=2,
            technique_hp=5,
            constitution_phys_atk=1,
            constitution_hp=3,
            primary={"strength": 10},
            primary_map={"strength": {"phys_atk": 0.0}},
            defaults={
                "phys_def": 0,
                "magic_atk": 0,
                "magic_def": 0,
                "mp": 0,
                "hit": 0,
                "dodge": 0,
            },
            labels={"phys_atk": "物理攻击", "hp": "生命"},
            channels={"equipment": {"enabled": False, "label_zh": "装备"}},
        ),
    )
    assert block["final"]["phys_atk"] == stats.atk
    assert block["final"]["hp"] == stats.hp
    assert block["final"]["atk"] == stats.atk
    assert any(
        b.get("source") == "equipment" and b.get("enabled") is False
        for b in block["breakdown"]
    )


def test_primary_map_adds_when_coeff_nonzero() -> None:
    """主键映射系数非 0 时加算进 final。"""
    deltas = map_primary_deltas(
        {"strength": 10, "intelligence": 8},
        {"strength": {"phys_atk": 0.5}, "intelligence": {"magic_atk": 0.5}},
    )
    assert deltas["phys_atk"] == pytest.approx(5.0)
    assert deltas["magic_atk"] == pytest.approx(4.0)


def test_additive_source_and_public_summary() -> None:
    """AdditiveSource 加算 + 对外摘要键与 schema 一致。"""
    block = assemble_combat_attr_block(
        CombatAttrAssembleInput(
            realm_phys_atk=10,
            realm_hp=100,
            realm_speed=8,
            rein_mult=1.0,
            grade_atk_mul=1.0,
            grade_hp_mul=1.0,
            additive_sources=(
                AdditiveSource(
                    source_id="equipment",
                    label_zh="装备",
                    amounts={"phys_atk": 3, "magic_atk": 2},
                    enabled=True,
                ),
            ),
            defaults={"magic_atk": 0, "phys_def": 0, "magic_def": 1, "mp": 0, "hit": 0, "dodge": 0},
            labels={"phys_atk": "物理攻击", "magic_atk": "法术攻击"},
        ),
    )
    assert block["final"]["phys_atk"] == 13
    assert block["final"]["magic_atk"] == 2
    summary = public_combat_final_summary(block["final"])
    assert set(summary) == {
        "phys_atk",
        "magic_atk",
        "hp",
        "phys_def",
        "magic_def",
        "speed",
    }
    assert "mag_atk" not in summary
    core = engine_unit_core_from_final(block["final"])
    assert core["atk"] == core["phys_atk"] == 13


def test_life_block_keys() -> None:
    """生活块含体力/吐纳等键。"""
    life = assemble_life_attr_block(
        values={
            "comprehension": 3,
            "stamina": 120,
            "resist_heart_demon": 0,
            "resist_tribulation": 0,
            "breath_efficiency": 1.0,
            "endurance": 0,
            "craft_dexterity": 0,
            "precision": 0,
            "temperament": 0,
        },
        labels={"stamina": "体力", "breath_efficiency": "吐纳效率"},
    )
    assert life["final"]["stamina"] == 120
    assert life["final"]["breath_efficiency"] == 1.0
    assert life["labels"]["stamina"] == "体力"


def test_build_combat_attrs_on_character(tmp_path: Path) -> None:
    """角色面板含 combat/life，且 base_atk 与 phys_atk 一致。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "attr.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "attr01@example.com", "属性测")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                public = await CharacterService(session).enrich_public(character)
                assert public.combat is not None
                assert public.life is not None
                assert public.combat["final"]["phys_atk"] == public.base_atk
                assert public.combat["final"]["hp"] == public.base_hp
                assert "phys_atk" in public.combat["final"]
                assert "stamina" in public.life["final"]
                assert any(
                    row.get("source") == "realm"
                    for row in public.combat.get("breakdown", [])
                )
                packed = await CharacterService(session).build_combat_attrs(character)
                assert packed["combat"]["final"]["atk"] == packed["combat"]["final"]["phys_atk"]

    _run(_body())
