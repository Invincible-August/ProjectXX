"""后台玩家账号管理 + 道号/user_id 解析。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password, verify_password
from app.db.models import AdminUser, Character, User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.admin_player_service import DEFAULT_RESET_PASSWORD, AdminPlayerService
from app.services.admin_rbac import roles_to_storage
from app.constants.admin_player import build_player_ops_schema
from app.services.character_resolve import resolve_character_ref
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


def test_admin_player_account_ops(tmp_path: Path) -> None:
    """列表 / 封号 / 重置密码 / 改联系方式 / 派发仙缘。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "admin_players.db") as factory:
            async with factory() as session:
                await auth_service.register_user(
                    session,
                    RegisterRequest(password="password123", email="player_ops@example.com"),
                )
                await session.commit()
                user = (
                    await session.execute(
                        select(User).where(User.email == "player_ops@example.com"),
                    )
                ).scalar_one()
                await character_service.create_character(
                    session,
                    user,
                    CreateCharacterRequest(name="运营测号"),
                )
                await session.commit()

                admin = AdminUser(
                    username="ops_admin",
                    password_hash=hash_password("adminpass1"),
                    display_name="Ops",
                    roles=roles_to_storage(["admin"]),
                    is_active=True,
                )
                session.add(admin)
                await session.flush()

                svc = AdminPlayerService(session)
                listed = await svc.list_accounts(admin, page=1, page_size=20)
                assert listed["total"] >= 1
                row = next(i for i in listed["items"] if i["id"] == user.id)
                assert row["email"] == "player_ops@example.com"
                assert row["user_id"].startswith("T")  # 测试环境前缀
                assert len(row["user_id"]) == 8
                assert row["fate_luck"] == 0
                assert row["total_recharge_amount"] == 0
                assert row["is_banned"] is False
                assert row["is_gm"] is False

                banned = await svc.ban_account(admin, user_id=user.id, banned=True)
                assert banned["is_banned"] is True
                assert banned["is_active"] is False

                gm = await svc.set_gm(admin, user_id=user.id, is_gm=True)
                assert gm["is_gm"] is True
                assert gm["user_id"].startswith("G")

                deleted = await svc.soft_delete_account(admin, user_id=user.id)
                assert deleted["is_active"] is False

                reset = await svc.reset_password(admin, user_id=user.id)
                await session.refresh(user)
                assert verify_password(DEFAULT_RESET_PASSWORD, user.password_hash)
                assert "12345678" in (reset.get("message") or "")

                updated = await svc.update_contacts(
                    admin,
                    user_id=user.id,
                    email="new_ops@example.com",
                    phone="13800138000",
                )
                assert updated["email"] == "new_ops@example.com"
                assert updated["phone"] == "13800138000"

                granted = await svc.grant_fate_luck(admin, user_id=user.id, amount=50)
                assert granted["fate_luck"] == 50
                ch = (
                    await session.execute(
                        select(Character).where(Character.user_id == user.id),
                    )
                ).scalar_one()
                assert int(ch.fate_luck) == 50

                tip = await svc.create_tip_record(
                    admin,
                    user_id=user.id,
                    paid_at="2026-08-14 15:30:00",
                    channel="微信",
                    order_no="WX-TEST-001",
                    amount=88,
                )
                assert tip["tip"]["amount"] == 88
                assert tip["account"]["total_recharge_amount"] == 88

                tips = await svc.list_tip_records(admin, user_id=user.id)
                assert tips["total"] == 1
                assert tips["items"][0]["order_no"] == "WX-TEST-001"

                grants = await svc.list_fate_luck_grants(admin, user_id=user.id)
                assert grants["total"] == 1
                assert grants["items"][0]["amount"] == 50

                ads = await svc.list_ad_watch_records(admin, user_id=user.id)
                assert ads["total"] == 0
                assert ads["watch_count"] == 0

                schema = svc.get_ops_schema(admin)
                assert schema["module_id"] == "player_accounts"
                assert schema["forms"]["tip_create"]
                assert any(f["key"] == "paid_at" for f in schema["forms"]["tip_create"])
                assert build_player_ops_schema()["title_zh"]

                await svc.ban_account(admin, user_id=user.id, banned=False)
                await session.commit()

    _run(_body())


def test_resolve_character_by_user_id_and_digit_name(tmp_path: Path) -> None:
    """道号优先；纯数字可回退为 user_id。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "resolve_uid.db") as factory:
            async with factory() as session:
                await auth_service.register_user(
                    session,
                    RegisterRequest(password="password123", email="resolve_uid@example.com"),
                )
                await session.commit()
                user = (
                    await session.execute(
                        select(User).where(User.email == "resolve_uid@example.com"),
                    )
                ).scalar_one()
                await character_service.create_character(
                    session,
                    user,
                    CreateCharacterRequest(name="解析道号"),
                )
                await session.commit()
                ch = (
                    await session.execute(
                        select(Character).where(Character.user_id == user.id),
                    )
                ).scalar_one()

                by_name = await resolve_character_ref(session, name="解析道号")
                assert by_name.id == ch.id

                by_uid = await resolve_character_ref(session, user_id=user.id)
                assert by_uid.id == ch.id

                by_digit = await resolve_character_ref(session, name=str(user.id))
                assert by_digit.id == ch.id

                assert user.public_uid
                by_public = await resolve_character_ref(session, name=user.public_uid)
                assert by_public.id == ch.id

                with pytest.raises(AppError):
                    await resolve_character_ref(session, name="不存在的道号xyz")

    _run(_body())
