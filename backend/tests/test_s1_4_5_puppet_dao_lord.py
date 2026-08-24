"""ARCH S1-4 傀儡双切面 + S1-5 道主 privilege 投影单测。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.dao_lord import (
    ABILITY_LORD_HEAVENLY_SKILL_SLOT,
    ABILITY_LORD_OPEN_SECRET_REALM,
    PRIVILEGE_FLAG_HEAVENLY_SKILL,
    PRIVILEGE_FLAG_OPEN_SECRET_REALM,
    PRIVILEGE_GRANTS_KEY,
)
from app.constants.inventory import ITEM_TYPE_PUPPET
from app.db.models import User
from app.db.models.puppet_actor import PuppetActor
from app.game.law.privilege import (
    has_privilege,
    normalize_privileges_payload,
    privilege_grant_sources,
)
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.services import auth_service, character_service
from app.services.formation_service import FormationService
from app.services.inventory_service import InventoryService
from app.services.puppet_service import PuppetService
from app.services.realm_config import clear_game_config_cache
from tests.async_db import open_test_session_factory, run_async as _run


@pytest.fixture(autouse=True)
def _cfg(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    monkeypatch.setattr(settings, "app_env", "development")
    clear_game_config_cache()
    yield
    clear_game_config_cache()


async def _user_with_character(session: AsyncSession, email: str) -> User:
    await auth_service.register_user(
        session,
        RegisterRequest(password="password123", email=email),
    )
    await session.commit()
    user = (await session.execute(select(User).where(User.email == email))).scalar_one()
    await character_service.create_character(
        session,
        user,
        CreateCharacterRequest(name=email.split("@")[0][:16]),
    )
    await session.commit()
    return user


def test_normalize_bool_only_fills_grants() -> None:
    """旧数据仅布尔：应投影出 grants。"""
    out = normalize_privileges_payload(
        {
            PRIVILEGE_FLAG_HEAVENLY_SKILL: True,
            PRIVILEGE_FLAG_OPEN_SECRET_REALM: False,
        },
        defaults={
            PRIVILEGE_FLAG_HEAVENLY_SKILL: False,
            PRIVILEGE_FLAG_OPEN_SECRET_REALM: False,
            PRIVILEGE_GRANTS_KEY: [],
        },
    )
    assert out[PRIVILEGE_FLAG_HEAVENLY_SKILL] is True
    assert out[PRIVILEGE_FLAG_OPEN_SECRET_REALM] is False
    assert out[PRIVILEGE_GRANTS_KEY] == [ABILITY_LORD_HEAVENLY_SKILL_SLOT]


def test_normalize_grants_only_fills_bools() -> None:
    """仅 grants：应投影布尔旗标。"""
    out = normalize_privileges_payload(
        {PRIVILEGE_GRANTS_KEY: [ABILITY_LORD_OPEN_SECRET_REALM]},
        defaults={
            PRIVILEGE_FLAG_HEAVENLY_SKILL: False,
            PRIVILEGE_FLAG_OPEN_SECRET_REALM: False,
            PRIVILEGE_GRANTS_KEY: [],
        },
    )
    assert out[PRIVILEGE_FLAG_OPEN_SECRET_REALM] is True
    assert out[PRIVILEGE_FLAG_HEAVENLY_SKILL] is False
    assert ABILITY_LORD_OPEN_SECRET_REALM in out[PRIVILEGE_GRANTS_KEY]


def test_privilege_grant_sources_and_has_flag() -> None:
    """GrantSource 与 has_privilege 查询一致。"""
    priv = normalize_privileges_payload(
        {PRIVILEGE_GRANTS_KEY: [ABILITY_LORD_HEAVENLY_SKILL_SLOT]},
    )
    sources = privilege_grant_sources(priv, dao_id="sword")
    assert len(sources) == 1
    assert sources[0].ability_ids == [ABILITY_LORD_HEAVENLY_SKILL_SLOT]
    assert has_privilege(priv, PRIVILEGE_FLAG_HEAVENLY_SKILL) is True
    assert has_privilege(priv, PRIVILEGE_FLAG_OPEN_SECRET_REALM) is False


def test_puppet_actor_bind_and_bench_ref_id(tmp_path: Path) -> None:
    """炼成/入包后 Actor 绑定；bench.ref_id = PuppetActor.id。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "s14.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "s14puppet@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                await InventoryService(session).add_item(
                    character.id,
                    item_type=ITEM_TYPE_PUPPET,
                    item_id="puppet_wood_v1",
                    quantity=1,
                )
                await session.commit()

                actors = await PuppetService(session).on_craft_granted(
                    character.id,
                    item_id="puppet_wood_v1",
                    quantity=1,
                )
                await session.commit()
                assert len(actors) == 1
                actor = actors[0]
                assert actor.def_id == "puppet_wood_v1"
                assert actor.ephemeral is False
                assert actor.inventory_item_id is not None

                from app.db.models.inventory_item import InventoryItem
                from app.services.equipment_service import EquipmentService

                inv_row = await session.get(InventoryItem, int(actor.inventory_item_id))
                assert inv_row is not None
                await EquipmentService(session).add_puppet_to_loadout(
                    character,
                    item_uid=str(inv_row.item_uid),
                )
                await session.commit()

                bench = await FormationService(session).bench_units(character)
                # 真傀 unit_uid = 背包 item_uid；须先编成才进 Bench
                real = [b for b in bench if b.get("ref_id") is not None]
                assert real, "bench 应含绑定 Actor 的真傀"
                assert int(real[0]["ref_id"]) == int(actor.id)

                row = await session.get(PuppetActor, int(actor.id))
                assert row is not None
                facade = PuppetService(session).build_character_from_actor(
                    row,
                    stats={"hp": 10, "phys_atk": 3, "speed": 5},
                )
                seed = facade.on_battle_enter(
                    unit_uid=str(real[0]["unit_uid"]),
                    side="attacker",
                    x=0,
                    y=0,
                )
                assert seed.unit_kind == "puppet"
                assert int(seed.stats.get("hp") or 0) == 10

    _run(_body())


def test_trial_puppet_not_on_formation_bench(tmp_path: Path) -> None:
    """试炼木傀不再进入阵法 Bench（须走编成板真傀）。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "s14trial.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "s14trial@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.trial_puppet_count = 1
                await session.commit()

                bench = await FormationService(session).bench_units(character)
                trials = [b for b in bench if str(b["unit_uid"]).startswith("puppet_")]
                assert not trials

    _run(_body())
