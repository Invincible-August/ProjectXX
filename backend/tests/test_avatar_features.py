"""
化身深化测试：功能解锁 / 互传折扣 / 体力 / 独战闸 / 任务桩（AVATAR-D01～D06）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.domain.avatar_rules import (
    ERR_FEATURE_LOCKED,
    ERR_SOLO_FORMATION_INVALID,
    compute_transfer_preview,
    is_feature_unlocked,
)
from app.domain.m4_constants import AvatarFeature
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.avatar_service import AvatarService
from app.services.craft_service import CraftService
from app.services.formation_service import FormationService
from app.services.gm_service import GmService
from app.services.realm_config import clear_game_config_cache, get_game_config

from tests.async_db import open_test_session_factory, run_async as _run


async def _user_with_character(session: AsyncSession, email: str) -> User:
    """注册并创角。"""
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
def _reload_config() -> None:
    """重置配置缓存。"""
    clear_game_config_cache()
    yield
    clear_game_config_cache()


def test_config_max_avatars_is_one() -> None:
    """配置硬约束：max_avatars=1。"""
    cfg = get_game_config().avatar
    assert cfg.max_avatars == 1
    assert AvatarFeature.IDLE_CRAFTING in cfg.feature_unlocks
    assert 0 < cfg.transfer.retention_ratio <= 1


def test_jindan_idle_crafting_rejected(tmp_path: Path) -> None:
    """金丹不可制造业方向 → 40090。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "af1.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "af01@example.com")
                await GmService(session).gm_set_character(
                    user, force_jindan=True, spirit_stones=5000,
                )
                await session.commit()
                svc = AvatarService(session)
                await svc.condense(user)
                await session.commit()
                with pytest.raises(AppError) as exc:
                    await svc.set_idle(user, "crafting")
                assert exc.value.code == ERR_FEATURE_LOCKED

    _run(_body())


def test_yuanying_idle_crafting_ok(tmp_path: Path) -> None:
    """元婴可制造业方向。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "af2.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "af02@example.com")
                await GmService(session).gm_set_character(
                    user, force_yuanying_peak=True, spirit_stones=5000,
                )
                await session.commit()
                svc = AvatarService(session)
                await svc.condense(user)
                await session.commit()
                panel = await svc.set_idle(user, "crafting")
                assert panel["idle_direction"] == "crafting"

    _run(_body())


def test_features_endpoint_explicit(tmp_path: Path) -> None:
    """GET features 含 label/summary；金丹未解锁 idle_crafting；含凝练闸。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "af3.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "af03@example.com")
                await GmService(session).gm_set_character(
                    user, force_jindan=True, spirit_stones=5000,
                )
                await session.commit()
                from app.services.play_gate import PlayGate

                character = await PlayGate(session).require_character(user)
                data = await AvatarService(session).get_features(character)
                assert data["major_realm"] == "jindan"
                by_id = {f["feature_id"]: f for f in data["features"]}
                assert by_id["idle_spirit"]["unlocked"] is True
                assert by_id["idle_crafting"]["unlocked"] is False
                assert by_id["idle_crafting"]["label_zh"]
                assert data["unlock_preview"] is not None
                assert data["unlock_preview"]["next_major"] == "yuanying"
                gate = data["condense"]
                assert gate["can_condense"] is True
                assert gate["realm_ok"] is True
                assert gate["stones_ok"] is True
                assert gate["has_avatar"] is False
                assert gate["unlock_major_realm"] == "jindan"

    _run(_body())


def test_features_condense_true_immortal_ok(tmp_path: Path) -> None:
    """真仙 ≥ 金丹门槛：凝练闸 can_condense=True（修复前端漏判同源规则）。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "af3b.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "af03b@example.com")
                await GmService(session).gm_set_character(
                    user,
                    force_true_immortal=True,
                    spirit_stones=5000,
                )
                await session.commit()
                from app.services.play_gate import PlayGate

                character = await PlayGate(session).require_character(user)
                data = await AvatarService(session).get_features(character)
                assert data["major_realm"] == "true_immortal"
                gate = data["condense"]
                assert gate["realm_ok"] is True
                assert gate["can_condense"] is True
                panel = await AvatarService(session).condense(user)
                assert panel["status"] == "idle"

    _run(_body())


def test_features_condense_blocked_low_realm(tmp_path: Path) -> None:
    """锻体/炼气：condense.realm_ok=False，block_code=40050。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "af3c.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "af03c@example.com")
                from app.services.play_gate import PlayGate

                character = await PlayGate(session).require_character(user)
                data = await AvatarService(session).get_features(character)
                gate = data["condense"]
                assert gate["can_condense"] is False
                assert gate["realm_ok"] is False
                assert gate["block_code"] == 40050

    _run(_body())


def test_transfer_retention_preview_and_apply(tmp_path: Path) -> None:
    """retention=0.8：传 100 → 发送方 -100，接收方 +80。"""
    preview = compute_transfer_preview(100, retention_ratio=0.8, min_amount=1)
    assert preview["gross"] == 100
    assert preview["net"] == 80
    assert preview["fee"] == 20

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "af4.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "af04@example.com")
                await GmService(session).gm_set_character(
                    user,
                    force_jindan=True,
                    spirit_stones=5000,
                    cultivation_points=500,
                )
                await session.commit()
                svc = AvatarService(session)
                await svc.condense(user)
                await session.commit()
                # 凝练后化身修为=本体当时池；再给本体补池便于互传
                from app.services.play_gate import PlayGate

                character = await PlayGate(session).require_character(user)
                character.cultivation_points = 200
                await session.commit()

                prev = await svc.transfer_preview(
                    user,
                    direction="main_to_avatar",
                    resource="cultivation_points",
                    amount=100,
                )
                assert prev["ok"] is True
                assert prev["net"] == 80

                avatar_before = await svc.get_avatar_row(character.id)
                assert avatar_before is not None
                av_cult_before = int(avatar_before.cultivation_points)
                main_before = int(character.cultivation_points)

                result = await svc.transfer(
                    user,
                    direction="main_to_avatar",
                    resource="cultivation_points",
                    amount=100,
                )
                assert result["gross"] == 100
                assert result["net"] == 80
                assert result["main_cultivation"] == main_before - 100
                assert result["avatar_cultivation"] == av_cult_before + 80

    _run(_body())


