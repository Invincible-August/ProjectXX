"""神通装备栏口子：神通池选装，格数=修为基数+品阶。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.services import auth_service, character_service
from app.services.divine_ability_service import DivineAbilityService, compute_divine_ability_slot_cap
from app.services.realm_config import clear_game_config_cache, get_game_config
from tests.async_db import open_test_session_factory, run_async as _run


@pytest.fixture(autouse=True)
def _cfg(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    monkeypatch.setattr(settings, "app_env", "development")
    clear_game_config_cache()
    yield
    clear_game_config_cache()


async def _prepare(session, email: str, name: str) -> User:
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


def test_divine_yaml_has_samples() -> None:
    cfg = get_game_config()
    assert "thunder_finger" in cfg.divine_abilities
    assert cfg.divine_abilities["thunder_finger"].name == "雷指"
    assert cfg.divine_ability_loadout.slots_by_major["body_tempering"] == 1
    assert cfg.divine_ability_loadout.slots_by_major["jindan"] == 2


def test_create_character_pool_and_equip_grows_with_realm_and_grade(tmp_path: Path) -> None:
    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "divine_board.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "divine@example.com", "神通栏测")
                character = await character_service.get_character_by_user_id(
                    session,
                    user.id,
                )
                assert character is not None
                svc = DivineAbilityService(session)
                page = await svc.get_page(character)
                assert any(it["id"] == "thunder_finger" for it in page["items"])
                assert page["loadout"]["realm_slots"] == 1
                assert page["loadout"]["grade_slots"] == 0
                assert page["loadout"]["slot_cap"] == 1
                assert len(page["loadout"]["slots"]) == 1

                page = await svc.equip_ability(
                    character,
                    ability_id="thunder_finger",
                    slot_index=0,
                )
                assert page["loadout"]["slots"][0]["ability_id"] == "thunder_finger"
                assert page["loadout"]["slots"][0]["name"] == "雷指"
                assert page["loadout"]["slots"][0]["label_zh"] == "神通一"

                character.major_realm = "jindan"
                await session.flush()
                assert compute_divine_ability_slot_cap(character) == 2
                page = await svc.get_page(character)
                assert page["loadout"]["slot_cap"] == 2
                assert page["loadout"]["slots"][0]["ability_id"] == "thunder_finger"

                page = await svc.equip_ability(
                    character,
                    ability_id="iron_body_seal",
                    slot_index=1,
                )
                ids = {s["ability_id"] for s in page["loadout"]["slots"]}
                assert ids == {"thunder_finger", "iron_body_seal"}

                character.divine_ability_slots = 2
                await session.flush()
                page = await svc.get_page(character)
                assert page["loadout"]["realm_slots"] == 2
                assert page["loadout"]["grade_slots"] == 2
                assert page["loadout"]["slot_cap"] == 4

                page = await svc.equip_ability(
                    character,
                    ability_id="thunder_finger",
                    slot_index=1,
                )
                assert page["loadout"]["slots"][0]["ability_id"] is None
                assert page["loadout"]["slots"][1]["ability_id"] == "thunder_finger"

                page = await svc.unequip_ability(character, slot_index=1)
                assert page["loadout"]["slots"][1]["ability_id"] is None
                assert compute_divine_ability_slot_cap(character) == 4

    _run(_body())
