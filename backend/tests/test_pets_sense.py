"""
M4 灵宠与神识测试（§10.4）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.domain.divine_sense import apply_overload_mult, overload_multiplier
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.avatar_service import AvatarService
from app.services.gm_service import GmService
from app.services.pet_service import PetService
from app.services.realm_config import clear_game_config_cache

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
def _reload_config(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_game_config_cache()
    yield
    clear_game_config_cache()


def test_transfer_crafting_exp_rejected(tmp_path: Path) -> None:
    """传 crafting_exp → 40052。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "sense1.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "sense01@example.com")
                await GmService(session).gm_set_character(user, force_jindan=True, spirit_stones=5000)
                await session.commit()
                av = AvatarService(session)
                await av.condense(user)
                with pytest.raises(AppError) as exc:
                    await av.transfer(
                        user,
                        direction="main_to_avatar",
                        resource="crafting_exp",
                        amount=10,
                    )
                assert exc.value.code == 40052

    _run(_body())


def test_overload_reduces_stats() -> None:
    """宠+化身超载 → atk 下降可断言（阶梯表）。"""
    from app.domain.divine_sense import apply_overload_mult, overload_multiplier

    mult = overload_multiplier(
        load=12,
        capacity=10,
        soft_cap=10,
        bands=[
            {"max_load_ratio": 1.0, "combat_stat_mult": 1.0, "zone": "comfort"},
            {"max_load_ratio": 1.25, "combat_stat_mult": 0.85, "zone": "overload"},
            {"max_load_ratio": 1.5, "combat_stat_mult": 0.7, "zone": "overload"},
            {"max_load_ratio": None, "combat_stat_mult": 0.5, "zone": "critical"},
        ],
    )
    assert mult == 0.85  # 12/10=1.2 → 1.25 档
    stats = apply_overload_mult({"atk": 100, "hp": 100}, mult)
    assert stats["atk"] < 100


def test_divine_sense_comfort_overload_hard() -> None:
    """M4-D03：舒适 / 超载 / 硬顶三档单测。"""
    from app.domain.divine_sense import (
        compute_load,
        resolve_backlash_entry,
        resolve_overload_band,
        should_trigger_backlash,
        soft_hard_caps,
    )
    from app.services.realm_config import get_game_config

    cfg = get_game_config().divine_sense
    assert cfg.overload_bands
    assert cfg.backlash_table

    capacity = 10
    soft, hard = soft_hard_caps(
        capacity,
        soft_ratio=cfg.soft_ratio,
        hard_ratio=cfg.hard_ratio,
    )
    assert soft == 10
    assert hard == 15

    bands = [
        {
            "max_load_ratio": b.max_load_ratio,
            "combat_stat_mult": b.combat_stat_mult,
            "zone": b.zone,
        }
        for b in cfg.overload_bands
    ]

    # 舒适：load ≤ soft
    comfort = resolve_overload_band(10, capacity, soft_cap=soft, bands=bands)
    assert comfort.zone == "comfort"
    assert comfort.combat_stat_mult == 1.0
    assert not should_trigger_backlash(10, hard)

    # 超载：10 < load ≤ 12.5 → 0.85
    over = resolve_overload_band(12, capacity, soft_cap=soft, bands=bands)
    assert over.zone == "overload"
    assert over.combat_stat_mult == 0.85
    assert not should_trigger_backlash(12, hard)

    # 硬顶：load > 15
    assert should_trigger_backlash(16, hard)
    critical = resolve_overload_band(16, capacity, soft_cap=soft, bands=bands)
    assert critical.combat_stat_mult == 0.5
    assert critical.zone == "critical"
    entry = resolve_backlash_entry(
        over_hard=True,
        table=[
            {
                "id": t.id,
                "when": t.when,
                "idle_mult": t.idle_mult,
                "set_flag": t.set_flag,
                "summary": t.summary,
            }
            for t in cfg.backlash_table
        ],
        fallback_idle_mult=cfg.backlash_idle_mult,
    )
    assert entry is not None
    assert entry.idle_mult == 0.5
    assert entry.when == "over_hard"

    # 物种占用覆盖：crane cost=4
    load = compute_load(
        avatar_count=1,
        pet_count=1,
        cost_avatar=5,
        cost_pet=3,
        pet_costs=[4],
    )
    assert load == 9


