"""
M2-D01 / ADM：配置覆盖层合并、发布热更、与玩家 Bundle 隔离鉴权。
"""

from __future__ import annotations

from pathlib import Path

from app.config_source.merge import deep_merge
from app.config_source.overlay_store import OverlayStore
from app.core.security import (
    create_access_token,
    create_admin_access_token,
    decode_admin_token,
    decode_token,
    hash_password,
)
from app.db.models import AdminUser
from app.services.admin_auth_service import AdminAuthService
from app.services.admin_config_service import AdminConfigService
from app.services.admin_rbac import roles_to_storage
from app.services.realm_config import clear_game_config_cache, get_game_config
from tests.async_db import open_test_session_factory, run_async


def test_deep_merge_nested_species() -> None:
    """覆盖层只增物种时保留 YAML 原有键。"""
    base = {"hold_cap": 5, "species": {"a": {"name": "甲"}}}
    overlay = {"species": {"b": {"name": "乙", "base_atk": 1, "base_hp": 1, "base_speed": 1}}}
    merged = deep_merge(base, overlay)
    assert merged["hold_cap"] == 5
    assert "a" in merged["species"] and "b" in merged["species"]


def test_player_token_rejected_as_admin_and_vice_versa() -> None:
    """玩家 / 后台 JWT 不可互用。"""
    OverlayStore.replace_all({})
    player_token, _ = create_access_token(1)
    admin_token, _ = create_admin_access_token(1, roles=["admin"])

    claims = decode_token(player_token, expected_type="access")
    assert claims["sub"] == "1"

    admin_claims = decode_admin_token(admin_token)
    assert admin_claims["aud"] == "admin"

    try:
        decode_admin_token(player_token)
        assert False, "player token must not decode as admin"
    except Exception:
        pass

    try:
        decode_token(admin_token, expected_type="access")
        assert False, "admin token must not decode as player"
    except Exception:
        pass


def test_publish_pets_overlay_hot_reloads_bundle(tmp_path: Path) -> None:
    """发布 pets 覆盖后 Bundle.species 出现新物种，无需改 YAML 文件。"""

    async def _run() -> None:
        OverlayStore.replace_all({})
        clear_game_config_cache()
        before = get_game_config()
        assert "admin_smoke_pet" not in before.pets.species

        async with open_test_session_factory(tmp_path / "adm.db") as factory:
            async with factory() as session:
                admin = AdminUser(
                    username="ops",
                    password_hash=hash_password("ops-pass-123"),
                    display_name="Ops",
                    roles=roles_to_storage(
                        ["viewer", "editor_content", "publisher", "admin"],
                    ),
                    is_active=True,
                )
                session.add(admin)
                await session.commit()
                await session.refresh(admin)

                svc = AdminConfigService(session)
                overlay = {
                    "species": {
                        "admin_smoke_pet": {
                            "name": "后台烟宠",
                            "race": "beast",
                            "rarity": "common",
                            "roles": ["dps"],
                            "acquire_tags": ["gm_grant"],
                            "base_atk": 3,
                            "base_hp": 20,
                            "base_speed": 8,
                            "upgrade_cost": {
                                "spirit_stones": 10,
                                "materials": [],
                            },
                        },
                    },
                }
                await svc.save_draft("pets", overlay, admin=admin)
                result = await svc.publish("pets", admin=admin, note="smoke")
                assert result["version"] == 1

        after = get_game_config()
        assert "admin_smoke_pet" in after.pets.species
        assert after.pets.species["admin_smoke_pet"].name == "后台烟宠"

        # 清理，避免污染同进程其它用例
        OverlayStore.replace_all({})
        clear_game_config_cache()
        get_game_config()

    run_async(_run())


def test_bootstrap_admin_once(tmp_path: Path) -> None:
    """bootstrap 仅在空库创建一次。"""

    async def _run() -> None:
        async with open_test_session_factory(tmp_path / "boot.db") as factory:
            async with factory() as session:
                auth = AdminAuthService(session)
                await auth.ensure_bootstrap_admin()
                await auth.ensure_bootstrap_admin()
                data = await auth.login(username="admin", password="admin123")
                assert data["access_token"]
                assert "admin" in data["user"]["roles"]

    run_async(_run())
