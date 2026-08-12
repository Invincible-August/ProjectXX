"""轮回强化：点数路径倍率、永久加成、携带与商店（纯规则 + 集成）。"""

from __future__ import annotations

import random
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.models import User
from app.db.models.formation_preset import FormationPreset
from app.db.models.inventory_item import InventoryItem
from app.db.models.reincarnation_bonus import CharacterReincarnationBonus
from app.db.models.technique import CharacterTechnique
from app.domain.reincarnation_rules import (
    clamp_break_success_rate,
    compute_reincarnation_bag_slots,
    compute_reincarnation_points,
    compute_settle_permanent_delta,
    compute_slot_cap,
    filter_random_pool,
    roll_shop_offers,
)
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.services import auth_service, character_service
from app.services.realm_config import clear_game_config_cache, get_game_config
from app.services.reincarnation_service import ReincarnationService
from tests.async_db import open_test_session_factory, run_async as _run


@pytest.fixture(autouse=True)
def _cfg(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    clear_game_config_cache()
    yield
    clear_game_config_cache()


def test_points_path_multiplier() -> None:
    """主动入轮回点数高于死亡强制。"""
    cfg = get_game_config().reincarnation.points
    forced = compute_reincarnation_points("jindan", "forced", cfg)
    altar = compute_reincarnation_points("jindan", "altar", cfg)
    self_path = compute_reincarnation_points("jindan", "self", cfg)
    assert forced == 12
    assert altar == int(12 * 1.5)
    assert self_path == altar
    assert altar > forced


def test_permanent_delta_scales_with_realm() -> None:
    """境界越高结算永久加成越高。"""
    cfg = get_game_config().reincarnation.permanent_bonus_on_settle
    low = compute_settle_permanent_delta("body_tempering", cfg)
    high = compute_settle_permanent_delta("huashen", cfg)
    assert high.initial_attr > low.initial_attr
    assert high.break_rate > low.break_rate


def test_slot_cap_and_bag() -> None:
    """槽位与轮回袋容量随次数增长。"""
    slots = get_game_config().reincarnation.slots["constitution"]
    assert compute_slot_cap(reincarnation_count=0, bought=0, slots_kind_cfg=slots) == 1
    assert compute_slot_cap(reincarnation_count=3, bought=0, slots_kind_cfg=slots) == 2
    bags = get_game_config().reincarnation.bags
    assert compute_reincarnation_bag_slots(0, bags) == 4
    assert compute_reincarnation_bag_slots(5, bags) == 9


def test_break_rate_clamp() -> None:
    """突破成功率钳制。"""
    assert clamp_break_success_rate(0.9, 0.2, {"min": 0.05, "max": 0.95}) == 0.95
    assert clamp_break_success_rate(0.1, -0.2, {"min": 0.05, "max": 0.95}) == 0.05


def test_filter_and_roll_pool() -> None:
    """随机池条件过滤与加权抽取。"""
    pool = (get_game_config().reincarnation.shop.get("random") or {}).get("pool") or {}
    early = filter_random_pool(pool, reincarnation_count=0, peak_major="body_tempering")
    assert "rare_extra_constitution_slot" not in early
    late = filter_random_pool(pool, reincarnation_count=3, peak_major="jindan")
    assert "rare_extra_constitution_slot" in late
    rng = random.Random(42)
    offers = roll_shop_offers(late, 3, rng=rng)
    assert 1 <= len(offers) <= 3
    assert len(offers) == len(set(offers))


async def _prepare(session, email: str, name: str) -> User:
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


def test_pre_foundation_idle_free_and_full_ticks() -> None:
    """筑基前灵石消耗为 0，且 cost=0 时按时间片满 tick 结算。"""
    from types import SimpleNamespace

    from app.domain.idle import IdleGainCalculator
    from app.services.realm_config import stones_per_tick_for

    assert stones_per_tick_for(SimpleNamespace(major_realm="body_tempering")) == 0
    assert stones_per_tick_for(SimpleNamespace(major_realm="qi_refining")) == 0
    assert stones_per_tick_for(SimpleNamespace(major_realm="foundation")) == 3

    breakdown = IdleGainCalculator.compute(
        status="normal",
        direction="spirit",
        spirit_stones=0,
        max_ticks=5,
        gain_per_tick=10,
        stone_cost_per_tick=0,
    )
    assert breakdown.used == 5
    assert breakdown.spent_stones == 0
    assert breakdown.stalled is False
    assert breakdown.gained_cultivation == 50


def test_altar_applies_permanent_bonus_and_clears_normal_bag(tmp_path: Path) -> None:
    """祭坛轮回：永久表累加、普通袋清空、轮回袋保留、阵法重置。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "rein_bonus.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "bonus@example.com", "加成者")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.major_realm = "huashen"
                character.peak_major_realm = "huashen"
                character.realm_stage = 1
                character.spirit_stones = 5000
                session.add(
                    InventoryItem(
                        character_id=character.id,
                        item_uid="n1",
                        item_type="material",
                        item_id="ore_iron_raw",
                        quantity=3,
                        bag_kind="normal",
                    ),
                )
                session.add(
                    InventoryItem(
                        character_id=character.id,
                        item_uid="r1",
                        item_type="material",
                        item_id="herb_spirit_grass",
                        quantity=2,
                        bag_kind="reincarnation",
                    ),
                )
                # 不可轮回功法抬级；可轮回保留
                tech = (
                    await session.execute(
                        select(CharacterTechnique).where(
                            CharacterTechnique.character_id == character.id,
                            CharacterTechnique.technique_id == "beginner_alchemy",
                        ),
                    )
                ).scalar_one_or_none()
                if tech:
                    tech.level = 3
                qi = (
                    await session.execute(
                        select(CharacterTechnique).where(
                            CharacterTechnique.character_id == character.id,
                            CharacterTechnique.technique_id == "basic_qi_art",
                        ),
                    )
                ).scalar_one()
                qi.level = 5
                # 前世自定义阵法：轮回后应重置
                session.add(
                    FormationPreset(
                        character_id=character.id,
                        slot=0,
                        name="前世杀阵",
                        role="attack",
                        formation_id="four_symbols",
                        units_json='[{"unit_uid":"main","unit_kind":"main","x":1,"y":1}]',
                    ),
                )
                await session.commit()

                result = await ReincarnationService(session).altar(user)
                await session.commit()
                assert result["path"] == "altar"
                assert result["points_gained"] == int(40 * 1.5)

                presets = (
                    await session.execute(
                        select(FormationPreset).where(
                            FormationPreset.character_id == character.id,
                        ),
                    )
                ).scalars().all()
                assert len(presets) >= 3
                assert all(p.formation_id == "none" for p in presets)
                assert all(p.name in ("进攻", "防守", "临时") for p in presets)

                bonus = (
                    await session.execute(
                        select(CharacterReincarnationBonus).where(
                            CharacterReincarnationBonus.character_id == character.id,
                        ),
                    )
                ).scalar_one()
                assert float(bonus.initial_attr_bonus) > 0
                assert float(bonus.lifetime_applied_growth) == 0.0

                bags = (
                    await session.execute(
                        select(InventoryItem).where(
                            InventoryItem.character_id == character.id,
                        ),
                    )
                ).scalars().all()
                kinds = {row.bag_kind for row in bags}
                assert "normal" not in kinds or all(
                    row.bag_kind != "normal" for row in bags
                )
                assert any(row.bag_kind == "reincarnation" for row in bags)

                qi_after = (
                    await session.execute(
                        select(CharacterTechnique).where(
                            CharacterTechnique.character_id == character.id,
                            CharacterTechnique.technique_id == "basic_qi_art",
                        ),
                    )
                ).scalar_one()
                assert qi_after.level == 5
                alchemy = (
                    await session.execute(
                        select(CharacterTechnique).where(
                            CharacterTechnique.character_id == character.id,
                            CharacterTechnique.technique_id == "beginner_alchemy",
                        ),
                    )
                ).scalar_one()
                assert alchemy.level == 0

                # 商店刷新
                character.reincarnation_points = 50
                character.fate_luck = 20
                await session.commit()
                shop = await ReincarnationService(session).shop_catalog(user)
                assert shop["fixed_items"]
                assert "random_items" in shop
                refreshed = await ReincarnationService(session).shop_refresh(
                    user,
                    currency="fate_luck",
                )
                await session.commit()
                assert refreshed["refreshed"] is True
                assert character.fate_luck == 10

                await ReincarnationService(session).complete_newborn(
                    user,
                    spirit_root_ids=["thunder_root"],
                    legacy_ids=[],
                )
                await session.commit()
                assert character.status == "normal"

    _run(_body())
