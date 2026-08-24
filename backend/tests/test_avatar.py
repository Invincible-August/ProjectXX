"""
M4 化身凝练测试（§10.4）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.avatar_service import AvatarService
from app.services.gm_service import GmService
from app.services.realm_config import clear_game_config_cache

from tests.async_db import open_test_session_factory, run_async as _run


async def _user_with_character(session: AsyncSession, email: str) -> User:
    """注册并创角。"""
    await auth_service.register_user(
        session,
        RegisterRequest(password="password123", email=email),
    )
    await session.commit()
    from sqlalchemy import select
    from app.db.models import User as UserModel

    result = await session.execute(select(UserModel).where(UserModel.email == email))
    user = result.scalar_one()
    await character_service.create_character(
        session,
        user,
        CreateCharacterRequest(name=email.split("@")[0][:16]),
    )
    await session.commit()
    return user


@pytest.fixture(autouse=True)
def _reload_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """重置配置缓存。"""
    clear_game_config_cache()
    yield
    clear_game_config_cache()


def test_condense_rejected_below_jindan(tmp_path: Path) -> None:
    """炼气/锻体不可凝练 → 40050。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "av1.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "av01@example.com")
                svc = AvatarService(session)
                with pytest.raises(AppError) as exc:
                    await svc.condense(user)
                assert exc.value.code == 40050

    _run(_body())


def test_condense_success_after_gm_jindan(tmp_path: Path) -> None:
    """GM 金丹后可凝练 1 个化身。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "av2.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "av02@example.com")
                await GmService(session).gm_set_character(user, force_jindan=True, spirit_stones=5000)
                await session.commit()
                svc = AvatarService(session)
                panel = await svc.condense(user)
                assert panel is not None
                assert panel["status"] == "idle"
                with pytest.raises(AppError) as exc:
                    await svc.condense(user)
                assert exc.value.code == 40051

    _run(_body())


def test_condense_recipe_and_dismiss(tmp_path: Path) -> None:
    """玩法凝练须填功法与媒介；破除后可再凝练。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "av-recipe.db") as factory:
            async with factory() as session:
                from sqlalchemy import select

                from app.db.models.character import Character
                from app.services.inventory_service import InventoryService
                from app.services.play_gate import PlayGate

                user = await _user_with_character(session, "avrecipe@example.com")
                await GmService(session).gm_set_character(
                    user,
                    force_jindan=True,
                    spirit_stones=5000,
                    cultivation_points=2000,
                )
                await session.commit()
                character = (
                    await session.execute(select(Character).where(Character.user_id == user.id))
                ).scalar_one()
                await InventoryService(session).add_item(
                    character.id,
                    item_type="material",
                    item_id="herb_spirit_grass",
                    quantity=2,
                )
                await session.commit()

                svc = AvatarService(session)
                with pytest.raises(AppError) as missing:
                    await svc.condense(
                        user,
                        require_recipe=True,
                    )
                assert missing.value.code == 40054

                panel = await svc.condense(
                    user,
                    technique_id="basic_qi_art",
                    medium_item_id="herb_spirit_grass",
                    require_recipe=True,
                )
                assert panel["status"] == "idle"
                assert panel["major_realm"] == "jindan"
                assert int(panel.get("cultivation_points") or 0) == 0
                character = await PlayGate(session).require_character(user)
                assert int(character.spirit_stones) == 4000
                assert int(character.cultivation_points) == 1500
                counts = await InventoryService(session).material_counts(character.id)
                assert counts.get("herb_spirit_grass", 0) == 1

                avatar_row = await svc.get_avatar_row(character.id)
                assert avatar_row is not None
                avatar_row.cultivation_points = 80
                await session.flush()
                dismissed = await svc.dismiss(user)
                assert dismissed["dismissed"] is True
                assert int(dismissed["transferred_cultivation"]) == 80
                character = await PlayGate(session).require_character(user)
                assert int(character.cultivation_points) == 1580
                assert await svc.get_me(character) is None

                panel2 = await svc.condense(
                    user,
                    technique_id="basic_qi_art",
                    medium_item_id="herb_spirit_grass",
                    require_recipe=True,
                )
                assert panel2["status"] == "idle"
                assert panel2["major_realm"] == "jindan"

    _run(_body())


