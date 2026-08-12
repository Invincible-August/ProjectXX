"""
M4-D04c 野外遭遇与捕获测试。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.inventory_service import InventoryService
from app.services.pet_explore_service import PetExploreService, PetExploreSessionStore
from app.services.pet_service import PetService
from app.services.realm_config import clear_game_config_cache, get_game_config

from tests.async_db import open_test_session_factory, run_async as _run


async def _user_with_character(session: AsyncSession, email: str) -> User:
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
    clear_game_config_cache()
    PetExploreSessionStore.clear_all()
    yield
    clear_game_config_cache()
    PetExploreSessionStore.clear_all()


def test_pet_encounter_config_hotplug() -> None:
    """遭遇/捕获配置外键与诱灵草道具齐全。"""
    bundle = get_game_config()
    assert bundle.pet_encounter.tables
    assert "spirit_beast" in bundle.pet_encounter.capturable_types
    assert bundle.pet_capture.lure_item_id in bundle.inventory.items
    assert bundle.pet_capture.bag_item_id in bundle.inventory.items
    for table in bundle.pet_encounter.tables:
        for ent in table["entries"]:
            sid = ent.get("species_id") or ""
            if sid and ent.get("type") in bundle.pet_encounter.capturable_types:
                assert "wild_capture" in bundle.pets.species[sid].acquire_tags


def test_wild_capture_audit_and_not_capture_test(tmp_path: Path) -> None:
    """野外捕获：全因子审计；成功走 wild_capture；缺草 40082。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "pet_wild.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "petwild@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                explore = PetExploreService(session)
                inv = InventoryService(session)

                # 无草无袋 → 可遭遇但捕获拒绝
                enc = await explore.encounter(
                    character,
                    region_id="default",
                    seed=1001,
                )
                # 固定 seed 可能抽到 monster；循环直到可捕
                tries = 0
                while not enc.get("capturable") and tries < 40:
                    tries += 1
                    enc = await explore.encounter(
                        character,
                        region_id="default",
                        seed=1001 + tries,
                    )
                assert enc["capturable"], "未能掷出可捕遭遇"
                assert enc["species_id"]
                assert enc["battle_resolved"] is True

                with pytest.raises(AppError) as exc_bag:
                    await explore.capture(
                        character,
                        encounter_id=str(enc["encounter_id"]),
                        seed=42,
                    )
                assert exc_bag.value.code in (40082, 40083)

                await inv.add_item(
                    character.id,
                    item_type="material",
                    item_id="pet_spirit_bag",
                    quantity=1,
                )
                with pytest.raises(AppError) as exc_lure:
                    await explore.capture(
                        character,
                        encounter_id=str(enc["encounter_id"]),
                        seed=42,
                    )
                assert exc_lure.value.code == 40082

                await inv.add_item(
                    character.id,
                    item_type="material",
                    item_id="pet_lure_grass",
                    quantity=5,
                )

                # 强制高成功率：用极大 seed 扫成功一次，并校验审计字段
                captured = None
                for s in range(0, 80):
                    # 每次失败会扣草；草不足则补
                    lure = (await inv.material_counts(character.id)).get("pet_lure_grass", 0)
                    if lure < 1:
                        await inv.add_item(
                            character.id,
                            item_type="material",
                            item_id="pet_lure_grass",
                            quantity=5,
                        )
                    # 遭遇可能已被成功移除；重新掷
                    if PetExploreSessionStore.get(str(enc["encounter_id"])) is None:
                        enc = await explore.encounter(
                            character,
                            region_id="default",
                            seed=2000 + s,
                        )
                        if not enc.get("capturable"):
                            continue
                    result = await explore.capture(
                        character,
                        encounter_id=str(enc["encounter_id"]),
                        seed=s,
                    )
                    assert "p" in result
                    assert "factors" in result
                    assert "roll" in result
                    assert "seed" in result
                    assert result["acquire_tag"] == "wild_capture"
                    for key in (
                        "p_race",
                        "p_taming_tech",
                        "p_realm_diff",
                        "p_root_affinity",
                        "pen_affix",
                        "pen_grade",
                    ):
                        assert key in result["factors"]
                    if result["success"]:
                        captured = result
                        break
                assert captured is not None, "应能在多次尝试中捕获成功"
                assert captured["pet"] is not None
                assert captured["pet"]["species_id"] == enc["species_id"]
                # 不得冒充 capture_test 路径：持有宠来自 wild_capture 入园
                pets = PetService(session)
                listed = await pets.list_pets(character)
                assert any(p["id"] == captured["id"] for p in listed)

                # 缺草再次捕获
                enc2 = await explore.encounter(character, region_id="default", seed=9)
                # 清草
                counts = await inv.material_counts(character.id)
                left = int(counts.get("pet_lure_grass", 0))
                if left > 0:
                    await inv._remove_item_id(character.id, "pet_lure_grass", left)
                # 找可捕遭遇
                t = 0
                while not enc2.get("capturable") and t < 40:
                    t += 1
                    enc2 = await explore.encounter(character, region_id="default", seed=9 + t)
                if enc2.get("capturable"):
                    with pytest.raises(AppError) as exc2:
                        await explore.capture(
                            character,
                            encounter_id=str(enc2["encounter_id"]),
                            seed=1,
                        )
                    assert exc2.value.code == 40082

    _run(_body())


def test_capture_probability_factors_unit() -> None:
    """全因子公式可审计 clamp。"""
    from app.domain.pet_capture_rules import compute_capture_probability

    p, factors = compute_capture_probability(
        p_race=0.35,
        p_taming_tech=0.0,
        p_realm_diff=0.1,
        p_root_affinity=0.0,
        n_special_affix=2,
        pen_affix=0.05,
        pen_grade=0.03,
    )
    assert abs(p - (0.35 + 0.1 - 0.1 - 0.03)) < 1e-9
    assert factors["pen_affix"] == 0.1
    assert 0.0 <= p <= 1.0
