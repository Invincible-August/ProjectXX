"""M7 L8：会员帽 18/24、过期回落、沙盒天道点、禁售本命道。"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.time_utils import now_utc
from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.commerce_service import CommerceService
from app.services.currency_ledger_service import reset_system_recycle_balance_for_tests
from app.services.realm_config import clear_game_config_cache, offline_cap_hours_for_tier
from tests.async_db import open_test_session_factory, run_async as _run


@pytest.fixture(autouse=True)
def _cfg(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "gm_enabled", True)
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    monkeypatch.setattr(settings, "commerce_system_enabled", True)
    monkeypatch.setattr(settings, "commerce_sandbox_enabled", True)
    clear_game_config_cache()
    reset_system_recycle_balance_for_tests()
    yield
    clear_game_config_cache()
    reset_system_recycle_balance_for_tests()


async def _register(session, email: str, name: str):
    await auth_service.register_user(
        session,
        RegisterRequest(password="password123", email=email),
    )
    await session.commit()
    user = (await session.execute(select(User).where(User.email == email))).scalar_one()
    await character_service.create_character(
        session,
        user,
        CreateCharacterRequest(name=name, gender="male"),
    )
    await session.commit()
    return user


def test_commerce_membership_sandbox(tmp_path: Path) -> None:
    """沙盒加点 → 开通 tier1 帽 18 → 过期回落 12；禁售本命道。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "commerce.db") as factory:
            async with factory() as session:
                user = await _register(session, "c@example.com", "商修甲")
                svc = CommerceService(session)

                me0 = await svc.me(user)
                assert me0["membership"]["tier"] == "free"
                assert me0["membership"]["idle_cap_hours"] == 12

                granted = await svc.sandbox_grant_tiandao(user, 100)
                await session.commit()
                assert granted["tiandao_points"] == 100

                act = await svc.activate_membership(user, "tier1")
                await session.commit()
                assert act["membership"]["tier"] == "tier1"
                assert act["membership"]["idle_cap_hours"] == 18
                assert act["tiandao_points"] == 0
                assert offline_cap_hours_for_tier("tier1") == 18.0

                shop = await svc.shop(user)
                assert "指定本命" in shop["boundary_zh"] or "本命" in shop["boundary_zh"]
                kinds = [i.get("kind") for i in shop["items"]]
                assert "appointed_dao" not in kinds
                assert "fate_dao" not in kinds

                # 过期回落
                ch = await character_service.CharacterService(session).get_by_user_id(user.id)
                assert ch is not None
                ch.membership_expires_at = now_utc() - timedelta(seconds=10)
                await session.commit()
                me1 = await svc.me(user)
                await session.commit()
                assert me1["membership"]["tier"] == "free"
                assert me1["membership"]["idle_cap_hours"] == 12

                # 天道点不足（余额 0）
                with pytest.raises(AppError) as exc:
                    await svc.activate_membership(user, "tier2")
                assert exc.value.code == 40170

                # 沙盒关闭拒
                settings = get_settings()
                settings.commerce_sandbox_enabled = False
                with pytest.raises(AppError):
                    await svc.sandbox_grant_tiandao(user, 10)

    _run(_body())
