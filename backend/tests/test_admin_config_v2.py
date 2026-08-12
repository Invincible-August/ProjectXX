"""
ADM 深化：sects/map/activity、条目 upsert、导入导出。
"""

from __future__ import annotations

from pathlib import Path

from app.config_source.overlay_store import OverlayStore
from app.core.security import hash_password
from app.db.models import AdminUser
from app.services.admin_config_service import AdminConfigService
from app.services.admin_io import csv_to_entries, entries_to_csv
from app.services.admin_rbac import roles_to_storage
from app.services.realm_config import clear_game_config_cache, get_game_config
from tests.async_db import open_test_session_factory, run_async


def test_sects_map_activity_loaded_in_bundle() -> None:
    """新域 YAML 进入 Bundle。"""
    OverlayStore.replace_all({})
    clear_game_config_cache()
    cfg = get_game_config()
    assert "spirit_beast_sect" in cfg.sects.facilities
    assert cfg.sects.facilities["spirit_beast_sect"]["enabled"] is False
    assert "default" in cfg.map.regions
    assert "placeholder_double_idle" in cfg.activity.activities


def test_csv_roundtrip_entries() -> None:
    """CSV 导出再导入保留 id。"""
    table = {
        "a": {"name": "甲", "base_atk": 1},
        "b": {"name": "乙", "tags": ["x"]},
    }
    text = entries_to_csv("pets", table)
    back = csv_to_entries(text)
    assert set(back.keys()) == {"a", "b"}
    assert back["a"]["name"] == "甲"
    assert back["b"]["tags"] == ["x"]


def test_upsert_entry_and_publish_facility(tmp_path: Path) -> None:
    """sects 设施开关经条目 upsert 发布后 Bundle 反映。"""

    async def _run() -> None:
        OverlayStore.replace_all({})
        clear_game_config_cache()
        assert get_game_config().sects.facilities["spirit_beast_sect"]["enabled"] is False

        async with open_test_session_factory(tmp_path / "adm2.db") as factory:
            async with factory() as session:
                admin = AdminUser(
                    username="ops2",
                    password_hash=hash_password("ops-pass-123"),
                    display_name="Ops2",
                    roles=roles_to_storage(
                        ["viewer", "editor_content", "publisher", "admin"],
                    ),
                    is_active=True,
                )
                session.add(admin)
                await session.commit()
                await session.refresh(admin)

                svc = AdminConfigService(session)
                await svc.upsert_entry(
                    "sects",
                    "spirit_beast_sect",
                    {"enabled": True, "note": "联调开放"},
                    admin=admin,
                )
                await svc.publish("sects", admin=admin, note="open facility")

        cfg = get_game_config()
        assert cfg.sects.facilities["spirit_beast_sect"]["enabled"] is True

        OverlayStore.replace_all({})
        clear_game_config_cache()
        get_game_config()

    run_async(_run())


def test_pets_species_upsert(tmp_path: Path) -> None:
    """pets 条目 upsert 发布后物种出现。"""

    async def _run() -> None:
        OverlayStore.replace_all({})
        clear_game_config_cache()

        async with open_test_session_factory(tmp_path / "adm3.db") as factory:
            async with factory() as session:
                admin = AdminUser(
                    username="ops3",
                    password_hash=hash_password("ops-pass-123"),
                    display_name="Ops3",
                    roles=roles_to_storage(
                        ["viewer", "editor_content", "publisher", "admin"],
                    ),
                    is_active=True,
                )
                session.add(admin)
                await session.commit()
                await session.refresh(admin)
                svc = AdminConfigService(session)
                await svc.upsert_entry(
                    "pets",
                    "table_pet_owl",
                    {
                        "name": "表编灵鸮",
                        "race": "beast",
                        "rarity": "common",
                        "roles": ["dps"],
                        "acquire_tags": ["gm_grant"],
                        "base_atk": 5,
                        "base_hp": 25,
                        "base_speed": 11,
                        "upgrade_cost": {"spirit_stones": 1, "materials": []},
                    },
                    admin=admin,
                )
                await svc.publish("pets", admin=admin, note="entry")

        assert "table_pet_owl" in get_game_config().pets.species
        OverlayStore.replace_all({})
        clear_game_config_cache()
        get_game_config()

    run_async(_run())
