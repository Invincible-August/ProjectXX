"""装备栏化身开关 / 神识只算装备 / 阵法 Bench 过滤。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.avatar_service import AvatarService
from app.services.equipment_service import EquipmentService
from app.services.formation_service import FormationService
from app.services.gm_service import GmService
from app.services.pet_service import PetService
from app.services.realm_config import clear_game_config_cache, get_game_config

from tests.async_db import open_test_session_factory, run_async as _run


@pytest.fixture(autouse=True)
def _reload_config() -> None:
    clear_game_config_cache()
    yield
    clear_game_config_cache()


async def _user_with_character(session, email: str) -> User:
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


def test_avatar_switch_controls_sense_and_bench(tmp_path: Path) -> None:
    """凝练后默认不上阵；打开开关才占神识并进 Bench。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "avsw.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "avsw@example.com")
                await GmService(session).gm_set_character(
                    user, force_jindan=True, spirit_stones=5000,
                )
                await session.commit()
                await AvatarService(session).condense(user)
                char = await character_service.get_character_by_user_id(session, user.id)
                assert char is not None
                form = FormationService(session)
                eq = EquipmentService(session)
                av_svc = AvatarService(session)
                bench = await form.bench_units(char)
                assert not any(b["unit_kind"] == "avatar" for b in bench)
                empty = await av_svc.get_sense(char)
                assert empty["load"] == 0
                state = await eq.set_avatar_deployed(char, deployed=True)
                assert state["avatar_deploy"]["deployed"] is True
                await session.commit()
                bench2 = await form.bench_units(char)
                assert any(b["unit_kind"] == "avatar" and b.get("enabled") for b in bench2)
                cost = int(get_game_config().divine_sense.cost_avatar)
                sense = await av_svc.get_sense(char)
                assert sense["load"] == cost
                await eq.set_avatar_deployed(char, deployed=False)
                await session.commit()
                bench3 = await form.bench_units(char)
                assert not any(b["unit_kind"] == "avatar" for b in bench3)

    _run(_body())


def test_equipped_pet_only_on_bench(tmp_path: Path) -> None:
    """灵宠须穿在装备槽才出现在阵法列表。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "petsw.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "petsw@example.com")
                char = await character_service.get_character_by_user_id(session, user.id)
                assert char is not None
                pet_svc = PetService(session)
                spawned = await pet_svc.capture_test(char)
                pet_id = int(spawned["id"])
                await session.commit()
                form = FormationService(session)
                bench = await form.bench_units(char)
                assert not any(b["unit_kind"] == "pet" for b in bench)
                eq = EquipmentService(session)
                state = await eq.get_slots_state(char)
                pet_bag = [row for row in state["bag_equipment"] if row.get("item_type") == "pet"]
                assert pet_bag
                await eq.equip_item(char, slot="pet", item_uid=pet_bag[0]["item_uid"])
                await session.commit()
                bench2 = await form.bench_units(char)
                pets = [b for b in bench2 if b["unit_kind"] == "pet"]
                assert len(pets) == 1
                assert pets[0]["ref_id"] == pet_id

    _run(_body())


def test_unequipped_puppets_not_on_bench(tmp_path: Path) -> None:
    """未编成傀儡不得进阵法 Bench；默认试炼木傀也不再例外。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "pupsw.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "pupsw@example.com")
                char = await character_service.get_character_by_user_id(session, user.id)
                assert char is not None
                assert int(char.trial_puppet_count) >= 1
                form = FormationService(session)
                bench = await form.bench_units(char)
                assert not any(b["unit_kind"] == "puppet" for b in bench)

                with pytest.raises(AppError) as exc:
                    await form.save_preset(
                        char,
                        0,
                        name="偷渡木傀",
                        role="attack",
                        formation_id="none",
                        units=[
                            {"unit_uid": "main", "unit_kind": "main", "x": 0, "y": 3},
                            {"unit_uid": "puppet_1", "unit_kind": "puppet", "x": 1, "y": 2},
                        ],
                    )
                assert exc.value.code == 40041

    _run(_body())