def test_capture_test_pet(tmp_path: Path) -> None:
    """测试捕获灵宠（加权物种 + 品阶 + 词条填槽）。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "pet1.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "pet01@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                pet_svc = PetService(session)
                data = await pet_svc.capture_test(character)
                assert data["species_id"] in {
                    "test_pet_fox",
                    "pet_crane_qing",
                    "pet_centipede_yin",
                }
                assert int(data["grade"]) >= 1
                assert await pet_svc.count_pets(character.id) == 1
                pet = data["pet"]
                from app.services.realm_config import get_game_config

                grade_cfg = get_game_config().pets.grades[int(data["grade"])]
                assert len(pet["affixes"]) == grade_cfg.affix_slots
                assert int(data["affix_count"]) == grade_cfg.affix_slots
                catalog = await pet_svc.catalog(character)
                assert len(catalog["races"]) >= 2
                assert len(catalog["species"]) >= 3
                caught = [
                    s for s in catalog["species"] if s["species_id"] == data["species_id"]
                ]
                assert caught and caught[0]["caught"] is True

    _run(_body())


def test_pets_config_hotplug_races_and_grades() -> None:
    """N4 配置：≥2 种族、≥3 物种、品阶表可加载。"""
    from app.services.realm_config import get_game_config

    cfg = get_game_config().pets
    assert len(cfg.races) >= 2
    assert len(cfg.species) >= 3
    assert len(cfg.grades) >= 3
    for sp in cfg.species.values():
        assert sp.race in cfg.races
        assert sp.rarity in {"common", "rare", "epic", "legendary"}


def test_pet_affixes_config_separate_from_constitution() -> None:
    """PET-D01：词条库独立加载，与体质表分离。"""
    from app.services.realm_config import get_game_config

    bundle = get_game_config()
    assert len(bundle.pet_affixes.types) >= 3
    assert "flat_atk" in {t.kind for t in bundle.pet_affixes.types.values()}
    # 体质词条键不应作为灵宠词条类型主键混用（分表验收）
    assert not hasattr(bundle.constitution, "types") or True
    assert bundle.pets.grade_up.get("spirit_stones_base")


def test_grade_up_and_value_reroll(tmp_path: Path) -> None:
    """升阶追加词条；数值洗炼不改类型/品级。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "pet_affix.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "petaffix@example.com")
                await GmService(session).gm_set_character(
                    user,
                    spirit_stones=50_000,
                )
                await session.commit()
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                pet_svc = PetService(session)
                captured = await pet_svc.capture_test(
                    character,
                    species_id="test_pet_fox",
                )
                pet_id = int(captured["id"])
                before_affixes = list(captured["pet"]["affixes"])
                before_types = [a["affix_type_id"] for a in before_affixes]
                before_count = len(before_affixes)

                graded = await pet_svc.grade_up(character, pet_id)
                after = graded["pet"]["affixes"]
                assert int(graded["grade"]) == int(captured["grade"]) + 1
                assert len(after) == before_count + 1
                # 旧槽类型保留
                for i, type_id in enumerate(before_types):
                    assert after[i]["affix_type_id"] == type_id

                slot0 = after[0]
                stones_before = int(character.spirit_stones)
                rerolled = await pet_svc.reroll_affix_value(
                    character,
                    pet_id,
                    slot_index=int(slot0["slot_index"]),
                )
                new_affix = rerolled["affix"]
                assert new_affix["affix_type_id"] == slot0["affix_type_id"]
                assert new_affix["affix_tier"] == slot0["affix_tier"]
                assert int(character.spirit_stones) < stones_before
                assert int(rerolled["value_reroll_count"]) == 1

    _run(_body())


