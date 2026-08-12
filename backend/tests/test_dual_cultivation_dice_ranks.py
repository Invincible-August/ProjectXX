"""M7 L7：双增/传修为 + 掷骰档 + 四榜。"""

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
from app.services.dual_cultivation_service import DualCultivationService
from app.services.gm_service import GmService
from app.services.realm_config import clear_game_config_cache
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
    monkeypatch.setattr(settings, "dual_cultivation_enabled", True)
    clear_game_config_cache()
    reset_system_recycle_balance_for_tests()
    yield
    clear_game_config_cache()
    reset_system_recycle_balance_for_tests()


async def _register(session, email: str, name: str, gender: str):
    await auth_service.register_user(
        session,
        RegisterRequest(password="password123", email=email),
    )
    await session.commit()
    user = (await session.execute(select(User).where(User.email == email))).scalar_one()
    await character_service.create_character(
        session,
        user,
        CreateCharacterRequest(name=name, gender=gender),
    )
    await session.commit()
    return user


def test_dual_mutual_and_transfer_ranks(tmp_path: Path) -> None:
    """双增一局 + 传修为一局；掷骰可复现；四榜有分。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "dual.db") as factory:
            async with factory() as session:
                male_u = await _register(session, "m@example.com", "乾修甲", "male")
                female_u = await _register(session, "f@example.com", "坤修乙", "female")
                await GmService(session).gm_set_character(
                    male_u,
                    spirit_stones=5_000,
                    cultivation_points=200,
                )
                await GmService(session).gm_set_character(
                    female_u,
                    spirit_stones=5_000,
                    cultivation_points=200,
                )
                await session.commit()
                svc = DualCultivationService(session)

                # --- mutual_gain ---
                invited = await svc.invite(
                    male_u,
                    technique_id="twin_moon_mutual",
                    target_character_id=None,
                    target_name="坤修乙",
                    dice_seed=42,
                )
                await session.commit()
                sid = int(invited["session"]["session_id"])
                await svc.confirm(female_u, sid)
                await session.commit()
                rolled = await svc.roll(male_u, sid, dice_seed=42)
                await session.commit()
                assert rolled["dice"]["purpose"] == "dual_cultivation"
                assert rolled["dice"]["roll"] is not None
                assert rolled["dice"]["yield_mult"] is not None
                # 同 seed 再开一场应同出目：先结算本场
                settled = await svc.settle(male_u, sid)
                await session.commit()
                assert settled["summary"]["mode"] == "mutual_gain"
                assert settled["summary"]["scaled_yield"] > 0

                ranks = await svc.ranks(male_u)
                assert ranks["boards"]["male_number_one"]["my_score"] >= 1
                assert ranks["boards"]["female_number_one"]["entries"]

                # --- transfer ---
                invited2 = await svc.invite(
                    male_u,
                    technique_id="jade_dew_transfer",
                    target_name="坤修乙",
                    target_character_id=None,
                    dice_seed=7,
                )
                await session.commit()
                sid2 = int(invited2["session"]["session_id"])
                await svc.confirm(female_u, sid2)
                await session.commit()
                await svc.roll(male_u, sid2, dice_seed=7)
                await session.commit()
                settled2 = await svc.settle(female_u, sid2)
                await session.commit()
                assert settled2["summary"]["mode"] == "transfer"
                assert settled2["summary"]["receiver_gain"] > 0

                ranks2 = await svc.ranks(female_u, board="female_zero")
                assert ranks2["boards"]["female_zero"]["my_score"] >= 1

                # 无性别拒
                bare = await _register(session, "x@example.com", "未定丙", "male")
                # 强制清空性别模拟存量
                from app.services.character_service import CharacterService

                ch = await CharacterService(session).get_by_user_id(bare.id)
                assert ch is not None
                ch.gender = None
                await session.commit()
                with pytest.raises(AppError) as exc:
                    await svc.invite(
                        bare,
                        technique_id="twin_moon_mutual",
                        target_name="坤修乙",
                        target_character_id=None,
                    )
                assert exc.value.code == 40160

                # 补选后可邀
                await svc.set_gender(bare, "male")
                await session.commit()
                me = await svc.me(bare)
                assert me["gender"] == "male"
                assert me["needs_gender"] is False

    _run(_body())


def test_dual_dice_seed_reproducible(tmp_path: Path) -> None:
    """同 seed 掷骰出目一致。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "dual_seed.db") as factory:
            async with factory() as session:
                a = await _register(session, "a1@example.com", "甲一", "male")
                b = await _register(session, "b1@example.com", "乙一", "female")
                await GmService(session).gm_set_character(a, spirit_stones=2_000)
                await GmService(session).gm_set_character(b, spirit_stones=2_000)
                await session.commit()
                svc = DualCultivationService(session)
                rolls = []
                for i in range(2):
                    peer = "乙一" if i == 0 else "甲一"
                    inviter = a if i == 0 else b
                    invitee = b if i == 0 else a
                    # 第二轮：取消上一场后重开 — 直接各开一场 settle
                    inv = await svc.invite(
                        inviter,
                        technique_id="twin_moon_mutual",
                        target_name=peer,
                        target_character_id=None,
                        dice_seed=99,
                    )
                    await session.commit()
                    sid = int(inv["session"]["session_id"])
                    await svc.confirm(invitee, sid)
                    await session.commit()
                    rolled = await svc.roll(inviter, sid, dice_seed=99)
                    await session.commit()
                    rolls.append(int(rolled["dice"]["roll"]))
                    await svc.settle(inviter, sid)
                    await session.commit()
                assert rolls[0] == rolls[1]

    _run(_body())
