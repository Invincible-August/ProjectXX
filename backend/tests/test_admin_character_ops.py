"""后台角色管理：列表 / 软删 / 死亡 / 突破 / 货币 / 功法。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.constants.admin_character import build_character_ops_schema
from app.constants.character import (
    CHARACTER_STATUS_ADMIN_CHOICES,
    CHARACTER_STATUS_AWAITING_FERRY,
    CHARACTER_STATUS_WEAK,
)
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.models import AdminUser, Character, User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.services import auth_service, character_service
from app.services.admin_character_service import AdminCharacterService
from app.services.admin_rbac import roles_to_storage
from app.services.realm_config import clear_game_config_cache
from tests.async_db import open_test_session_factory, run_async as _run


@pytest.fixture(autouse=True)
def _cfg(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    clear_game_config_cache()
    yield
    clear_game_config_cache()


def test_character_status_constants() -> None:
    """运营状态下拉含正常/虚弱等；schema 可构建。"""
    assert "normal" in CHARACTER_STATUS_ADMIN_CHOICES
    assert CHARACTER_STATUS_WEAK in CHARACTER_STATUS_ADMIN_CHOICES
    schema = build_character_ops_schema()
    assert schema["module_id"] == "player_characters"
    assert any(o["value"] == "epiphany" for o in schema["status_options"])


def test_admin_character_ops(tmp_path: Path) -> None:
    """软删 / 死亡待引渡 / 修为突破 / 改状态 / 改货币。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "admin_chars.db") as factory:
            async with factory() as session:
                await auth_service.register_user(
                    session,
                    RegisterRequest(password="password123", email="char_ops@example.com"),
                )
                await session.commit()
                user = (
                    await session.execute(
                        select(User).where(User.email == "char_ops@example.com"),
                    )
                ).scalar_one()
                await character_service.create_character(
                    session,
                    user,
                    CreateCharacterRequest(name="角色运营测"),
                )
                await session.commit()
                character = (
                    await session.execute(
                        select(Character).where(Character.user_id == user.id),
                    )
                ).scalar_one()
                stage_before = int(character.realm_stage)

                admin = AdminUser(
                    username="char_admin",
                    password_hash=hash_password("adminpass1"),
                    display_name="CharOps",
                    roles=roles_to_storage(["admin"]),
                    is_active=True,
                )
                session.add(admin)
                await session.flush()

                svc = AdminCharacterService(session)
                listed = await svc.list_characters(admin, page=1, page_size=20)
                assert listed["total"] >= 1
                row = next(i for i in listed["items"] if i["id"] == character.id)
                assert row["name"] == "角色运营测"
                assert row["is_active"] is True

                detail = await svc.get_detail(admin, character.id)
                assert detail["base_attrs"]
                assert detail["currencies"]

                await svc.update_status(admin, character.id, status=CHARACTER_STATUS_WEAK)
                await session.refresh(character)
                assert character.status == CHARACTER_STATUS_WEAK

                await svc.update_currencies(
                    admin,
                    character.id,
                    amounts={"spirit_stones": 9999, "tiandao_points": 3},
                )
                await session.refresh(character)
                assert int(character.spirit_stones) == 9999
                assert int(character.tiandao_points) == 3

                await svc.breakthrough_cultivation(admin, character.id)
                await session.refresh(character)
                assert int(character.realm_stage) == stage_before + 1

                await svc.kill_to_ferry(admin, character.id)
                await session.refresh(character)
                assert character.status == CHARACTER_STATUS_AWAITING_FERRY
                assert character.ferry_deadline_at is not None

                deleted = await svc.soft_delete(admin, character.id)
                assert deleted["is_active"] is False
                await session.refresh(character)

    _run(_body())


def test_admin_grant_technique_craft_test_cards(tmp_path: Path) -> None:
    """运营后台直发无限属性/效能正式卡入包。"""
    from app.constants.technique_craft import (
        CARD_FORMAL_EFFICACY_INF_ID,
        CARD_FORMAL_ELEMENT_INF_ID,
    )
    from app.db.models.inventory_item import InventoryItem

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "admin_craft_cards.db") as factory:
            async with factory() as session:
                await auth_service.register_user(
                    session,
                    RegisterRequest(password="password123", email="craft_cards@example.com"),
                )
                await session.commit()
                user = (
                    await session.execute(
                        select(User).where(User.email == "craft_cards@example.com"),
                    )
                ).scalar_one()
                await character_service.create_character(
                    session,
                    user,
                    CreateCharacterRequest(name="自研发卡测"),
                )
                await session.commit()
                character = (
                    await session.execute(
                        select(Character).where(Character.user_id == user.id),
                    )
                ).scalar_one()
                admin = AdminUser(
                    username="craft_card_admin",
                    password_hash=hash_password("adminpass1"),
                    display_name="CraftCards",
                    roles=roles_to_storage(["admin"]),
                    is_active=True,
                )
                session.add(admin)
                await session.flush()

                svc = AdminCharacterService(session)
                detail = await svc.grant_technique_craft_test_cards(admin, character.id)
                await session.commit()
                ids = {row["item_id"] for row in detail["inventory"]["items"]}
                assert CARD_FORMAL_ELEMENT_INF_ID in ids
                assert CARD_FORMAL_EFFICACY_INF_ID in ids
                rows = list(
                    (
                        await session.execute(
                            select(InventoryItem).where(
                                InventoryItem.character_id == character.id,
                                InventoryItem.item_id.in_(
                                    [CARD_FORMAL_ELEMENT_INF_ID, CARD_FORMAL_EFFICACY_INF_ID],
                                ),
                            )
                        )
                    ).scalars()
                )
                assert len(rows) == 2

    _run(_body())