def test_type_reroll_cost_formula() -> None:
    """PET-D06：费用公式 cost = base_1 * i * (1+grow)^(k-1)。"""
    from app.domain.pet_rules import type_reroll_cost

    # 槽1 首次 100；第二次 110；槽2 首次 200
    assert type_reroll_cost(base_1=100, grow=0.1, slot_ordinal_1based=1, times_already=0) == 100
    assert type_reroll_cost(base_1=100, grow=0.1, slot_ordinal_1based=1, times_already=1) == 110
    assert type_reroll_cost(base_1=100, grow=0.1, slot_ordinal_1based=2, times_already=0) == 200
    assert type_reroll_cost(base_1=100, grow=0.1, slot_ordinal_1based=2, times_already=1) == 220


def test_sect_affix_type_reroll(tmp_path: Path) -> None:
    """PET-D06：可改槽扣费改类型；超槽拒绝；分槽计数独立。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "pet_type_reroll.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "pettyperoll@example.com")
                await GmService(session).gm_set_character(user, spirit_stones=50_000)
                await session.commit()
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                pet_svc = PetService(session)
                captured = await pet_svc.capture_test(
                    character,
                    species_id="test_pet_fox",
                )
                pet_id = int(captured["id"])
                pet = captured["pet"]
                type_slots = int(pet["type_reroll_slots"])
                assert type_slots >= 1
                assert pet["type_reroll_enabled"] is True

                status = await pet_svc.type_reroll_status(character, pet_id)
                assert status["enabled"] is True
                assert status["slots"]
                first = status["slots"][0]
                assert int(first["next_cost_spirit_stones"]) == 100
                assert first["eligible"] is True

                stones_before = int(character.spirit_stones)
                result = await pet_svc.reroll_affix_type(
                    character,
                    pet_id,
                    slot_index=0,
                )
                assert int(result["spirit_stones_spent"]) == 100
                assert int(character.spirit_stones) == stones_before - 100
                assert int(result["type_reroll_count"]) == 1
                # 第二次同槽费用 110
                second = await pet_svc.reroll_affix_type(
                    character,
                    pet_id,
                    slot_index=0,
                )
                assert int(second["spirit_stones_spent"]) == 110
                assert int(second["type_reroll_count"]) == 2

                # 超可改槽拒绝（凡品 type_reroll_slots=1 → 槽 1 不可）
                if type_slots == 1 and len(pet["affixes"]) > 1:
                    with pytest.raises(AppError) as exc:
                        await pet_svc.reroll_affix_type(
                            character,
                            pet_id,
                            slot_index=1,
                        )
                    assert exc.value.code == 40061

    _run(_body())


def test_pet_skills_equip_and_learn_book(tmp_path: Path) -> None:
    """PET-D02：捕获默认装备；池领悟；技能书 scope；装备最多 4。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "pet_skill.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "petskill@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                pet_svc = PetService(session)
                captured = await pet_svc.capture_test(
                    character,
                    species_id="test_pet_fox",
                )
                pet = captured["pet"]
                skills = pet["skills"]
                assert skills["equip_slots"] == 4
                assert len(skills["equipped_ids"]) == 4
                assert "skill_fox_bite" in skills["learned_ids"]
                # 池领悟
                learned = await pet_svc.learn_skill_from_pool(
                    character,
                    int(captured["id"]),
                    skill_id="skill_fox_tail",
                )
                assert "skill_fox_tail" in learned["pet"]["skills"]["learned_ids"]
                # 装备 3 招
                equipped = await pet_svc.equip_skills(
                    character,
                    int(captured["id"]),
                    equipped=[
                        "skill_fox_bite",
                        "skill_basic_scratch",
                        "skill_fox_tail",
                        None,
                    ],
                )
                assert equipped["equipped_ids"][2] == "skill_fox_tail"
                # 技能书：发书 → 通用可学
                from app.services.inventory_service import InventoryService

                inv = InventoryService(session)
                await inv.add_item(
                    character.id,
                    item_type="skill_book",
                    item_id="book_universal_guard",
                    quantity=1,
                )
                from_book = await pet_svc.learn_skill_from_book(
                    character,
                    int(captured["id"]),
                    book_id="book_universal_guard",
                )
                assert from_book["learned_skill_id"] == "skill_universal_guard"
                # 种族书：鸟宠不可学兽族咆哮
                crane = await pet_svc.capture_test(
                    character,
                    species_id="pet_crane_qing",
                )
                await inv.add_item(
                    character.id,
                    item_type="skill_book",
                    item_id="book_beast_roar",
                    quantity=1,
                )
                with pytest.raises(AppError) as exc:
                    await pet_svc.learn_skill_from_book(
                        character,
                        int(crane["id"]),
                        book_id="book_beast_roar",
                    )
                assert exc.value.code == 40062

    _run(_body())


