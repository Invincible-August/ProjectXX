"""M7 L7：道侣/炉鼎双修新流程 + 时长榜。"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.time_utils import now_utc
from app.db.models import User
from app.db.models.bond import BOND_KIND_COMPANION, BOND_KIND_VESSEL, CharacterBond
from app.db.models.dual_cultivation import DualCultivationSession
from app.domain.trade_rules import friendship_pair_key
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.bond_service import BondService
from app.services.character_service import CharacterService
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
    monkeypatch.setattr(settings, "friends_system_enabled", True)
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


async def _make_companion(session, a_user, b_user) -> None:
    bonds = BondService(session)
    peer = await CharacterService(session).get_by_user_id(b_user.id)
    assert peer is not None
    applied = await bonds.apply_companion(
        a_user,
        target_character_id=None,
        target_name=peer.name,
    )
    await session.commit()
    await bonds.accept(b_user, int(applied["bond_id"]))
    await session.commit()


def test_dual_companion_flow_climax_and_rank(tmp_path: Path) -> None:
    """道侣：邀约→接受→宽衣→开始→结算；时长计入总榜。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "dual.db") as factory:
            async with factory() as session:
                male_u = await _register(session, "m@example.com", "乾修甲", "male")
                female_u = await _register(session, "f@example.com", "坤修乙", "female")
                await GmService(session).gm_set_character(
                    male_u,
                    spirit_stones=5_000,
                    cultivation_points=5_000,
                )
                await GmService(session).gm_set_character(
                    female_u,
                    spirit_stones=5_000,
                    cultivation_points=5_000,
                )
                await session.commit()
                await _make_companion(session, male_u, female_u)

                female_ch = await CharacterService(session).get_by_user_id(female_u.id)
                assert female_ch is not None
                svc = DualCultivationService(session)

                with pytest.raises(AppError) as typed:
                    await svc.invite(
                        male_u,
                        technique_id="twin_moon_mutual",
                        target_character_id=female_ch.id,
                        bond_kind="companion",
                        target_name="坤修乙",
                    )
                assert typed.value.code == 40161

                invited = await svc.invite(
                    male_u,
                    technique_id="twin_moon_mutual",
                    target_character_id=female_ch.id,
                    bond_kind="companion",
                    dice_seed=42,
                )
                await session.commit()
                sid = int(invited["session"]["session_id"])
                assert invited["session"]["status"] == "inviting"

                await svc.confirm(female_u, sid)
                await session.commit()
                await svc.undress(female_u, sid)
                await session.commit()

                started = await svc.start(male_u, sid)
                await session.commit()
                summary = started["summary"]
                assert summary["mode"] == "mutual_gain"
                assert summary["duration_sec"] > 0
                assert summary.get("insert_count", 0) > 0
                assert summary.get("log_zh")

                ranks = await svc.ranks(male_u, board="duration_total", limit=100)
                assert ranks["boards"]["duration_total"]["my_score"] >= 1

                invited2 = await svc.invite(
                    male_u,
                    technique_id="jade_dew_transfer",
                    target_character_id=female_ch.id,
                    bond_kind="companion",
                    dice_seed=7,
                )
                await session.commit()
                sid2 = int(invited2["session"]["session_id"])
                await svc.confirm(female_u, sid2)
                await session.commit()
                await svc.undress(female_u, sid2)
                await session.commit()
                settled2 = await svc.start(male_u, sid2)
                await session.commit()
                assert settled2["summary"]["mode"] == "transfer"
                assert "transfer" in settled2["summary"]
                assert "stamina" in settled2["summary"]

                # 蛇蝎索取
                invited3 = await svc.invite(
                    male_u,
                    technique_id="serpent_extract",
                    target_character_id=female_ch.id,
                    bond_kind="companion",
                    dice_seed=11,
                )
                await session.commit()
                sid3 = int(invited3["session"]["session_id"])
                await svc.confirm(female_u, sid3)
                await session.commit()
                await svc.undress(female_u, sid3)
                await session.commit()
                settled3 = await svc.start(male_u, sid3)
                await session.commit()
                assert settled3["summary"]["mode"] == "extract"
                assert "extract" in settled3["summary"]
                assert settled3["summary"]["stamina"]["mode"] == "extract"
                assert settled3["summary"]["stamina"]["costs"]["extractor"] >= (
                    settled3["summary"]["stamina"]["costs"]["target"]
                )

    _run(_body())


