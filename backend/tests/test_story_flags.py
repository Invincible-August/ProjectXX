"""剧情 flag 读写测试（M5 D11）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.models import User
from app.domain.reincarnation_rules import (
    dump_story_flags,
    mark_story_node,
    parse_story_flags,
)
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.services import auth_service, character_service
from app.services.gm_service import GmService
from app.services.realm_config import clear_game_config_cache
from app.services.reincarnation_service import ReincarnationService
from tests.async_db import open_test_session_factory, run_async as _run


@pytest.fixture(autouse=True)
def _cfg(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "gm_enabled", True)
    clear_game_config_cache()
    yield
    clear_game_config_cache()


def test_parse_mark_story_flags() -> None:
    """flag 解析与幂等标记。"""
    flags = parse_story_flags(None)
    mark_story_node(flags, "intro_1")
    mark_story_node(flags, "intro_1")
    assert flags["experienced_nodes"] == ["intro_1"]
    raw = dump_story_flags(flags)
    again = parse_story_flags(raw)
    assert again["experienced_nodes"] == ["intro_1"]


def test_story_flags_survive_reincarnation(tmp_path: Path) -> None:
    """轮回保留 experienced_nodes。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "story.db") as factory:
            async with factory() as session:
                await auth_service.register_user(
                    session,
                    RegisterRequest(password="password123", email="story@example.com"),
                )
                await session.commit()
                user = (
                    await session.execute(select(User).where(User.email == "story@example.com"))
                ).scalar_one()
                await character_service.create_character(
                    session,
                    user,
                    CreateCharacterRequest(name="剧情旗"),
                )
                await session.commit()
                await GmService(session).gm_set_character(
                    user,
                    mark_story_node="chapter_1_boss",
                    spirit_stones=5000,
                )
                await session.commit()
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                flags = parse_story_flags(character.story_flags_json)
                assert "chapter_1_boss" in flags["experienced_nodes"]

                character.major_realm = "huashen"
                character.peak_major_realm = "huashen"
                character.spirit_stones = 5000
                await session.commit()
                await ReincarnationService(session).altar(user)
                await session.commit()
                await session.refresh(character)
                flags2 = parse_story_flags(character.story_flags_json)
                assert "chapter_1_boss" in flags2["experienced_nodes"]
                assert flags2.get("first_tribulation_done") is False

    _run(_body())
