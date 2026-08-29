"""
M4 工坊与背包测试（§10.4）：直入包 / 数量 / 取消退冻 / 顺序排队。
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import ensure_aware_utc, now_utc
from app.db.models import User
from app.db.models.craft_job import CraftJob
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.craft_service import CraftService
from app.services.gm_service import GmService
from app.services.inventory_service import InventoryService
from app.services.realm_config import clear_game_config_cache, get_game_config
from app.domain.craft_rules import serialize_craft_levels

from tests.async_db import open_test_session_factory, run_async as _run


def test_serialize_craft_levels_array_from_column() -> None:
    """阵法等级走 array_craft_level；其余默认 0。"""
    rows = serialize_craft_levels(
        growth_attrs={"craft_levels": {"alchemy": 2, "puppet": 1}},
        array_craft_level=4,
    )
    by_branch = {r["branch"]: r for r in rows}
    assert by_branch["alchemy"]["level"] == 2
    assert by_branch["alchemy"]["label_zh"] == "炼丹等级"
    assert by_branch["puppet"]["label_zh"] == "傀儡制作等级"
    assert by_branch["puppet"]["level"] == 1
    assert by_branch["array"]["level"] == 4
    assert by_branch["smithing"]["level"] == 0
    assert by_branch["talisman"]["level"] == 0


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


def test_craft_settle_auto_grants_inventory(tmp_path: Path) -> None:
    """到期 settle 直入包，无需领取。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "craft1.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "craft01@example.com")
                await GmService(session).gm_set_character(
                    user,
                    spirit_stones=5000,
                    set_stamina=200,
                    grant_craft_materials=True,
                )
                await session.commit()
                craft = CraftService(session)
                job = await craft.start(
                    user,
                    recipe_id="pill_stamina_minor",
                    actor="main",
                    quantity=1,
                )
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                row = await session.get(CraftJob, job["id"])
                assert row is not None
                row.finish_at = now_utc() - timedelta(seconds=1)
                await session.commit()
                await craft.settle_jobs_async(character, rng=random.Random(0))
                await session.refresh(row)
                assert row.status == "claimed"
                inv = InventoryService(session)
                counts = await inv.material_counts(character.id)
                assert counts.get("stamina_pill_minor", 0) >= 1

    _run(_body())


def test_claim_compat_after_settle(tmp_path: Path) -> None:
    """claim 兼容：settle 后可返回结果摘要。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "craft_auto.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "craftauto@example.com")
                await GmService(session).gm_set_character(
                    user,
                    spirit_stones=5000,
                    set_stamina=200,
                    grant_craft_materials=True,
                )
                await session.commit()
                craft = CraftService(session)
                job = await craft.start(user, recipe_id="pill_stamina_minor", actor="main")
                row = await session.get(CraftJob, job["id"])
                assert row is not None
                row.finish_at = now_utc() - timedelta(seconds=1)
                row.status = "running"
                await session.commit()
                result = await craft.claim(user, job["id"], rng=random.Random(0))
                assert result["failed"] is False

    _run(_body())


def test_craft_quantity_unit_by_unit(tmp_path: Path) -> None:
    """quantity=3：费用×3；单件窗口≈1×时长；settle 一件后剩 2 并入包。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "craft_qty.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "craftqty@example.com")
                await GmService(session).gm_set_character(
                    user,
                    spirit_stones=5000,
                    set_stamina=200,
                    grant_craft_materials=True,
                )
                await session.commit()
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                inv = InventoryService(session)
                herbs_before = (await inv.material_counts(character.id)).get(
                    "herb_spirit_grass",
                    0,
                )
                stones_before = int(character.spirit_stones)
                recipe = get_game_config().craft_recipes.recipes["pill_stamina_minor"]
                craft = CraftService(session)
                job1 = await craft.start(
                    user,
                    recipe_id="pill_stamina_minor",
                    quantity=1,
                )
                await session.refresh(character)
                job3 = await craft.start(
                    user,
                    recipe_id="pill_stamina_minor",
                    quantity=3,
                )
                await session.refresh(character)
                herbs_after = (await inv.material_counts(character.id)).get(
                    "herb_spirit_grass",
                    0,
                )
                assert herbs_before - herbs_after == int(recipe.materials[0].quantity) * (1 + 3)
                assert stones_before - int(character.spirit_stones) == int(
                    recipe.spirit_stone_cost,
                ) * (1 + 3)
                # 当前件窗口 = 单次时长（非整批）
                t1 = ensure_aware_utc(
                    datetime.fromisoformat(job1["finish_at"].replace("Z", "+00:00")),
                ) - ensure_aware_utc(
                    datetime.fromisoformat(job1["started_at"].replace("Z", "+00:00")),
                )
                t3_unit = ensure_aware_utc(
                    datetime.fromisoformat(job3["finish_at"].replace("Z", "+00:00")),
                ) - ensure_aware_utc(
                    datetime.fromisoformat(job3["started_at"].replace("Z", "+00:00")),
                )
                assert abs(t3_unit.total_seconds() - t1.total_seconds()) < 1.0
                # 整单结束约 3×
                total3 = ensure_aware_utc(
                    datetime.fromisoformat(job3["total_finish_at"].replace("Z", "+00:00")),
                ) - ensure_aware_utc(
                    datetime.fromisoformat(job3["started_at"].replace("Z", "+00:00")),
                )
                assert abs(total3.total_seconds() - t1.total_seconds() * 3) < 1.5

                row = await session.get(CraftJob, job3["id"])
                assert row is not None
                # 推到第一件刚完成
                row.finish_at = now_utc() - timedelta(milliseconds=50)
                await session.commit()
                await craft.settle_jobs_async(character, rng=random.Random(0))
                await session.refresh(row)
                assert row.status == "running"
                assert int(row.quantity) == 2
                counts = await inv.material_counts(character.id)
                assert counts.get("stamina_pill_minor", 0) >= 1

    _run(_body())


