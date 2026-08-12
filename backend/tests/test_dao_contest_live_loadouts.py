"""道主之争：开打瞬间双方现场进攻编成（不依赖旧防守快照）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Character, DefenseSnapshot, User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.services import auth_service, character_service
from app.services.dao_contest_service import DaoContestService, _SPECTATE_SLOTS
from app.services.formation_service import FormationService
from app.services.gm_service import GmService
from app.services.realm_config import clear_game_config_cache
from app.services.snapshot_service import SnapshotService
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
    monkeypatch.setattr(settings, "dao_system_enabled", True)
    monkeypatch.setattr(settings, "dao_lord_enabled", True)
    monkeypatch.setattr(settings, "pve_require_preset", False)
    clear_game_config_cache()
    _SPECTATE_SLOTS.clear()
    yield
    clear_game_config_cache()
    _SPECTATE_SLOTS.clear()


async def _mk_user(session, email: str, name: str) -> User:
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
    await GmService(session).gm_set_character(
        user,
        force_true_immortal=True,
        lock_fate_dao="dao_flame",
        set_dao_level=2,
    )
    await session.commit()
    return user


def test_duel_uses_live_attack_presets_not_stale_snapshot(tmp_path: Path) -> None:
    """乙方改进攻预设后开打应读到新阵法；旧 DefenseSnapshot 不得覆盖。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "contest_live_loadout.db") as factory:
            async with factory() as session:
                ua = await _mk_user(session, "live_lo_a@example.com", "甲方")
                ub = await _mk_user(session, "live_lo_b@example.com", "乙方")
                ca = (
                    await session.execute(
                        select(Character).where(Character.user_id == ua.id),
                    )
                ).scalar_one()
                cb = (
                    await session.execute(
                        select(Character).where(Character.user_id == ub.id),
                    )
                ).scalar_one()

                form = FormationService(session)
                units = [
                    {"unit_uid": "main", "unit_kind": "main", "x": 0, "y": 3},
                    {"unit_uid": "puppet_1", "unit_kind": "puppet", "x": 1, "y": 2},
                ]
                await form.save_preset(
                    ca,
                    0,
                    name="甲进攻",
                    role="attack",
                    formation_id="stone_wall_left",
                    units=units,
                )
                await form.save_preset(
                    cb,
                    0,
                    name="乙进攻",
                    role="attack",
                    formation_id="mist_domain",
                    units=units,
                )
                await session.commit()

                # 故意写入过时防守快照（formation=none、单本体）——现场编成不应吃它
                snaps = SnapshotService(session)
                row = await snaps.ensure_snapshot(cb)
                stale = {
                    "schema_version": 1,
                    "character_id": cb.id,
                    "formation_id": "none",
                    "units": [
                        {
                            "unit_uid": "main",
                            "unit_kind": "main",
                            "x": 0,
                            "y": 3,
                            "atk": 1,
                            "hp": 1,
                            "speed": 5,
                            "name": "stale",
                        },
                    ],
                    "content_hash": "stale-test",
                }
                row.payload_json = json.dumps(stale, ensure_ascii=False)
                row.content_hash = "stale-test"
                await session.commit()

                svc = DaoContestService(session)
                report, winner = await svc._duel_characters(
                    attacker_id=ca.id,
                    defender_id=cb.id,
                    defender_mode="live_attack",
                )
                assert winner in {ca.id, cb.id}
                loadouts = report.get("live_loadouts") or {}
                side_a = loadouts.get("side_a") or {}
                side_b = loadouts.get("side_b") or {}
                assert side_a.get("source") == "attack_preset_live"
                assert side_b.get("source") == "attack_preset_live"
                assert side_a.get("formation_id") == "stone_wall_left"
                assert side_b.get("formation_id") == "mist_domain"
                assert int(side_a.get("unit_count") or 0) == 2
                assert int(side_b.get("unit_count") or 0) == 2
                assert report.get("defender_mode") == "live_attack"

                # 库内快照仍是 stale，证明没有被赛会写回、也未被当作编成来源
                snap_row = (
                    await session.execute(
                        select(DefenseSnapshot).where(
                            DefenseSnapshot.character_id == cb.id,
                        ),
                    )
                ).scalar_one()
                stored = json.loads(snap_row.payload_json)
                assert stored.get("formation_id") == "none"
                assert len(stored.get("units") or []) == 1

    _run(_body())


def test_duel_frozen_snapshot_mode_still_reads_defense_snapshot(tmp_path: Path) -> None:
    """道主快照模式：乙方仍走库内防守快照。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "contest_frozen_lo.db") as factory:
            async with factory() as session:
                ua = await _mk_user(session, "froz_a@example.com", "挑战者")
                ub = await _mk_user(session, "froz_b@example.com", "道主")
                ca = (
                    await session.execute(
                        select(Character).where(Character.user_id == ua.id),
                    )
                ).scalar_one()
                cb = (
                    await session.execute(
                        select(Character).where(Character.user_id == ub.id),
                    )
                ).scalar_one()

                form = FormationService(session)
                units = [
                    {"unit_uid": "main", "unit_kind": "main", "x": 0, "y": 3},
                ]
                await form.save_preset(
                    ca,
                    0,
                    name="攻",
                    role="attack",
                    formation_id="stone_wall_left",
                    units=units,
                )
                # 进攻预设改成 mist，但防守快照保持 none —— frozen 模式应读 none
                await form.save_preset(
                    cb,
                    0,
                    name="道主进攻（不应被 frozen 使用）",
                    role="attack",
                    formation_id="mist_domain",
                    units=units,
                )
                await form.save_preset(
                    cb,
                    1,
                    name="道主防守",
                    role="defense",
                    formation_id="none",
                    units=units,
                )
                snaps = SnapshotService(session)
                await snaps.ensure_snapshot(cb)
                await snaps.manual_update(cb)  # 用防守预设刷库
                await session.commit()

                svc = DaoContestService(session)
                report, _winner = await svc._duel_characters(
                    attacker_id=ca.id,
                    defender_id=cb.id,
                    defender_mode="frozen_defense_snapshot",
                )
                loadouts = report.get("live_loadouts") or {}
                side_b = loadouts.get("side_b") or {}
                assert side_b.get("source") == "defense_snapshot"
                assert side_b.get("formation_id") == "none"
                assert report.get("defender_mode") == "frozen_defense_snapshot"

    _run(_body())
