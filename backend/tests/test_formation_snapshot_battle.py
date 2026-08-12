"""
布阵预设 / 防守快照 / 棋盘化战斗编排集成测试（M3 · S2/S3/S6）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.autochess_service import AutochessService
from app.services.formation_service import FormationService
from app.services.realm_config import clear_game_config_cache
from app.services.snapshot_service import SnapshotService

from tests.async_db import open_test_session_factory, run_async as _run

_NOW = datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc)


async def _prepare(session: AsyncSession, email: str, name: str) -> User:
    """注册 + 创角。"""
    await auth_service.register_user(
        session,
        RegisterRequest(password="password123", email=email),
    )
    await session.commit()
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    await character_service.create_character(
        session,
        user,
        CreateCharacterRequest(name=name),
    )
    await session.commit()
    return user


@pytest.fixture(autouse=True)
def _cfg(monkeypatch: pytest.MonkeyPatch) -> None:
    """开发态配置：固定演算种子保证测试可复现。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "autochess_rng_seed", 20260805)
    clear_game_config_cache()
    yield
    clear_game_config_cache()


def test_default_presets_and_save(tmp_path: Path) -> None:
    """默认三槽惰性种子；保存校验；非法占位报 40041。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "formation.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "fmt01@example.com", "布阵者")
                character = await character_service.get_character_by_user_id(
                    session,
                    user.id,
                )
                assert character is not None
                service = FormationService(session)

                data = await service.list_presets(character)
                assert len(data["presets"]) == 3
                assert data["max_units"] == 3  # 锻体期
                assert any(b["unit_kind"] == "puppet" for b in data["bench"])
                assert any(f["formation_id"] == "none" for f in data["formations"])

                # 合法保存：本体 + 一个傀儡
                saved = await service.save_preset(
                    character,
                    0,
                    name="我的攻阵",
                    role="attack",
                    formation_id="none",
                    units=[
                        {"unit_uid": "main", "unit_kind": "main", "x": 0, "y": 3},
                        {"unit_uid": "puppet_1", "unit_kind": "puppet", "x": 1, "y": 2},
                    ],
                )
                await session.commit()
                assert saved["name"] == "我的攻阵"
                assert len(saved["units"]) == 2

                # 非法：中立列落子
                with pytest.raises(AppError) as exc:
                    await service.save_preset(
                        character,
                        0,
                        name="非法",
                        role="attack",
                        formation_id="none",
                        units=[{"unit_uid": "main", "unit_kind": "main", "x": 3, "y": 3}],
                    )
                assert exc.value.code == 40041

                # 非法：傀儡超持有量（默认 1 个）
                with pytest.raises(AppError) as exc:
                    await service.save_preset(
                        character,
                        0,
                        name="超编",
                        role="attack",
                        formation_id="none",
                        units=[
                            {"unit_uid": "main", "unit_kind": "main", "x": 0, "y": 3},
                            {"unit_uid": "puppet_1", "unit_kind": "puppet", "x": 1, "y": 2},
                            {"unit_uid": "puppet_2", "unit_kind": "puppet", "x": 1, "y": 3},
                        ],
                    )
                assert exc.value.code == 40041

    _run(_body())


def test_snapshot_manual_update_cooldown(tmp_path: Path) -> None:
    """手动更新成功后 1 小时冷却 → 40045；冷却后可再次更新。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "snapshot.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "snap01@example.com", "快照者")
                character = await character_service.get_character_by_user_id(
                    session,
                    user.id,
                )
                assert character is not None
                service = SnapshotService(session)

                first = await service.manual_update(character, now=_NOW)
                await session.commit()
                assert first["snapshot"]["units"]
                assert first["snapshot"]["content_hash"]

                # 冷却中再更 → 40045
                with pytest.raises(AppError) as exc:
                    await service.manual_update(
                        character,
                        now=_NOW + timedelta(minutes=10),
                    )
                assert exc.value.code == 40045

                # 冷却过后可更新
                second = await service.manual_update(
                    character,
                    now=_NOW + timedelta(hours=1, seconds=1),
                )
                assert second["snapshot"]["content_hash"]

    _run(_body())