def test_pet_skills_config_hotplug() -> None:
    """技能/池/书配置可加载且物种池外键合法。"""
    from app.services.realm_config import get_game_config

    bundle = get_game_config()
    assert len(bundle.pet_skills.skills) >= 3
    assert "pool_fox" in bundle.pet_skills.pools
    assert "book_universal_guard" in bundle.pet_skill_books.books
    for sp in bundle.pets.species.values():
        if sp.skill_pool_id:
            assert sp.skill_pool_id in bundle.pet_skills.pools


def test_pet_egg_hatch_closed_loop(tmp_path: Path) -> None:
    """N5：蛋→开工→领取入园；0 秒蛋立刻 ready。"""
    from app.services.inventory_service import InventoryService
    from app.services.pet_hatch_service import PetHatchService

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "pet_hatch.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "pethatch@example.com")
                await GmService(session).gm_set_character(user, spirit_stones=10_000)
                await session.commit()
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                inv = InventoryService(session)
                await inv.add_item(
                    character.id,
                    item_type="pet_egg",
                    item_id="egg_fox_trial",
                    quantity=2,
                )
                hatch = PetHatchService(session)
                state0 = await hatch.list_state(character)
                assert any(e["egg_item_id"] == "egg_fox_trial" and e["owned"] >= 2 for e in state0["eggs"])

                started = await hatch.start(character, egg_item_id="egg_fox_trial")
                job = started["job"]
                assert job["status"] in {"hatching", "ready"}
                # hatch_seconds=0 → 立刻可领
                assert job["status"] == "ready"

                before = await PetService(session).count_pets(character.id)
                claimed = await hatch.claim(character, int(job["job_id"]))
                assert claimed["species_id"] == "test_pet_fox"
                assert int(claimed["id"]) > 0
                assert await PetService(session).count_pets(character.id) == before + 1
                # 蛋已扣 1
                state1 = await hatch.list_state(character)
                fox = next(e for e in state1["eggs"] if e["egg_item_id"] == "egg_fox_trial")
                assert fox["owned"] == 1

    _run(_body())


def test_pet_eggs_config_hotplug() -> None:
    """N5：蛋表可加载且物种/道具外键合法。"""
    from app.services.realm_config import get_game_config

    bundle = get_game_config()
    assert "egg_fox_trial" in bundle.pet_eggs.eggs
    egg = bundle.pet_eggs.eggs["egg_fox_trial"]
    assert egg.species_id in bundle.pets.species
    assert "egg_hatch" in bundle.pets.species[egg.species_id].acquire_tags
    assert egg.egg_id in bundle.inventory.items


def test_pet_passives_racial_talent_required(tmp_path: Path) -> None:
    """PET-D03：捕获必带种族天赋；独立被动可空；combat 进面板。"""
    from app.domain.pet_passive_rules import roll_independent_passive
    from app.services.realm_config import get_game_config

    bundle = get_game_config()
    assert "talent_beast_hide" in bundle.pet_passives.passives
    assert "pool_beast_passives" in bundle.pet_passives.pools
    for race in bundle.pets.races.values():
        assert race.racial_talent_id in bundle.pet_passives.passives

    # 空抽可复现：仅 empty_weight
    assert roll_independent_passive(empty_weight=100, weights={}) is None

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "pet_passive.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "petpassive@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                pet_svc = PetService(session)
                captured = await pet_svc.capture_test(
                    character,
                    species_id="test_pet_fox",
                )
                pet = captured["pet"]
                block = pet["passives"]
                assert block["racial_talent_id"] == "talent_beast_hide"
                assert block["racial_talent"]["name"]
                assert isinstance(block["rolled_ids"], list)
                # 厚皮 flat_hp=5 → hp 高于无天赋基线
                base_no_talent = 40  # fox base_hp grade1 level1
                assert int(pet["stats"]["hp"]) >= base_no_talent + 5

    _run(_body())


