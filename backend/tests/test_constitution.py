"""
体质镶嵌测试（本源 / 旁支双效果、动态槽、收藏区）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models.constitution import ConstitutionItem, ConstitutionSlot
from app.db.models.inventory_item import InventoryItem
from app.db.models.reincarnation_bonus import CharacterReincarnationBonus
from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service, constitution_service
from app.services.grade_service import GradeService
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


def test_starter_layout_and_collection_not_inventory(tmp_path: Path) -> None:
    """创角 1 本源 + 2 旁支；体质只在收藏区，不进道具背包。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "cons_layout.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "layout@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                state = await constitution_service.get_constitution_state(session, character)
                mains = [s for s in state["slots"] if s["slot_type"] == "main"]
                subs = [s for s in state["slots"] if s["slot_type"] == "sub"]
                assert len(mains) == 1
                assert len(subs) == 2
                assert mains[0]["label_zh"] == "本源"
                assert subs[0]["label_zh"] == "旁支"
                assert state["help_zh"] == "可以通过轮回点购买更多体质槽"
                assert state["soft_cap"] == 7
                collection = state["collection"]
                assert collection
                assert {row["id"] for row in collection} == {row["id"] for row in state["backpack"]}
                inv = (
                    await session.execute(
                        select(InventoryItem).where(InventoryItem.character_id == character.id),
                    )
                ).scalars().all()
                constitution_ids = {row["def_id"] for row in collection}
                assert not any(item.item_id in constitution_ids for item in inv)

    _run(_body())


def test_equip_main_affix(tmp_path: Path) -> None:
    """任意体质可装入本源槽。"""

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
    """同 def_id 不可装到两个旁支。"""

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


def test_body_physique_can_equip_benyuan(tmp_path: Path) -> None:
    """收集到的体质（含旧 kind=body）可装入本源。"""

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
                state = await constitution_service.equip_constitution_item(
                    session,
                    character,
                    item_id=item.id,
                    slot_type="main",
                    slot_index=0,
                )
                assert any(
                    s["slot_type"] == "main" and s["item_id"] == item.id for s in state["slots"]
                )

    _run(_body())


def test_same_physique_main_vs_sub_effects(tmp_path: Path) -> None:
    """同一体质装本源与旁支走两套效果。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "cons_dual.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "dual@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                item = (
                    await session.execute(
                        select(ConstitutionItem).where(
                            ConstitutionItem.character_id == character.id,
                            ConstitutionItem.def_id == "sample_main_affix_iron",
                        ),
                    )
                ).scalar_one()
                await constitution_service.equip_constitution_item(
                    session,
                    character,
                    item_id=item.id,
                    slot_type="main",
                    slot_index=0,
                )
                main_bonus = await GradeService(session).aggregate_constitution_bonuses(character.id)
                assert int(main_bonus["hp_bonus"]) == 20
                assert int(main_bonus["atk_bonus"]) == 0

                await constitution_service.unequip_constitution_item(
                    session,
                    character,
                    slot_type="main",
                    slot_index=0,
                )
                await constitution_service.equip_constitution_item(
                    session,
                    character,
                    item_id=item.id,
                    slot_type="sub",
                    slot_index=0,
                )
                sub_bonus = await GradeService(session).aggregate_constitution_bonuses(character.id)
                assert int(sub_bonus["hp_bonus"]) == 0
                assert int(sub_bonus["atk_bonus"]) == 4

    _run(_body())


def test_bought_slots_append_pangzhi_beyond_soft_cap(tmp_path: Path) -> None:
    """轮回点购槽只加旁支；软顶 7 仍可继续买出第 8 栏。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "cons_buy.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "buy@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                bonus = (
                    await session.execute(
                        select(CharacterReincarnationBonus).where(
                            CharacterReincarnationBonus.character_id == character.id,
                        ),
                    )
                ).scalar_one()
                bonus.constitution_slots_bought = 5
                await session.flush()
                state = await constitution_service.get_constitution_state(session, character)
                mains = [s for s in state["slots"] if s["slot_type"] == "main"]
                subs = [s for s in state["slots"] if s["slot_type"] == "sub"]
                assert len(mains) == 1
                assert len(subs) == 7
                assert len(state["slots"]) == 8
                assert state["soft_cap"] == 7
                assert state["slot_count"] == 8
                rows = (
                    await session.execute(
                        select(ConstitutionSlot).where(
                            ConstitutionSlot.character_id == character.id,
                            ConstitutionSlot.slot_type == "sub",
                        ),
                    )
                ).scalars().all()
                assert len(rows) == 7

    _run(_body())
