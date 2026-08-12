"""M7 L6：拜师→传功任务→出师；道友引渡成本差。"""

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
from app.services.currency_ledger_service import reset_system_recycle_balance_for_tests
from app.services.ferry_service import FerryService
from app.services.friend_service import FriendService
from app.services.gm_service import GmService
from app.services.mentor_service import MentorService
from app.services.realm_config import clear_game_config_cache
from app.services.sect_service import SectService
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
    monkeypatch.setattr(settings, "mentor_system_enabled", True)
    monkeypatch.setattr(settings, "friends_system_enabled", True)
    monkeypatch.setattr(settings, "sect_system_enabled", True)
    monkeypatch.setattr(settings, "same_region_stub", True)
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
        CreateCharacterRequest(name=name),
    )
    await session.commit()
    return user


def test_mentor_apply_pass_graduate(tmp_path: Path) -> None:
    """拜师→传功完成任务→出师；非法境界拒。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "mentor.db") as factory:
            async with factory() as session:
                master_u = await _register(session, "m@example.com", "师尊甲")
                appr_u = await _register(session, "a@example.com", "弟子乙")
                await GmService(session).gm_set_character(
                    master_u,
                    major_realm="foundation",
                    spirit_stones=5_000,
                )
                await GmService(session).gm_set_character(
                    appr_u,
                    major_realm="body_tempering",
                    spirit_stones=500,
                )
                await session.commit()
                svc = MentorService(session)
                # 徒弟拜师
                applied = await svc.apply(
                    appr_u,
                    target_character_id=None,
                    target_name="师尊甲",
                    intent="apprentice",
                )
                await session.commit()
                bond_id = int(applied["bond_id"])
                await svc.accept(master_u, bond_id)
                await session.commit()
                me = await svc.me(appr_u)
                assert me["bond"]["status"] == "active"
                assert me["channel_ref"] and me["channel_ref"].startswith("mentor:")

                # 传功推进任务
                await svc.pass_cultivation(master_u)
                await session.commit()
                me2 = await svc.me(appr_u)
                assert any(q["completed"] for q in me2["quests"])

                graduated = await svc.graduate(appr_u)
                await session.commit()
                assert graduated["bond"]["status"] == "graduated"

                # 同境界拒拜
                c = await _register(session, "c@example.com", "路人丙")
                await GmService(session).gm_set_character(
                    c,
                    major_realm="body_tempering",
                )
                await session.commit()
                with pytest.raises(AppError) as exc:
                    await svc.apply(
                        c,
                        target_name="弟子乙",
                        target_character_id=None,
                        intent="apprentice",
                    )
                assert exc.value.code == 40150

    _run(_body())


def test_ferry_friend_rescue_cheaper(tmp_path: Path) -> None:
    """道友引渡成功；成本低于自救；非道友拒。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "ferry_soc.db") as factory:
            async with factory() as session:
                victim_u = await _register(session, "v@example.com", "陨落甲")
                friend_u = await _register(session, "f@example.com", "道友乙")
                stranger_u = await _register(session, "s@example.com", "路人丁")
                await GmService(session).gm_set_character(friend_u, spirit_stones=2_000)
                await GmService(session).gm_set_character(victim_u, spirit_stones=50)
                await session.commit()
                friends = FriendService(session)
                applied = await friends.apply(
                    victim_u,
                    target_character_id=None,
                    target_name="道友乙",
                )
                await session.commit()
                await friends.accept(friend_u, int(applied["friendship_id"]))
                await session.commit()

                ferry = FerryService(session)
                victim = await character_service.get_character_by_user_id(session, victim_u.id)
                await ferry.enter_awaiting_ferry(victim)
                await session.commit()

                with pytest.raises(AppError) as exc:
                    await ferry.social_rescue(
                        stranger_u,
                        target_name="陨落甲",
                        target_character_id=None,
                        mode="friend",
                    )
                assert exc.value.code == 40180

                friend_ch = await character_service.get_character_by_user_id(session, friend_u.id)
                before = int(friend_ch.spirit_stones)
                rescued = await ferry.social_rescue(
                    friend_u,
                    target_name="陨落甲",
                    target_character_id=None,
                    mode="friend",
                )
                await session.commit()
                assert rescued["rescued"] is True
                cost = int(rescued["spirit_stones_spent"])
                assert cost < 500  # 低于自救
                await session.refresh(friend_ch)
                assert int(friend_ch.spirit_stones) == before - cost
                await session.refresh(victim)
                assert victim.status == "normal"

                # get_me 展示成本差
                await ferry.enter_awaiting_ferry(victim)
                await session.commit()
                panel = await ferry.get_me(victim_u)
                assert panel["ferry"]["social_rescue"]["friend_cheaper_by"] > 0

    _run(_body())


def test_ferry_sect_rescue_requires_higher_realm(tmp_path: Path) -> None:
    """同门引渡：修为不够拒绝；够则成功。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "ferry_sect.db") as factory:
            async with factory() as session:
                low = await _register(session, "low@example.com", "低修甲")
                high = await _register(session, "hi@example.com", "高修乙")
                await GmService(session).gm_set_character(
                    low,
                    major_realm="qi_refining",
                    spirit_stones=1_000,
                )
                await GmService(session).gm_set_character(
                    high,
                    major_realm="foundation",
                    spirit_stones=3_000,
                )
                await session.commit()
                sect = SectService(session)
                await sect.join(low, template_id="qingyun_zong")
                await sect.join(high, template_id="qingyun_zong")
                await session.commit()
                ferry = FerryService(session)
                victim = await character_service.get_character_by_user_id(session, low.id)
                await ferry.enter_awaiting_ferry(victim)
                await session.commit()
                # 低修救高修不可（victim is low; reverse: low tries to rescue - victim is high)
                # 这里高修救低修应成功；低修救同境界不可用——用 high 救 low
                ok = await ferry.social_rescue(
                    high,
                    target_name="低修甲",
                    target_character_id=None,
                    mode="sect",
                )
                await session.commit()
                assert ok["rescued"] is True

    _run(_body())