def test_pve_autochess_flow(tmp_path: Path) -> None:
    """棋盘化 PVE：无预设走本体锚点；返回 M3 战报 + 扣体力 + 奖励。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "pve_ac.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "acpve01@example.com", "棋盘讨伐者")
                service = AutochessService(session)

                data = await service.start_pve(user, "tutorial_slime", now=_NOW)
                await session.commit()

                report = data["report"]
                assert report["schema_version"] == 1
                assert report["seed"] == 20260805
                assert report["events"][0]["type"] == "battle_start"
                assert report["events"][-1]["type"] == "battle_end"
                assert "y\\x" in report["board_text"]
                assert report["detailed_log"]
                # 体力已扣（教学怪走默认 battle_pve 消耗）
                assert data["stamina"]["left"] < data["stamina"]["cap"]
                # 战报不落库：结果与奖励字段齐备
                assert data["result"] in ("win", "lose")
                assert "cultivation_points" in data["rewards"]

    _run(_body())


def test_pve_insufficient_stamina(tmp_path: Path) -> None:
    """体力不足开战 → 40049，引擎不被调用（角色资源零变化）。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "pve_nostam.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "acpve02@example.com", "力竭讨伐者")
                character = await character_service.get_character_by_user_id(
                    session,
                    user.id,
                )
                assert character is not None
                character.stamina = 0
                character.stamina_updated_at = _NOW
                await session.commit()
                before = int(character.cultivation_points)

                with pytest.raises(AppError) as exc:
                    await AutochessService(session).start_pve(
                        user,
                        "tutorial_slime",
                        now=_NOW,
                    )
                assert exc.value.code == 40049
                assert int(character.cultivation_points) == before

    _run(_body())


def test_pvp_attack_snapshot(tmp_path: Path) -> None:
    """PVP：攻打对方快照；防守方资源零变化；不能打自己。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "pvp.db") as factory:
            async with factory() as session:
                attacker = await _prepare(session, "pvp_a@example.com", "攻方道人")
                defender = await _prepare(session, "pvp_d@example.com", "守方道人")
                defender_char = await character_service.get_character_by_user_id(
                    session,
                    defender.id,
                )
                assert defender_char is not None
                # 守方生成快照
                await SnapshotService(session).manual_update(defender_char, now=_NOW)
                await session.commit()
                defender_stones_before = int(defender_char.spirit_stones)

                service = AutochessService(session)
                data = await service.start_pvp(
                    attacker,
                    target_character_id=defender_char.id,
                    now=_NOW,
                )
                await session.commit()
                assert data["mode"] == "pvp"
                assert data["target"]["character_id"] == defender_char.id
                assert data["report"]["events"]
                # 守方零打扰：资源不变
                await session.refresh(defender_char)
                assert int(defender_char.spirit_stones) == defender_stones_before

                # 不能攻打自己
                attacker_char = await character_service.get_character_by_user_id(
                    session,
                    attacker.id,
                )
                assert attacker_char is not None
                with pytest.raises(AppError) as exc:
                    await service.start_pvp(
                        attacker,
                        target_character_id=attacker_char.id,
                        now=_NOW,
                    )
                assert exc.value.code == 40047

    _run(_body())


def test_pvp_no_snapshot_target(tmp_path: Path) -> None:
    """目标无快照 → 40048。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "pvp_miss.db") as factory:
            async with factory() as session:
                attacker = await _prepare(session, "pvp_b@example.com", "扑空道人")
                with pytest.raises(AppError) as exc:
                    await AutochessService(session).start_pvp(
                        attacker,
                        target_character_id=99999,
                        now=_NOW,
                    )
                assert exc.value.code == 40048

    _run(_body())