def test_companion_invite_and_undress_timeout(tmp_path: Path) -> None:
    """道侣：邀约超时 / 宽衣超时均为终态 timeout。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "dual_timeout.db") as factory:
            async with factory() as session:
                male_u = await _register(session, "tm@example.com", "超时甲", "male")
                female_u = await _register(session, "tf@example.com", "超时乙", "female")
                await GmService(session).gm_set_character(male_u, spirit_stones=2_000)
                await GmService(session).gm_set_character(female_u, spirit_stones=2_000)
                await session.commit()
                await _make_companion(session, male_u, female_u)
                female_ch = await CharacterService(session).get_by_user_id(female_u.id)
                assert female_ch is not None
                svc = DualCultivationService(session)

                invited = await svc.invite(
                    male_u,
                    technique_id="twin_moon_mutual",
                    target_character_id=female_ch.id,
                    bond_kind="companion",
                    dice_seed=1,
                )
                await session.commit()
                sid = int(invited["session"]["session_id"])
                row = await session.get(DualCultivationSession, sid)
                assert row is not None
                row.invite_expire_at = now_utc() - timedelta(seconds=1)
                await session.commit()
                await svc._expire_stale()
                await session.commit()
                row = await session.get(DualCultivationSession, sid)
                assert row is not None
                assert row.status == "timeout"

                invited2 = await svc.invite(
                    male_u,
                    technique_id="twin_moon_mutual",
                    target_character_id=female_ch.id,
                    bond_kind="companion",
                    dice_seed=2,
                )
                await session.commit()
                sid2 = int(invited2["session"]["session_id"])
                await svc.confirm(female_u, sid2)
                await session.commit()
                row2 = await session.get(DualCultivationSession, sid2)
                assert row2 is not None
                assert row2.status == "accepted"
                row2.undress_expire_at = now_utc() - timedelta(seconds=1)
                await session.commit()
                await svc._expire_stale()
                await session.commit()
                row2 = await session.get(DualCultivationSession, sid2)
                assert row2 is not None
                assert row2.status == "timeout"

    _run(_body())


def test_vessel_invite_stays_inviting_and_auto_accept(tmp_path: Path) -> None:
    """炉鼎：邀约保持 inviting；可确认；受邀方不可取消；超时自动接受/宽衣。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "dual_vessel.db") as factory:
            async with factory() as session:
                a = await _register(session, "va@example.com", "炉主", "male")
                b = await _register(session, "vb@example.com", "炉鼎乙", "female")
                await GmService(session).gm_set_character(a, spirit_stones=2_000)
                await GmService(session).gm_set_character(b, spirit_stones=2_000)
                await session.commit()
                a_ch = await CharacterService(session).get_by_user_id(a.id)
                b_ch = await CharacterService(session).get_by_user_id(b.id)
                assert a_ch and b_ch
                low, high = friendship_pair_key(a_ch.id, b_ch.id)
                session.add(
                    CharacterBond(
                        character_low_id=low,
                        character_high_id=high,
                        bond_kind=BOND_KIND_VESSEL,
                        requester_id=a_ch.id,
                        owner_character_id=a_ch.id,
                        status="active",
                    ),
                )
                await session.commit()

                svc = DualCultivationService(session)
                invited = await svc.invite(
                    a,
                    technique_id="twin_moon_mutual",
                    target_character_id=b_ch.id,
                    bond_kind=BOND_KIND_VESSEL,
                    dice_seed=99,
                )
                await session.commit()
                assert invited["session"]["status"] == "inviting"
                assert invited["session"]["auto_forced"] is False
                sid = int(invited["session"]["session_id"])

                with pytest.raises(AppError) as cancel_err:
                    await svc.cancel(b, sid)
                assert cancel_err.value.http_status == 403

                await svc.confirm(b, sid)
                await session.commit()
                row = await session.get(DualCultivationSession, sid)
                assert row is not None
                assert row.status == "accepted"
                assert row.undress_expire_at is not None

                # 手动宽衣并开始
                await svc.undress(b, sid)
                await session.commit()
                started = await svc.start(a, sid)
                await session.commit()
                assert started["summary"]["duration_sec"] > 0

                # 超时自动接受 + 自动宽衣路径
                invited2 = await svc.invite(
                    a,
                    technique_id="twin_moon_mutual",
                    target_character_id=b_ch.id,
                    bond_kind=BOND_KIND_VESSEL,
                    dice_seed=100,
                )
                await session.commit()
                sid2 = int(invited2["session"]["session_id"])
                row2 = await session.get(DualCultivationSession, sid2)
                assert row2 is not None
                row2.invite_expire_at = now_utc() - timedelta(seconds=1)
                await session.commit()
                await svc._expire_stale()
                await session.commit()
                row2 = await session.get(DualCultivationSession, sid2)
                assert row2 is not None
                assert row2.status == "accepted"
                assert row2.auto_forced is True

                row2.undress_expire_at = now_utc() - timedelta(seconds=1)
                await session.commit()
                await svc._expire_stale()
                await session.commit()
                row2 = await session.get(DualCultivationSession, sid2)
                assert row2 is not None
                assert row2.status == "undressed"

    _run(_body())


def test_vessel_apply_blocked(tmp_path: Path) -> None:
    """炉鼎不可玩家直接邀请添加。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "vessel_block.db") as factory:
            async with factory() as session:
                a = await _register(session, "xa@example.com", "炉甲", "male")
                await _register(session, "xb@example.com", "炉乙", "female")
                bonds = BondService(session)
                with pytest.raises(AppError):
                    await bonds.apply_vessel(a, target_name="炉乙")

    _run(_body())