def test_workshop_actor_gate(tmp_path: Path) -> None:
    """金丹 actor=avatar 工坊拒绝；元婴允许。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "af5.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "af05@example.com")
                await GmService(session).gm_set_character(
                    user, force_jindan=True, spirit_stones=50000,
                )
                await session.commit()
                await AvatarService(session).condense(user)
                await session.commit()
                craft = CraftService(session)
                recipes = list(get_game_config().craft_recipes.recipes.keys())
                assert recipes
                rid = recipes[0]
                with pytest.raises(AppError) as exc:
                    await craft.start(user, recipe_id=rid, actor="avatar")
                assert exc.value.code == ERR_FEATURE_LOCKED

                await GmService(session).gm_set_character(
                    user, force_yuanying_peak=True, spirit_stones=50000,
                )
                await session.commit()
                # 元婴后仍可能因材料/体力失败，但不应再是 40090
                try:
                    await craft.start(user, recipe_id=rid, actor="avatar")
                except AppError as err:
                    assert err.code != ERR_FEATURE_LOCKED

    _run(_body())


def test_solo_battle_formation_gate(tmp_path: Path) -> None:
    """化神前无本体编成拒绝 40093；化神后可存。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "af6.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "af06@example.com")
                await GmService(session).gm_set_character(
                    user, force_jindan=True, spirit_stones=5000,
                )
                await session.commit()
                av_svc = AvatarService(session)
                panel = await av_svc.condense(user)
                await session.commit()
                avatar_id = panel["id"]

                from app.services.play_gate import PlayGate

                character = await PlayGate(session).require_character(user)
                form_svc = FormationService(session)
                solo_units = [
                    {
                        "unit_uid": f"avatar_{avatar_id}",
                        "unit_kind": "avatar",
                        "ref_id": avatar_id,
                        "x": 0,
                        "y": 3,
                    },
                ]
                with pytest.raises(AppError) as exc:
                    await form_svc.validate_units(character, solo_units, "none")
                assert exc.value.code == ERR_SOLO_FORMATION_INVALID

                # 抬到化神
                await GmService(session).gm_set_character(
                    user, major_realm="huashen", realm_stage=1, spirit_stones=5000,
                )
                await session.commit()
                character = await PlayGate(session).require_character(user)
                assert is_feature_unlocked(
                    character.major_realm,
                    AvatarFeature.SOLO_BATTLE,
                    feature_unlocks=get_game_config().avatar.feature_unlocks,
                    realms=get_game_config().realms,
                )
                await form_svc.validate_units(character, solo_units, "none")

    _run(_body())


def test_stamina_spend_and_daily(tmp_path: Path) -> None:
    """元婴体力不足 / 日行动用尽。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "af7.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "af07@example.com")
                await GmService(session).gm_set_character(
                    user, force_yuanying_peak=True, spirit_stones=5000,
                )
                await session.commit()
                svc = AvatarService(session)
                await svc.condense(user)
                await session.commit()
                from app.services.play_gate import PlayGate

                character = await PlayGate(session).require_character(user)
                avatar = await svc.get_avatar_row(character.id)
                assert avatar is not None
                panel = svc.refresh_stamina_state(avatar, character)
                assert panel is not None
                assert panel["stamina"] > 0

                avatar.stamina = 1
                with pytest.raises(AppError) as exc:
                    svc.spend_avatar_action(avatar, character, action_key="solo_battle")
                assert exc.value.code == 40091

                # 灌满体力但日行动耗尽
                avatar.stamina = 100
                avatar.daily_actions_used = get_game_config().avatar.stamina.daily_action_cap
                from app.domain.avatar_rules import utc_day_key
                from app.core.time_utils import now_utc

                avatar.daily_actions_day = utc_day_key(now_utc())
                with pytest.raises(AppError) as exc2:
                    svc.spend_avatar_action(avatar, character, action_key="quest_accept")
                assert exc2.value.code == 40092

    _run(_body())


def test_quest_stub(tmp_path: Path) -> None:
    """未解锁拒；解锁后桩 50110。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "af8.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "af08@example.com")
                await GmService(session).gm_set_character(
                    user, force_jindan=True, spirit_stones=5000,
                )
                await session.commit()
                svc = AvatarService(session)
                await svc.condense(user)
                await session.commit()
                with pytest.raises(AppError) as exc:
                    await svc.quest_accept_stub(user, quest_kind="npc")
                assert exc.value.code == ERR_FEATURE_LOCKED

                await GmService(session).gm_set_character(
                    user, major_realm="huashen", realm_stage=1, spirit_stones=5000,
                )
                await session.commit()
                # 化神解锁 quest；体力也需元婴+（化神已具备）
                result = await svc.quest_accept_stub(user, quest_kind="npc")
                assert result["code"] == 50110
                assert result["implemented"] is False

    _run(_body())
