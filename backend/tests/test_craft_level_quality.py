"""制作等级门槛与品质掷骰。"""

from __future__ import annotations

import random
from pathlib import Path

import pytest
from sqlalchemy import select

from app.constants.craft import ERR_CRAFT_LEVEL
from app.db.models import User
from app.domain.craft_quality import resolve_quality_weights, roll_craft_quality
from app.domain.reincarnation_rules import parse_growth_attrs
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.craft_service import CraftService
from app.services.gm_service import GmService
from app.services.realm_config import clear_game_config_cache, get_game_config

from tests.async_db import open_test_session_factory, run_async as _run


@pytest.fixture(autouse=True)
def _reload() -> None:
    clear_game_config_cache()
    yield
    clear_game_config_cache()


def test_quality_weights_jump_with_level_delta() -> None:
    bands = get_game_config().craft_recipes.quality_by_level_delta
    low = resolve_quality_weights(0, bands)
    high = resolve_quality_weights(5, bands)
    assert low["white"] > high["white"]
    assert high.get("orange", 0) + high.get("red", 0) > low.get("orange", 0) + low.get(
        "red",
        0,
    )
    rng = random.Random(1)
    assert roll_craft_quality(5, bands, rng=rng) in {
        "gray",
        "white",
        "green",
        "blue",
        "purple",
        "orange",
        "red",
    }


def test_normalize_legacy_craft_quality() -> None:
    from app.domain.craft_quality import normalize_craft_quality

    assert normalize_craft_quality("common") == "white"
    assert normalize_craft_quality("fine") == "green"
    assert normalize_craft_quality("rare") == "blue"
    assert normalize_craft_quality("superb") == "purple"
    assert normalize_craft_quality("凡品") == "white"
    assert normalize_craft_quality("极品") == "purple"
    assert normalize_craft_quality("orange") == "orange"
    assert normalize_craft_quality("") == "white"


def test_craft_equip_slot_group_maps_catalog_kinds() -> None:
    """Workshop slot filter groups weapons/armor pieces, not 17-zone pointers."""
    from app.constants.craft import craft_equip_slot_group

    assert craft_equip_slot_group("weapon_1h") == "weapon"
    assert craft_equip_slot_group("weapon_2h") == "weapon"
    assert craft_equip_slot_group("armor_head") == "head"
    assert craft_equip_slot_group("armor_hands") == "hands"
    assert craft_equip_slot_group("armor_legs") == "legs"
    assert craft_equip_slot_group("accessory") == "accessory"
    assert craft_equip_slot_group("fabao_1") == "fabao"
    assert craft_equip_slot_group("ore_plate") is None


async def _user(session, email: str) -> User:
    await auth_service.register_user(
        session,
        RegisterRequest(password="password123", email=email),
    )
    await session.commit()
    user = (await session.execute(select(User).where(User.email == email))).scalar_one()
    await character_service.create_character(
        session,
        user,
        CreateCharacterRequest(name=email.split("@")[0][:16]),
    )
    await session.commit()
    return user


def test_recipe_locked_until_craft_level(tmp_path: Path) -> None:
    """二级矿板要求炼器等级 2。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "clv.db") as factory:
            async with factory() as session:
                user = await _user(session, "clv@example.com")
                await GmService(session).gm_set_character(
                    user, spirit_stones=5000, set_stamina=200, grant_craft_materials=True,
                )
                await session.commit()
                craft = CraftService(session)
                char = await character_service.get_character_by_user_id(session, user.id)
                assert char is not None
                recipes = {r["recipe_id"]: r for r in craft.list_recipes(char)}
                assert "array_drill_1" not in recipes
                assert all(r["branch"] != "array" for r in recipes.values())
                assert recipes["ore_plate_t2"]["locked"] is True
                assert recipes["ore_plate_t2"]["materials"][0]["label_zh"] == "粗铁矿"
                assert "smithing" not in (recipes["ore_plate_t2"]["lock_reason"] or "")
                pill = recipes["pill_stamina_minor"]
                assert pill["materials"][0]["label_zh"] == "灵草"
                assert "恢复体力" in (pill["effect_zh"] or "")
                inspect = pill["inspect"]
                assert inspect["craft_level_label_zh"] == "炼丹等级"
                assert inspect["required_craft_level"] == 0
                assert inspect["element"]["id"] == "wood"
                assert inspect["element"]["label_zh"] == "木"
                assert "resists" not in inspect
                assert any(tag["label_zh"] == "恢复体力" for tag in inspect["effects"])
                assert inspect["realm_req_zh"] == "无"
                assert inspect["help_zh"]
                assert recipes["talisman_atk_t1"]["talisman_kind"] == "offensive"
                alchemy = [r for r in recipes.values() if r["branch"] == "alchemy"]
                assert len(alchemy) >= 8
                alchemy_element_ids = {
                    ((r.get("inspect") or {}).get("element") or {}).get("id")
                    for r in alchemy
                }
                assert alchemy_element_ids == {
                    "metal",
                    "wood",
                    "water",
                    "fire",
                    "earth",
                    "wind",
                    "thunder",
                    "dark",
                }
                alchemy_levels = {int(r["required_craft_level"]) for r in alchemy}
                assert 0 in alchemy_levels and 3 in alchemy_levels
                assert recipes["pill_fire_minor"]["locked"] is True
                smith = recipes["ore_plate_t1"]
                assert smith["inspect"]["craft_level_label_zh"] == "炼器等级"
                assert smith["inspect"]["element"]["id"] == "metal"
                assert smith["equip_slot_group"] is None
                assert recipes["iron_sword_t1"]["equip_slot_group"] == "weapon"
                assert recipes["iron_sword_t1"]["equip_slot_group_zh"] == "武器"
                assert recipes["cloth_cap_t1"]["equip_slot_group"] == "head"
                assert recipes["iron_gloves_t1"]["equip_slot_group"] == "hands"
                assert recipes["iron_greaves_t1"]["equip_slot_group"] == "legs"
                smithing_groups = {
                    r["equip_slot_group"]
                    for r in recipes.values()
                    if r["branch"] == "smithing" and r.get("equip_slot_group")
                }
                assert {
                    "weapon",
                    "head",
                    "chest",
                    "hands",
                    "legs",
                    "shoes",
                    "accessory",
                    "fabao",
                }.issubset(smithing_groups)
                talisman_kinds = {
                    r["talisman_kind"]
                    for r in recipes.values()
                    if r["branch"] == "talisman"
                }
                assert talisman_kinds == {"buff", "offensive", "curse"}
                assert recipes["talisman_ward_t1"]["talisman_kind_zh"] == "增益"
                assert recipes["talisman_atk_t1"]["talisman_kind_zh"] == "攻击"
                assert recipes["talisman_curse_t1"]["talisman_kind_zh"] == "诅咒"
                assert recipes["talisman_curse_t1"]["locked"] is True
                assert pill["recipe_tier"] == 1
                with pytest.raises(AppError) as exc:
                    await craft.start(user, recipe_id="ore_plate_t2", actor="main")
                assert exc.value.code == ERR_CRAFT_LEVEL
                import json

                growth = parse_growth_attrs(char.growth_attrs_json)
                growth["craft_levels"] = {"smithing": 2}
                char.growth_attrs_json = json.dumps(growth, ensure_ascii=False)
                await session.commit()
                recipes2 = {r["recipe_id"]: r for r in craft.list_recipes(char)}
                assert recipes2["ore_plate_t2"]["locked"] is False
                job = await craft.start(user, recipe_id="ore_plate_t2", actor="main")
                assert job["recipe_id"] == "ore_plate_t2"

    _run(_body())
