"""
道友化身助战：开关 → 邀请化身立即入队 → bench 客串 → 助战体力扣减 → 战后离队。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import User
from app.db.models.avatar import Avatar
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.avatar_assist_service import (
    AvatarAssistService,
    guest_unit_uid,
)
from app.services.avatar_service import AvatarService
from app.services.formation_service import FormationService
from app.services.friend_service import FriendService
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
    monkeypatch.setattr(settings, "friends_system_enabled", True)
    monkeypatch.setattr(settings, "avatar_enabled", True)
    clear_game_config_cache()
    yield
    clear_game_config_cache()


async def _register(session, email: str, name: str) -> User:
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


async def _huashen_with_avatar(session, user: User) -> None:
    """化神 + 灵石 → 凝练化身（friend_assist / stamina 均已解锁）。"""
    await GmService(session).gm_set_character(
        user,
        major_realm="huashen",
        realm_stage=1,
        spirit_stones=5000,
    )
    await session.commit()
    await AvatarService(session).condense(user)
    await session.commit()


def test_invite_avatar_join_bench_spend_assist_stamina_and_end(tmp_path: Path) -> None:
    """
    主人开助战 → 道友邀请立即 active → bench 含 guest →
    spend_assist_battle 扣助战体力（不扣探索体力）→ 战后离队后可再邀。
    """

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "assist_pve.db") as factory:
            async with factory() as session:
                owner_user = await _register(session, "assist_owner@example.com", "助甲")
                borrower_user = await _register(session, "assist_borrow@example.com", "助乙")

                await _huashen_with_avatar(session, owner_user)
                await GmService(session).gm_set_character(
                    borrower_user,
                    major_realm="huashen",
                    realm_stage=1,
                    spirit_stones=1000,
                )
                await session.commit()

                owner_ch = await character_service.get_character_by_user_id(
                    session, owner_user.id,
                )
                borrower_ch = await character_service.get_character_by_user_id(
                    session, borrower_user.id,
                )
                assert owner_ch is not None and borrower_ch is not None

                friends = FriendService(session)
                applied = await friends.apply(
                    borrower_user,
                    target_character_id=None,
                    target_name="助甲",
                )
                await session.commit()
                await friends.accept(owner_user, int(applied["friendship_id"]))
                await session.commit()

                assist = AvatarAssistService(session)

                # 未开开关 → 闭关
                with pytest.raises(AppError) as closed_exc:
                    await assist.invite(
                        borrower_user,
                        target_character_id=owner_ch.id,
                        target_name=None,
                    )
                assert "闭关" in closed_exc.value.message

                settings_res = await assist.set_assist_settings(owner_user, enabled=True)
                await session.commit()
                assert settings_res["assist_friends_enabled"] is True

                invited = await assist.invite(
                    borrower_user,
                    target_character_id=owner_ch.id,
                    target_name=None,
                )
                await session.commit()
                assert invited["auto_accepted"] is True
                sess = invited["session"]
                assert sess["status"] == "active"
                avatar_row = (
                    await session.execute(
                        select(Avatar).where(Avatar.character_id == owner_ch.id),
                    )
                ).scalar_one()
                expected_uid = guest_unit_uid(owner_ch.id, avatar_row.id)
                assert sess["guest_unit_uid"] == expected_uid

                form = FormationService(session)
                bench = await form.bench_units(borrower_ch)
                guests = [
                    b for b in bench
                    if b.get("is_guest") or str(b.get("unit_uid", "")).startswith("avatar_guest_")
                ]
                assert len(guests) == 1
                assert guests[0]["unit_uid"] == expected_uid
                assert guests[0]["enabled"] is True

                units = [
                    {"unit_uid": "main", "unit_kind": "main", "x": 0, "y": 3},
                    {
                        "unit_uid": expected_uid,
                        "unit_kind": "avatar",
                        "ref_id": avatar_row.id,
                        "owner_character_id": owner_ch.id,
                        "x": 1,
                        "y": 3,
                    },
                ]
                await form.validate_units(borrower_ch, units, "none")

                # 助战体力独立：探索 stamina 不变
                assist.refresh_assist_stamina(avatar_row, owner_ch, persist=True)
                await session.flush()
                before_assist = int(avatar_row.assist_stamina)
                before_explore = int(avatar_row.stamina)
                before_daily = int(avatar_row.daily_actions_used)
                assist.spend_assist_battle(avatar_row, owner_ch)
                await session.commit()
                assert int(avatar_row.assist_stamina) < before_assist
                assert int(avatar_row.stamina) == before_explore
                assert int(avatar_row.daily_actions_used) == before_daily

                # 忙碌中不可再邀请
                with pytest.raises(AppError) as busy_exc:
                    await assist.invite(
                        borrower_user,
                        target_character_id=owner_ch.id,
                        target_name=None,
                    )
                assert "助战中" in busy_exc.value.message

                # PVE 战后离队
                ended = await assist.end_active_for_borrower(
                    borrower_ch.id,
                    reason="pve_battle_end",
                )
                await session.commit()
                assert ended == 1
                bench_after = await form.bench_units(borrower_ch)
                assert not any(b.get("is_guest") for b in bench_after)

                # 离队后可再邀
                again = await assist.invite(
                    borrower_user,
                    target_character_id=owner_ch.id,
                    target_name=None,
                )
                await session.commit()
                assert again["session"]["status"] == "active"

                from app.services.autochess_service import AutochessService

                with pytest.raises(AppError) as pvp_exc:
                    AutochessService._reject_guest_units(units, mode="PVP")
                assert pvp_exc.value.code == 40041

    _run(_body())


def test_assist_stamina_zero_requires_resume(tmp_path: Path) -> None:
    """助战体力归零锁定，须恢复到阈值才可再助战。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "assist_lock.db") as factory:
            async with factory() as session:
                owner_user = await _register(session, "lock_a@example.com", "锁甲")
                await _huashen_with_avatar(session, owner_user)
                owner_ch = await character_service.get_character_by_user_id(
                    session, owner_user.id,
                )
                assert owner_ch is not None
                avatar_row = (
                    await session.execute(
                        select(Avatar).where(Avatar.character_id == owner_ch.id),
                    )
                ).scalar_one()
                assist = AvatarAssistService(session)
                assist.refresh_assist_stamina(avatar_row, owner_ch, persist=True)
                avatar_row.assist_stamina = 0
                avatar_row.assist_stamina_locked = 1
                await session.flush()
                with pytest.raises(AppError) as exc:
                    assist.assert_can_lend(avatar_row, owner_ch)
                assert "恢复" in exc.value.message

    _run(_body())
