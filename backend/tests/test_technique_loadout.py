"""功法装备栏与灵根展示口子。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.constants.technique import (
    DEFAULT_SPIRIT_ROOT,
    TECHNIQUE_SLOT_ART,
    TECHNIQUE_SLOT_MAIN,
    TECHNIQUE_SOURCE_SYSTEM,
)
from app.core.config import get_settings
from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.realm_config import clear_game_config_cache, get_game_config
from app.services.technique_service import TechniqueService
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


def test_technique_yaml_has_loadout_and_elements() -> None:
    cfg = get_game_config()
    assert cfg.technique_loadout.main_slots == 1
    assert cfg.technique_loadout.art_slots_by_major["body_tempering"] == 1
    qi = cfg.techniques["basic_qi_art"]
    assert "wood" in qi.elements
    assert qi.skills_main[0].label_zh == "吐纳"


def test_create_character_has_spirit_root_and_technique_board(tmp_path: Path) -> None:
    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "tech_board.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "techboard@example.com", "功法栏测")
                character = await character_service.get_character_by_user_id(
                    session,
                    user.id,
                )
                assert character is not None
                public = await character_service.enrich_character_public(session, character)
                assert DEFAULT_SPIRIT_ROOT in public.spirit_root_tags
                assert public.spirit_roots[0]["label_zh"] == "杂灵根"
                svc = TechniqueService(session)
                page = await svc.get_techniques_page(character)
                mains = [s for s in page["loadout"]["slots"] if s["slot_type"] == TECHNIQUE_SLOT_MAIN]
                arts = [s for s in page["loadout"]["slots"] if s["slot_type"] == TECHNIQUE_SLOT_ART]
                assert len(mains) == 1
                assert len(arts) == 1
                assert any(it["id"] == "basic_qi_art" for it in page["items"])
                assert any(it["source"] == TECHNIQUE_SOURCE_SYSTEM for it in page["items"])

                page = await svc.equip_technique(
                    character,
                    technique_id="basic_qi_art",
                    slot_type=TECHNIQUE_SLOT_ART,
                    slot_index=0,
                )
                assert page["loadout"]["slots"][0]["technique_id"] is None
                arts_after = [
                    s for s in page["loadout"]["slots"] if s["slot_type"] == TECHNIQUE_SLOT_ART
                ]
                assert arts_after[0]["technique_id"] == "basic_qi_art"

                page = await svc.equip_technique(
                    character,
                    technique_id="basic_qi_art",
                    slot_type=TECHNIQUE_SLOT_MAIN,
                    slot_index=0,
                )
                assert page["loadout"]["slots"][0]["technique_id"] == "basic_qi_art"
                assert page["loadout"]["granted_skills"]
                assert page["loadout"]["granted_skills"][0]["label_zh"] == "吐纳"

                page = await svc.equip_technique(
                    character,
                    technique_id="thunder_breath_art",
                    slot_type=TECHNIQUE_SLOT_ART,
                    slot_index=0,
                )
                names = {s["id"] for s in page["loadout"]["granted_skills"]}
                assert "qi_breath" in names
                assert "thunder_spark" in names

                with pytest.raises(AppError):
                    await svc.equip_technique(
                        character,
                        technique_id="iron_body_art",
                        slot_type=TECHNIQUE_SLOT_ART,
                        slot_index=1,
                    )

                page = await svc.unequip_technique(
                    character,
                    slot_type=TECHNIQUE_SLOT_MAIN,
                    slot_index=0,
                )
                assert page["loadout"]["slots"][0]["technique_id"] is None
                skill_ids = {s["id"] for s in page["loadout"]["granted_skills"]}
                assert "qi_breath" not in skill_ids

    _run(_body())
