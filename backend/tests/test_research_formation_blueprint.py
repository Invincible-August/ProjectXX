"""
M8 R3: custom formation research session / draft / finalize / picker / snapshot inline.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import PrivateFormation, User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.formation_service import FormationService
from app.services.inventory_service import InventoryService
from app.services.realm_config import clear_game_config_cache, get_game_config
from app.services.research_service import ResearchService
from app.services.snapshot_service import SnapshotService
from tests.async_db import open_test_session_factory, run_async as _run


@pytest.fixture(autouse=True)
def _cfg(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    monkeypatch.setattr(settings, "app_env", "development")
    clear_game_config_cache()
    yield
    clear_game_config_cache()


async def _prepare_researcher(session, email: str, name: str):
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
    char = await character_service.get_character_by_user_id(session, user.id)
    assert char is not None
    char.cultivation_points = 200
    await InventoryService(session).add_item(
        char.id,
        item_type="material",
        item_id="herb_spirit_grass",
        quantity=10,
    )
    await session.commit()
    return char


def _free_own_blueprint(*, terrain: list[dict]) -> dict:
    return {
        "deploy": {
            "mode": "free_own",
            "cells": [],
            "add_cells": [],
            "exclude_cells": [],
            "allow_neutral": False,
        },
        "terrain_layout": get_game_config().research.formation.terrain_layout,
        "terrain": terrain,
        "force_shifts": [],
    }


def test_research_catalog_opens_formation() -> None:
    cfg = get_game_config()
    assert cfg.research.formation.min_materials >= 1
    catalog = ResearchService(MagicMock()).get_catalog()
    kinds = {k["id"]: k["open"] for k in catalog["kinds"]}
    assert kinds["formation"] is True
    assert kinds["talisman"] is True


def test_formation_finalize_picker_and_snapshot_inline(tmp_path: Path) -> None:
    """Draft → finalize → picker; snapshot keeps inline blueprint after author row mutates."""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "r3form.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "r3form@test.com", "阵研甲")
                svc = ResearchService(session)
                created = await svc.create_session(
                    char,
                    kind="formation",
                    materials=[{"item_id": "herb_spirit_grass", "quantity": 1}],
                    spends={"cultivation_points": 10},
                )
                assert created["kind"] == "formation"
                assert created["phase"] == "drafting"
                assert created["dice"]["purpose"] == "research_formation"
                sid = int(created["id"])
                saved = await svc.save_formation_draft(
                    char,
                    sid,
                    _free_own_blueprint(
                        terrain=[
                            {"x": 1, "y": 1, "type": "obstacle", "subtype": "destructible"},
                        ],
                    ),
                )
                assert saved["blueprint"]["terrain"][0]["x"] == 1
                finalized = await svc.finalize_session(
                    char,
                    session_id=sid,
                    label_zh="青岚拒马",
                )
                await session.commit()
                assert finalized["phase"] == "finalized"
                fid = finalized["private"]["id"]
                assert fid.startswith("custom:formation:")

                with pytest.raises(AppError) as frozen_exc:
                    await svc.save_formation_draft(
                        char,
                        sid,
                        _free_own_blueprint(terrain=[]),
                    )
                assert frozen_exc.value.code == 40206

                mine = await svc.list_mine(char)
                assert any(i["id"] == fid and i["kind"] == "formation" for i in mine)

                form_svc = FormationService(session)
                resolved = await form_svc.resolve_formation_def(fid, char)
                assert resolved.name == "青岚拒马"
                assert len(resolved.terrain) == 1

                presets = await form_svc.list_presets(char)
                custom = next(f for f in presets["formations"] if f["formation_id"] == fid)
                assert custom["source"] == "custom"
                assert custom["unlocked"] is True

                await form_svc.save_preset(
                    char,
                    1,
                    name="自研防阵",
                    role="defense",
                    formation_id=fid,
                    units=[
                        {"unit_uid": "main", "unit_kind": "main", "x": 0, "y": 3},
                    ],
                )
                snap_svc = SnapshotService(session)
                updated = await snap_svc.manual_update(char)
                payload = updated["snapshot"]
                assert payload["formation_id"] == fid
                assert payload["formation_name"] == "青岚拒马"
                assert payload["formation_blueprint"]["terrain"][0]["y"] == 1

                private = (
                    await session.execute(
                        select(PrivateFormation).where(PrivateFormation.formation_id == fid),
                    )
                ).scalar_one()
                mutated = json.loads(private.blueprint_json)
                mutated["terrain"] = []
                private.blueprint_json = json.dumps(mutated, ensure_ascii=False)
                await session.flush()

                live = await form_svc.resolve_formation_def(fid, char)
                assert live.terrain == ()
                battle_payload = await snap_svc.load_payload_for_battle(char.id)
                assert battle_payload["formation_blueprint"]["terrain"][0]["y"] == 1
                preview = await snap_svc.preview_for_attack(char.id)
                assert preview["formation_name"] == "青岚拒马"

    _run(_body())


def test_formation_brush_over_budget_rejected(tmp_path: Path) -> None:
    """Too many obstacles → 40202 on finalize."""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "r3bad.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "r3bad@test.com", "越刷乙")
                svc = ResearchService(session)
                created = await svc.create_session(
                    char,
                    kind="formation",
                    materials=[{"item_id": "herb_spirit_grass", "quantity": 1}],
                    spends={"cultivation_points": 10},
                )
                terrain = [
                    {"x": 0, "y": y, "type": "obstacle", "subtype": "destructible"}
                    for y in range(4)
                ]
                await svc.save_formation_draft(
                    char,
                    int(created["id"]),
                    _free_own_blueprint(terrain=terrain),
                )
                with pytest.raises(AppError) as exc:
                    await svc.finalize_session(
                        char,
                        session_id=int(created["id"]),
                        label_zh="超额障碍阵",
                    )
                assert exc.value.code == 40202

    _run(_body())


def test_formation_enemy_half_terrain_rejected(tmp_path: Path) -> None:
    """Terrain on the enemy half → 40202 on finalize."""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "r3zone.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "r3zone@test.com", "越区丙")
                svc = ResearchService(session)
                created = await svc.create_session(
                    char,
                    kind="formation",
                    materials=[{"item_id": "herb_spirit_grass", "quantity": 1}],
                    spends={"cultivation_points": 10},
                )
                enemy_x = int(get_game_config().board.zones.enemy_x[0])
                await svc.save_formation_draft(
                    char,
                    int(created["id"]),
                    _free_own_blueprint(
                        terrain=[
                            {
                                "x": enemy_x,
                                "y": 3,
                                "type": "obstacle",
                                "subtype": "destructible",
                            },
                        ],
                    ),
                )
                with pytest.raises(AppError) as exc:
                    await svc.finalize_session(
                        char,
                        session_id=int(created["id"]),
                        label_zh="越区拒马",
                    )
                assert exc.value.code == 40202

    _run(_body())