def test_craft_queue_chains_finish_times(tmp_path: Path) -> None:
    """连续入队：第二条 started_at ≈ 第一条整单结束。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "craft_chain.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "craftchain@example.com")
                await GmService(session).gm_set_character(
                    user,
                    spirit_stones=5000,
                    set_stamina=200,
                    grant_craft_materials=True,
                )
                await session.commit()
                craft = CraftService(session)
                job_a = await craft.start(user, recipe_id="pill_stamina_minor", quantity=1)
                job_b = await craft.start(user, recipe_id="pill_stamina_minor", quantity=1)
                assert job_b["started_at"] == job_a["total_finish_at"]

    _run(_body())


def test_cancel_waiting_does_not_reset_active(tmp_path: Path) -> None:
    """取消排队项不重置正在制造中的 started_at/finish_at。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "craft_nochurn.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "craftnochurn@example.com")
                await GmService(session).gm_set_character(
                    user,
                    spirit_stones=5000,
                    set_stamina=200,
                    grant_craft_materials=True,
                )
                await session.commit()
                craft = CraftService(session)
                job_a = await craft.start(user, recipe_id="pill_stamina_minor", quantity=1)
                job_b = await craft.start(user, recipe_id="pill_stamina_minor", quantity=1)
                row_a = await session.get(CraftJob, job_a["id"])
                assert row_a is not None
                started_before = ensure_aware_utc(row_a.started_at)
                finish_before = ensure_aware_utc(row_a.finish_at)
                await craft.cancel(user, job_b["id"])
                await session.refresh(row_a)
                assert ensure_aware_utc(row_a.started_at) == started_before
                assert ensure_aware_utc(row_a.finish_at) == finish_before

    _run(_body())


def test_craft_cancel_refunds_and_rechains(tmp_path: Path) -> None:
    """取消退冻资源，并重排后续任务。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "craft_cancel.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "craftcancel@example.com")
                await GmService(session).gm_set_character(
                    user,
                    spirit_stones=5000,
                    set_stamina=200,
                    grant_craft_materials=True,
                )
                await session.commit()
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                craft = CraftService(session)
                job_a = await craft.start(user, recipe_id="pill_stamina_minor", quantity=1)
                job_b = await craft.start(user, recipe_id="pill_stamina_minor", quantity=1)
                await session.refresh(character)
                stones_mid = int(character.spirit_stones)
                herbs_mid = (
                    await InventoryService(session).material_counts(character.id)
                ).get("herb_spirit_grass", 0)
                stamina_mid = int(character.stamina)
                snap = json.loads(
                    (await session.get(CraftJob, job_a["id"])).cost_snapshot_json or "{}",
                )
                await craft.cancel(user, job_a["id"])
                await session.refresh(character)
                assert int(character.spirit_stones) == stones_mid + int(
                    snap.get("spirit_stones") or 0,
                )
                herbs_after = (
                    await InventoryService(session).material_counts(character.id)
                ).get("herb_spirit_grass", 0)
                assert herbs_after == herbs_mid + int(
                    (snap.get("materials") or [{}])[0].get("quantity") or 0,
                )
                assert int(character.stamina) == stamina_mid + int(snap.get("stamina") or 0)
                row_b = await session.get(CraftJob, job_b["id"])
                assert row_b is not None
                assert row_b.status == "running"
                # 取消 A 后 B 应提前到 now 附近开工
                assert ensure_aware_utc(row_b.started_at) <= now_utc() + timedelta(seconds=2)

    _run(_body())


def test_crafting_direction_faster_finish() -> None:
    """本体 crafting 挂机方向 → 效率加成，完成耗时更短（纯函数）。"""
    from app.domain.craft_rules import compute_efficiency, compute_finish_at
    from datetime import datetime, timezone

    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bonus = float(get_game_config().craft_recipes.main_crafting_bonus)
    eff_craft = compute_efficiency(
        actor="main",
        character_idle_direction="crafting",
        avatar_idle_direction=None,
        main_crafting_bonus=bonus,
    )
    eff_spirit = compute_efficiency(
        actor="main",
        character_idle_direction="spirit",
        avatar_idle_direction=None,
        main_crafting_bonus=bonus,
    )
    assert eff_craft == bonus
    assert eff_spirit == 1.0
    finish_fast = compute_finish_at(started, 60, eff_craft)
    finish_slow = compute_finish_at(started, 60, eff_spirit)
    assert finish_fast < finish_slow


def test_remove_materials_shortage_uses_zh_name(tmp_path: Path) -> None:
    """材料不足提示用中文名和缺少数量，不甩 item_id。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "craft_mat.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "craftmat@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                inv = InventoryService(session)
                with pytest.raises(AppError) as exc:
                    await inv.remove_materials(
                        character.id,
                        [{"item_id": "herb_spirit_grass", "quantity": 2}],
                    )
                assert exc.value.code == 40055
                assert "herb_spirit_grass" not in exc.value.message
                assert exc.value.message == "材料不足：灵草 缺少 2"
                await inv.add_item(
                    character.id,
                    item_type="material",
                    item_id="herb_spirit_grass",
                    quantity=1,
                )
                with pytest.raises(AppError) as exc2:
                    await inv.remove_materials(
                        character.id,
                        [{"item_id": "herb_spirit_grass", "quantity": 2}],
                    )
                assert exc2.value.message == "材料不足：灵草 缺少 1"

    _run(_body())
