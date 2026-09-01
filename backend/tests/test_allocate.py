"""
资源分配测试（M2）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import allocate_service, auth_service, character_service
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
    monkeypatch.setattr(settings, "offline_preview_threshold_seconds", 300)
    clear_game_config_cache()
    yield
    clear_game_config_cache()


def test_allocate_realm_progress(tmp_path: Path) -> None:
    """分配修为池到境界进度。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "alloc_realm.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "alloc@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.cultivation_points = 100
                character.realm_progress = 0
                await session.commit()

                data = await allocate_service.allocate_resources(
                    session,
                    user,
                    target_type="realm",
                    target_id=None,
                    amount=40,
                )
                await session.commit()
                assert data["allocated"] == 40
                assert data["character"]["realm_progress"] == 40
                assert data["character"]["cultivation_points"] == 60

    _run(_body())


def test_allocate_body_temper_progress(tmp_path: Path) -> None:
    """分配淬体度池到淬体进度。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "alloc_bt.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "btpool@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.body_tempering_points = 80
                character.body_temper_stage = "refine_skin"
                character.body_temper_progress = 0
                await session.commit()

                data = await allocate_service.allocate_resources(
                    session,
                    user,
                    target_type="body_temper",
                    target_id=None,
                    amount=40,
                )
                await session.commit()
                assert data["allocated"] == 40
                assert data["character"]["body_temper_progress"] == 40
                assert data["character"]["body_tempering_points"] == 40

    _run(_body())


def test_allocate_body_temper_overflow_kept(tmp_path: Path) -> None:
    """淬体投入可超过本档门槛，全额扣池并写入进度。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "alloc_bt_over.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "btover@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.body_tempering_points = 80
                character.body_temper_stage = "refine_skin"
                character.body_temper_progress = 0
                await session.commit()

                data = await allocate_service.allocate_resources(
                    session,
                    user,
                    target_type="body_temper",
                    target_id=None,
                    amount=80,
                )
                await session.commit()
                assert data["allocated"] == 80
                assert data["character"]["body_temper_progress"] == 80
                assert data["character"]["body_tempering_points"] == 0

    _run(_body())


def test_allocate_technique_level_up(tmp_path: Path) -> None:
    """分配淬体度升炼体功法层数（可修炼从 1 层起，1→2 用 cost[1]）。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "alloc_tech.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "tech@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.body_tempering_points = 50
                await session.commit()

                data = await allocate_service.allocate_resources(
                    session,
                    user,
                    target_type="technique",
                    target_id="iron_body_art",
                    amount=40,
                )
                await session.commit()
                assert data["levels_gained"] == 1
                assert data["character"]["body_tempering_points"] == 10

    _run(_body())


def test_allocate_technique_not_cultivable_rejected(tmp_path: Path) -> None:
    """不可修炼功法拒绝资源分配。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "alloc_nc.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "nocult@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.cultivation_points = 500
                await session.commit()
                with pytest.raises(AppError) as exc_info:
                    await allocate_service.allocate_resources(
                        session,
                        user,
                        target_type="technique",
                        target_id="beginner_alchemy",
                        amount=30,
                    )
                assert exc_info.value.code == 40033
                assert "不可修炼" in exc_info.value.message

    _run(_body())


def test_allocate_technique_to_perfection(tmp_path: Path) -> None:
    """10 层后再投入 perfection_cost 置大圆满。"""

    async def _body() -> None:
        from app.db.models.technique import CharacterTechnique
        from app.services.technique_service import TechniqueService

        async with open_test_session_factory(tmp_path / "alloc_perf.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "perf@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.cultivation_points = 5000
                await session.commit()
                await TechniqueService(session).ensure_default_techniques(character.id)
                row = (
                    await session.execute(
                        select(CharacterTechnique).where(
                            CharacterTechnique.character_id == character.id,
                            CharacterTechnique.technique_id == "basic_qi_art",
                        )
                    )
                ).scalar_one()
                row.level = 10
                row.perfected = False
                await session.commit()

                data = await allocate_service.allocate_resources(
                    session,
                    user,
                    target_type="technique",
                    target_id="basic_qi_art",
                    amount=1200,
                )
                await session.commit()
                assert data["levels_gained"] == 1
                await session.refresh(row)
                assert row.perfected is True
                assert row.level == 10

                with pytest.raises(AppError) as exc_info:
                    await allocate_service.allocate_resources(
                        session,
                        user,
                        target_type="technique",
                        target_id="basic_qi_art",
                        amount=1200,
                    )
                assert "大圆满" in exc_info.value.message

    _run(_body())


def test_technique_combat_stacks_milestones(tmp_path: Path) -> None:
    """五层与大圆满叠里程碑 ATTR。"""

    async def _body() -> None:
        from app.services.technique_service import TechniqueService

        async with open_test_session_factory(tmp_path / "combat_ms.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "combatms@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                items = await TechniqueService(session).list_my_techniques(character)
                qi = next(i for i in items if i["id"] == "basic_qi_art")
                qi["level"] = 5
                qi["perfected"] = False
                mid = TechniqueService.compute_technique_combat_amounts([qi])
                # level*1 atk + tier5 tb_atk_gray phys_atk 1
                assert mid["phys_atk"] == pytest.approx(5 + 1)
                qi["perfected"] = True
                full = TechniqueService.compute_technique_combat_amounts([qi])
                # + pf_atk_blue phys_atk 4
                assert full["phys_atk"] == pytest.approx(5 + 1 + 4)

    _run(_body())


def test_allocate_insufficient_pool_40032(tmp_path: Path) -> None:
    """池不足 → 40032。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "alloc_low.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "low@example.com")
                with pytest.raises(AppError) as exc_info:
                    await allocate_service.allocate_resources(
                        session,
                        user,
                        target_type="realm",
                        target_id=None,
                        amount=10,
                    )
                assert exc_info.value.code == 40032

    _run(_body())