def test_avatar_equipment_independent_of_main(tmp_path: Path) -> None:
    """本体与化身装备槽独立；对方已穿实例不进本主体背包池。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "av-gear.db") as factory:
            async with factory() as session:
                from sqlalchemy import select

                from app.db.models.character import Character
                from app.services.equipment_service import EquipmentService
                from app.services.inventory_service import InventoryService
                from app.services.play_gate import PlayGate
                from app.services.technique_service import TechniqueService

                user = await _user_with_character(session, "avgear@example.com")
                await GmService(session).gm_set_character(
                    user,
                    force_jindan=True,
                    spirit_stones=5000,
                    cultivation_points=2000,
                )
                await session.commit()
                character = (
                    await session.execute(select(Character).where(Character.user_id == user.id))
                ).scalar_one()
                inv = InventoryService(session)
                await inv.add_item(
                    character.id,
                    item_type="material",
                    item_id="herb_spirit_grass",
                    quantity=1,
                )
                await inv.add_item(
                    character.id,
                    item_type="equipment",
                    item_id="iron_sword_t1",
                    quantity=1,
                )
                await inv.add_item(
                    character.id,
                    item_type="equipment",
                    item_id="iron_sword_t1",
                    quantity=1,
                )
                await session.commit()

                svc = AvatarService(session)
                await svc.condense(
                    user,
                    technique_id="basic_qi_art",
                    medium_item_id="herb_spirit_grass",
                    require_recipe=True,
                )
                character = await PlayGate(session).require_character(user)
                eq = EquipmentService(session)
                bag = await eq.get_slots_state(character, actor="main")
                swords = [i for i in bag["bag_equipment"] if i["item_id"] == "iron_sword_t1"]
                assert len(swords) >= 2
                main_uid = swords[0]["item_uid"]
                avatar_uid = swords[1]["item_uid"]
                await eq.equip_item(character, slot="weapon_1", item_uid=main_uid, actor="main")
                await eq.equip_item(character, slot="weapon_1", item_uid=avatar_uid, actor="avatar")
                await session.commit()

                main_state = await eq.get_slots_state(character, actor="main")
                avatar_state = await eq.get_slots_state(character, actor="avatar")
                main_w1 = next(s for s in main_state["slots"] if s["slot"] == "weapon_1")
                av_w1 = next(s for s in avatar_state["slots"] if s["slot"] == "weapon_1")
                assert main_w1["item_uid"] == main_uid
                assert av_w1["item_uid"] == avatar_uid
                main_bag_uids = {i["item_uid"] for i in main_state["bag_equipment"]}
                avatar_bag_uids = {i["item_uid"] for i in avatar_state["bag_equipment"]}
                assert avatar_uid not in main_bag_uids
                assert main_uid not in avatar_bag_uids

                tech = TechniqueService(session)
                await tech.equip_technique(
                    character,
                    technique_id="basic_qi_art",
                    slot_type="main",
                    slot_index=0,
                    actor="main",
                )
                main_page = await tech.get_techniques_page(character, actor="main")
                av_page = await tech.get_techniques_page(character, actor="avatar")
                assert any(it["id"] == "basic_qi_art" for it in main_page["items"])
                assert all(it["id"] != "basic_qi_art" for it in av_page["items"])

                main_mods, _, _, _ = await eq.aggregate_equipped_modifiers(
                    character.id,
                    actor="main",
                )
                avatar_mods, _, _, _ = await eq.aggregate_equipped_modifiers(
                    character.id,
                    actor="avatar",
                )
                assert main_mods
                assert avatar_mods
                await eq.unequip_slot(character, slot="weapon_1", actor="main")
                main_after, _, _, _ = await eq.aggregate_equipped_modifiers(
                    character.id,
                    actor="main",
                )
                avatar_after, _, _, _ = await eq.aggregate_equipped_modifiers(
                    character.id,
                    actor="avatar",
                )
                assert main_after != avatar_after
                assert avatar_after

    _run(_body())
