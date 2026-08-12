"""
道友化身助战竖切：好友 → 开开关 → 邀请（离线自动 accept）→ bench 客串 → validate → spend。
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


def test_friend_assist_auto_accept_bench_validate_spend(tmp_path: Path) -> None:
    """
    主人开助战 → 道友邀请（主人离线自动 active）→ bench 含 guest →
    validate 可上阵 → spend_avatar_action(assist_battle) 扣主人体力。
    """

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "assist_pve.db") as factory:
            async with factory() as session:
                owner_user = await _register(session, "assist_owner@example.com", "助甲")
                borrower_user = await _register(session, "assist_borrow@example.com", "助乙")

                await _huashen_with_avatar(session, owner_user)
                # 借用人也到化神，便于同场编成（非必须，但便于断言）
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

                # 结为道友
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
                # 主人开开关
                settings_res = await assist.set_assist_settings(owner_user, enabled=True)
                await session.commit()
                assert settings_res["assist_friends_enabled"] is True

                # 离线自动 accept（assist_dev_assume_online=false + 无 WS）
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

                # bench 含客串化身
                form = FormationService(session)
                bench = await form.bench_units(borrower_ch)
                guests = [
                    b for b in bench
                    if b.get("is_guest") or str(b.get("unit_uid", "")).startswith("avatar_guest_")
                ]
                assert len(guests) == 1
                assert guests[0]["unit_uid"] == expected_uid
                assert guests[0]["enabled"] is True
                assert "助甲" in guests[0]["name"]

                # 校验可放入进攻编成（含本体 + 客串）
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

                # PVE spend 路径：扣主人化身 assist_battle
                av_svc = AvatarService(session)
                av_svc.refresh_stamina_state(avatar_row, owner_ch, persist=True)
                await session.flush()
                before = int(avatar_row.stamina)
                av_svc.spend_avatar_action(
                    avatar_row,
                    owner_ch,
                    action_key="assist_battle",
                )
                await session.commit()
                assert int(avatar_row.stamina) < before
                assert int(avatar_row.daily_actions_used) >= 1

                # 忙碌中不可再邀请
                with pytest.raises(AppError) as exc:
                    await assist.invite(
                        borrower_user,
                        target_character_id=owner_ch.id,
                        target_name=None,
                    )
                assert "助战" in exc.value.message

                # PVP 拒客串
                from app.services.autochess_service import AutochessService

                with pytest.raises(AppError) as pvp_exc:
                    AutochessService._reject_guest_units(units, mode="PVP")
                assert pvp_exc.value.code == 40041

    _run(_body())


def test_friend_assist_online_requires_accept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """主人在线时邀请保持 invited，须手动 accept。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "assist_online.db") as factory:
            async with factory() as session:
                monkeypatch.setattr(
                    AvatarAssistService,
                    "_is_owner_online",
                    lambda self, owner_character_id: True,
                )
                owner_user = await _register(session, "assist_on_a@example.com", "在甲")
                borrower_user = await _register(session, "assist_on_b@example.com", "在乙")
                await _huashen_with_avatar(session, owner_user)

                friends = FriendService(session)
                applied = await friends.apply(
                    borrower_user,
                    target_character_id=None,
                    target_name="在甲",
                )
                await session.commit()
                await friends.accept(owner_user, int(applied["friendship_id"]))
                await session.commit()

                assist = AvatarAssistService(session)
                await assist.set_assist_settings(owner_user, enabled=True)
                await session.commit()

                invited = await assist.invite(
                    borrower_user,
                    target_character_id=None,
                    target_name="在甲",
                )
                await session.commit()
                assert invited["auto_accepted"] is False
                assert invited["session"]["status"] == "invited"

                # 借入人 bench 尚无客串
                borrower_ch = await character_service.get_character_by_user_id(
                    session, borrower_user.id,
                )
                assert borrower_ch is not None
                bench = await FormationService(session).bench_units(borrower_ch)
                assert not any(b.get("is_guest") for b in bench)

                accepted = await assist.accept(
                    owner_user,
                    int(invited["session"]["id"]),
                )
                await session.commit()
                assert accepted["session"]["status"] == "active"
                bench2 = await FormationService(session).bench_units(borrower_ch)
                assert any(b.get("is_guest") for b in bench2)

    _run(_body())
