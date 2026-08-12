"""
M4 布阵棋子解禁测试（§10.4）。
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
from app.services.formation_service import FormationService
from app.services.gm_service import GmService
from app.services.realm_config import clear_game_config_cache

from tests.async_db import open_test_session_factory, run_async as _run


async def _user_with_character(session: AsyncSession, email: str) -> User:
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
    clear_game_config_cache()
    yield
    clear_game_config_cache()


def test_bench_includes_avatar_after_condense(tmp_path: Path) -> None:
    """凝练后 bench 含 enabled 化身。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "form1.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "form01@example.com")
                await GmService(session).gm_set_character(user, force_jindan=True, spirit_stones=5000)
                await session.commit()
                await AvatarService(session).condense(user)
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                bench = await FormationService(session).bench_units(character)
                avatars = [b for b in bench if b["unit_kind"] == "avatar"]
                assert any(b.get("enabled") for b in avatars)

    _run(_body())


def test_storm_force_requires_array_level(tmp_path: Path) -> None:
    """阵法 storm_force 需 array_craft_level → 40054。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "form2.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "form02@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                form = FormationService(session)
                units = [{"unit_uid": "main", "unit_kind": "main", "x": 0, "y": 3}]
                with pytest.raises(AppError) as exc:
                    await form.validate_units(character, units, "storm_force")
                assert exc.value.code == 40054

    _run(_body())


def test_prune_ghost_avatar_when_no_avatar(tmp_path: Path) -> None:
    """无化身时预设残留 avatar_{id} 应在 list_presets 时被清洗。"""

    async def _body() -> None:
        from sqlalchemy import delete, select

        from app.db.models.avatar import Avatar
        from app.db.models.formation_preset import FormationPreset

        async with open_test_session_factory(tmp_path / "form_prune.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "formprune@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                form = FormationService(session)
                await form.ensure_default_presets(character)
                preset = (
                    await session.execute(
                        select(FormationPreset).where(
                            FormationPreset.character_id == character.id,
                            FormationPreset.slot == 0,
                        ),
                    )
                ).scalar_one()
                preset.units_json = (
                    '[{"unit_uid":"main","unit_kind":"main","x":0,"y":3},'
                    '{"unit_uid":"avatar_99","unit_kind":"avatar","ref_id":99,"x":1,"y":3}]'
                )
                await session.commit()

                # 确保无化身行
                await session.execute(
                    delete(Avatar).where(Avatar.character_id == character.id),
                )
                await session.commit()

                data = await form.list_presets(character)
                await session.commit()
                slot0 = next(p for p in data["presets"] if p["slot"] == 0)
                kinds = [u["unit_kind"] for u in slot0["units"]]
                assert "avatar" not in kinds
                assert "main" in kinds

    _run(_body())


def test_tribulation_blocks_avatar_in_formation(tmp_path: Path) -> None:
    """渡劫钩子：保存含 avatar → 拒绝。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "form3.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "form03@example.com")
                await GmService(session).gm_set_character(
                    user,
                    force_jindan=True,
                    spirit_stones=5000,
                    status="normal",
                )
                await session.commit()
                av_svc = AvatarService(session)
                await av_svc.condense(user)
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.status = "tribulation"
                avatar = await av_svc.get_avatar_row(character.id)
                assert avatar is not None
                form = FormationService(session)
                units = [
                    {"unit_uid": "main", "unit_kind": "main", "x": 0, "y": 3},
                    {
                        "unit_uid": f"avatar_{avatar.id}",
                        "unit_kind": "avatar",
                        "ref_id": avatar.id,
                        "x": 1,
                        "y": 3,
                    },
                ]
                with pytest.raises(AppError) as exc:
                    await form.validate_units(character, units, "none")
                assert exc.value.code == 40042

    _run(_body())