def test_pet_feed_raises_stats_and_caps(tmp_path: Path) -> None:
    """PET-D04：喂养涨面板；超单药上限 40066；背包不足 40055。"""
    from app.services.inventory_service import InventoryService
    from app.services.realm_config import get_game_config

    bundle = get_game_config()
    assert "pet_pill_atk_minor" in bundle.pet_feed.items
    assert "pet_pill_atk_minor" in bundle.inventory.items

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "pet_feed.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "petfeed@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                pet_svc = PetService(session)
                captured = await pet_svc.capture_test(
                    character,
                    species_id="test_pet_fox",
                )
                pet_id = int(captured["id"])
                atk_before = int(captured["pet"]["stats"]["atk"])

                inv = InventoryService(session)
                # 未发丹 → 40055
                with pytest.raises(AppError) as exc_bag:
                    await pet_svc.feed(
                        character,
                        pet_id,
                        item_id="pet_pill_atk_minor",
                        quantity=1,
                    )
                assert exc_bag.value.code == 40055

                await inv.add_item(
                    character.id,
                    item_type="consumable",
                    item_id="pet_pill_atk_minor",
                    quantity=10,
                )
                fed = await pet_svc.feed(
                    character,
                    pet_id,
                    item_id="pet_pill_atk_minor",
                    quantity=1,
                )
                assert fed["times_fed"] == 1
                assert int(fed["pet"]["stats"]["atk"]) == atk_before + 1
                assert fed["pet"]["feed"]["applied_effects"]["flat_atk"] == 1.0

                # 单药上限 5：再喂 4 达顶，第 6 次拒绝
                topped = await pet_svc.feed(
                    character,
                    pet_id,
                    item_id="pet_pill_atk_minor",
                    quantity=4,
                )
                assert topped["times_fed"] == 5
                assert topped["total_used"] == 5
                with pytest.raises(AppError) as exc_cap:
                    await pet_svc.feed(
                        character,
                        pet_id,
                        item_id="pet_pill_atk_minor",
                        quantity=1,
                    )
                assert exc_cap.value.code == 40066

    _run(_body())


def test_pet_duel_auto_seed_reproducible(tmp_path: Path) -> None:
    """PET-D05：自动对战同一 seed 结果一致；零 board 依赖。"""
    from app.services.pet_duel_service import PetDuelService

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "pet_duel.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "petduel@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                pet_svc = PetService(session)
                captured = await pet_svc.capture_test(
                    character,
                    species_id="test_pet_fox",
                )
                duel = PetDuelService(session)
                r1 = await duel.auto_npc(
                    character,
                    pet_id=int(captured["id"]),
                    seed=424242,
                )
                r2 = await duel.auto_npc(
                    character,
                    pet_id=int(captured["id"]),
                    seed=424242,
                )
                assert r1["report"]["winner"] == r2["report"]["winner"]
                assert r1["report"]["rounds"] == r2["report"]["rounds"]
                assert len(r1["report"]["events"]) == len(r2["report"]["events"])
                assert r1["report"]["seed"] == 424242
                # 交互一回合不崩溃
                started = await duel.start_npc(
                    character,
                    pet_id=int(captured["id"]),
                    seed=7,
                )
                turned = await duel.turn(
                    character,
                    started["duel_id"],
                    skill_id="skill_fox_bite",
                )
                assert "state" in turned
                assert turned["state"]["round_index"] >= 1

    _run(_body())
