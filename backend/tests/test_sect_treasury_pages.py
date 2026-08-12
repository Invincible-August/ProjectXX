"""M7-V+ 藏宝阁页权限与禁止图纸。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.gm_service import GmService
from app.services.realm_config import clear_game_config_cache
from app.services.sect_facility_service import SectFacilityService
from app.services.sect_service import SectService
from app.domain.sect_org_rules import deposit_type_forbidden, treasury_page_allowed
from app.services.realm_config import get_game_config
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
    monkeypatch.setattr(settings, "sect_system_enabled", True)
    clear_game_config_cache()
    yield
    clear_game_config_cache()


async def _register_char(session, email: str, name: str):
    await auth_service.register_user(
        session,
        RegisterRequest(password="password123", email=email),
    )
    await session.commit()
    user = (await session.execute(select(User).where(User.email == email))).scalar_one()
    await character_service.create_character(
        session,
        user,
        CreateCharacterRequest(name=name),
    )
    await session.commit()
    return user


def test_treasury_rules_unit() -> None:
    """页权限与禁止类型。"""
    ranks = get_game_config().sects.disciple_ranks
    forbidden = list(
        (get_game_config().sects.treasury or {}).get("forbidden_deposit_types") or [],
    )
    assert treasury_page_allowed(rank="outer_elder", page=1, disciple_ranks=ranks)
    assert not treasury_page_allowed(rank="outer_elder", page=2, disciple_ranks=ranks)
    assert treasury_page_allowed(rank="founder", page=6, disciple_ranks=ranks)
    assert deposit_type_forbidden("forge_blueprint", forbidden)
    assert not deposit_type_forbidden("material", forbidden)


def test_treasury_deposit_forbid_blueprint(tmp_path: Path) -> None:
    """创派可放入，但图纸类型拒绝。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "sect_treasury.db") as factory:
            async with factory() as session:
                user = await _register_char(session, "tr@example.com", "藏宝丁")
                await GmService(session).gm_set_character(
                    user,
                    spirit_stones=200_000,
                )
                await session.commit()
                await SectService(session).create(
                    user,
                    name="藏宝试宗",
                    motto=None,
                    specialty="formation",
                )
                await session.commit()
                fac = SectFacilityService(session)
                with pytest.raises(AppError) as exc:
                    await fac.treasury_deposit(
                        user,
                        page=1,
                        item_type="forge_blueprint",
                        item_id="sword_bp",
                        quantity=1,
                        label_zh="剑图纸",
                    )
                assert "图纸" in (exc.value.message or "")

                ok = await fac.treasury_deposit(
                    user,
                    page=1,
                    item_type="material",
                    item_id="ore_iron_raw",
                    quantity=3,
                    label_zh="铁矿",
                )
                assert ok["id"] > 0

                # 兑换
                listed = await fac.treasury_list(user)
                assert listed["catalog"]
                key = listed["catalog"][0]["item_key"]
                # 灌贡献
                from app.db.models.sect import SectMember

                m = (await session.execute(select(SectMember))).scalars().first()
                assert m is not None
                m.contribution = 500
                await session.commit()
                ex = await fac.treasury_exchange(user, item_key=key)
                assert "兑换" in ex["message"]

                # 矿脉：被动入库（无日领）
                mine = await fac.mine_status(user)
                assert "pool_rate_per_hour" in mine
                assert mine["max_miners"] >= 1
                assert mine["mining"] is False

    _run(_body())
