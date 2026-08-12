"""
体质镶嵌测试（M2）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models.constitution import ConstitutionItem
from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service, constitution_service
from app.services.realm_config import clear_game_config_cache
from tests.async_db import open_test_session_factory, run_async as _run


async def _prepare(session, email: str) -> User:
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
        CreateCharacterRequest(name=email.split("@")[0][:16]),
    )
    await session.commit()
    return user


@pytest.fixture(autouse=True)
def _cfg(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    clear_game_config_cache()
    yield
    clear_game_config_cache()


def test_equip_main_affix(tmp_path: Path) -> None:
    """镶嵌主词条到主格。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "cons_equip.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "cons@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                result = await session.execute(
                    select(ConstitutionItem).where(
                        ConstitutionItem.character_id == character.id,
                        ConstitutionItem.def_id == "sample_main_affix_iron",
                    ),
                )
                item = result.scalar_one()
                state = await constitution_service.equip_constitution_item(
                    session,
                    character,
                    item_id=item.id,
                    slot_type="main",
                    slot_index=0,
                )
                await session.commit()
                assert any(s["item_id"] == item.id for s in state["slots"])

    _run(_body())


def test_equip_slot_full_40034(tmp_path: Path) -> None:
    """格满再镶嵌 → 40034。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "cons_full.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "full@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                items = (
                    await session.execute(
                        select(ConstitutionItem).where(
                            ConstitutionItem.character_id == character.id,
                            ConstitutionItem.def_id == "sample_sub_affix_swift",
                        ),
                    )
                ).scalars().all()
                assert len(items) >= 2
                await constitution_service.equip_constitution_item(
                    session,
                    character,
                    item_id=items[0].id,
                    slot_type="sub",
                    slot_index=0,
                )
                with pytest.raises(AppError) as exc_info:
                    await constitution_service.equip_constitution_item(
                        session,
                        character,
                        item_id=items[1].id,
                        slot_type="sub",
                        slot_index=0,
                    )
                assert exc_info.value.code == 40034

    _run(_body())


def test_equip_duplicate_def_blocked(tmp_path: Path) -> None:
    """同 def_id 不可装到两个副格。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "cons_dup.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "dup@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                items = (
                    await session.execute(
                        select(ConstitutionItem).where(
                            ConstitutionItem.character_id == character.id,
                            ConstitutionItem.def_id == "sample_sub_affix_swift",
                        ),
                    )
                ).scalars().all()
                assert len(items) >= 2
                await constitution_service.equip_constitution_item(
                    session,
                    character,
                    item_id=items[0].id,
                    slot_type="sub",
                    slot_index=0,
                )
                with pytest.raises(AppError) as exc_info:
                    await constitution_service.equip_constitution_item(
                        session,
                        character,
                        item_id=items[1].id,
                        slot_type="sub",
                        slot_index=1,
                    )
                assert exc_info.value.code == 40034

    _run(_body())


def test_equip_body_kind_blocked(tmp_path: Path) -> None:
    """本体类不可镶嵌主副格。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "cons_body.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "body@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                item = (
                    await session.execute(
                        select(ConstitutionItem).where(
                            ConstitutionItem.character_id == character.id,
                            ConstitutionItem.def_id == "sample_body_root",
                        ),
                    )
                ).scalar_one()
                with pytest.raises(AppError) as exc_info:
                    await constitution_service.equip_constitution_item(
                        session,
                        character,
                        item_id=item.id,
                        slot_type="main",
                        slot_index=0,
                    )
                assert exc_info.value.code == 40034

    _run(_body())
