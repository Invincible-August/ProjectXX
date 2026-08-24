"""M8 R5 / M7-D06: sect workshop true materials + manual blueprint types."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.constants.inventory import ERR_BLUEPRINT_TYPE_MISMATCH, ItemType
from app.core.config import get_settings
from app.core.time_utils import now_utc
from app.db.models import InventoryItem, User
from app.db.models.sect import SectCraftJob, SectMember
from app.domain.sect_blueprint_rules import deposit_forbidden, manual_kind_matches_workshop
from app.domain.sect_org_rules import deposit_type_forbidden
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.gm_service import GmService
from app.services.inventory_service import InventoryService
from app.services.realm_config import clear_game_config_cache, get_game_config
from app.services.sect_facility_service import SectFacilityService
from app.services.sect_service import SectService
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
    monkeypatch.setattr(settings, "sect_system_enabled", True)
    clear_game_config_cache()
    yield
    clear_game_config_cache()


async def _register_char(session, email: str, name: str):
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
    return user


def test_blueprint_type_rules_unit() -> None:
    forbidden = list(
        (get_game_config().sects.treasury or {}).get("forbidden_deposit_types") or [],
    )
    assert deposit_type_forbidden("forge_blueprint", forbidden)
    assert deposit_type_forbidden("manual", forbidden, manual_kind="forge_blueprint")
    assert not deposit_type_forbidden("manual", forbidden, manual_kind="technique")
    assert not deposit_type_forbidden("material", forbidden)
    assert deposit_forbidden(
        item_type="manual",
        forbidden=forbidden,
        manual_kind="alchemy_formula",
    )
    assert manual_kind_matches_workshop("forge_blueprint", "smithing")
    assert not manual_kind_matches_workshop("alchemy_formula", "smithing")
    assert "bp_ore_plate_t1" in get_game_config().inventory.items
    assert get_game_config().inventory.items["bp_ore_plate_t1"].manual_kind == "forge_blueprint"


def test_sect_blueprint_hire_donate_exchange(tmp_path: Path) -> None:
    """真扣材料 / 兑换入包 / 捐赠校验 40209 / 成品入包 / 藏宝阁拒图纸。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "r5bp.db") as factory:
            async with factory() as session:
                user = await _register_char(session, "r5bp@test.com", "图纸甲")
                await GmService(session).gm_set_character(user, spirit_stones=200_000)
                await session.commit()
                await SectService(session).create(
                    user,
                    name="图纸试宗",
                    motto=None,
                    specialty="formation",
                )
                await session.commit()
                member = (await session.execute(select(SectMember))).scalars().first()
                assert member is not None
                member.contribution = 500
                await session.commit()

                fac = SectFacilityService(session)
                inv = InventoryService(session)
                char = await character_service.get_character_by_user_id(session, user.id)
                assert char is not None

                # 藏宝阁：遗留假类型 + manual+kind 均拒
                with pytest.raises(AppError) as exc_legacy:
                    await fac.treasury_deposit(
                        user,
                        page=1,
                        item_type="forge_blueprint",
                        item_id="sword_bp",
                        quantity=1,
                    )
                assert "图纸" in (exc_legacy.value.message or "")
                with pytest.raises(AppError) as exc_manual:
                    await fac.treasury_deposit(
                        user,
                        page=1,
                        item_type=ItemType.MANUAL,
                        item_id="bp_ore_plate_t1",
                        quantity=1,
                    )
                assert "图纸" in (exc_manual.value.message or "")

                # 无材料聘工 → 40055
                with pytest.raises(AppError) as exc_mat:
                    await fac.workshop_hire(
                        user,
                        branch="smithing",
                        craftsman_id="apprentice_smith",
                        recipe_id="ore_plate_t1",
                    )
                assert exc_mat.value.code == 40055

                await inv.add_item(
                    char.id,
                    item_type="material",
                    item_id="ore_iron_raw",
                    quantity=3,
                )
                await session.commit()
                hire = await fac.workshop_hire(
                    user,
                    branch="smithing",
                    craftsman_id="apprentice_smith",
                    recipe_id="ore_plate_t1",
                )
                await session.commit()
                left_ore = (
                    await session.execute(
                        select(InventoryItem).where(
                            InventoryItem.character_id == char.id,
                            InventoryItem.item_id == "ore_iron_raw",
                        ),
                    )
                ).scalars().all()
                assert sum(int(r.quantity) for r in left_ore) == 0

                job = await session.get(SectCraftJob, int(hire["job_id"]))
                assert job is not None
                job.finish_at = now_utc() - timedelta(seconds=1)
                await session.commit()
                claimed = await fac.workshop_claim(user, job_id=int(hire["job_id"]))
                await session.commit()
                assert claimed["outputs"]
                plates = (
                    await session.execute(
                        select(InventoryItem).where(
                            InventoryItem.character_id == char.id,
                            InventoryItem.item_id == "ore_plate_t1",
                        ),
                    )
                ).scalars().all()
                assert sum(int(r.quantity) for r in plates) >= 1

                # 兑换图纸入背包
                member.contribution = 500
                await session.commit()
                exchanged = await fac.workshop_exchange_blueprint(
                    user,
                    branch="alchemy",
                    recipe_id="pill_stamina_minor",
                )
                await session.commit()
                assert exchanged["item_id"] == "bp_pill_stamina_minor"
                bp_rows = (
                    await session.execute(
                        select(InventoryItem).where(
                            InventoryItem.character_id == char.id,
                            InventoryItem.item_type == ItemType.MANUAL,
                            InventoryItem.item_id == "bp_pill_stamina_minor",
                        ),
                    )
                ).scalars().all()
                assert sum(int(r.quantity) for r in bp_rows) == 1

                # 目录已有的图纸不可再缴
                with pytest.raises(AppError) as exc_dup:
                    await fac.workshop_donate_blueprint(
                        user,
                        branch="alchemy",
                        recipe_id="",
                        label_zh="",
                        inventory_item_id=int(bp_rows[0].id),
                    )
                assert "已收录" in (exc_dup.value.message or "")

                # 自定义未收录丹方：错误分支 40209；正确分支成功并耗尽
                await inv.add_item(
                    char.id,
                    item_type=ItemType.MANUAL,
                    item_id="bp_custom_alchemy_r5",
                    quantity=1,
                    meta={
                        "manual_kind": "alchemy_formula",
                        "unlock_recipe_id": "pill_custom_r5",
                        "label_zh": "试炼丹方",
                    },
                )
                await session.commit()
                custom = (
                    await session.execute(
                        select(InventoryItem).where(
                            InventoryItem.character_id == char.id,
                            InventoryItem.item_id == "bp_custom_alchemy_r5",
                        ),
                    )
                ).scalar_one()
                with pytest.raises(AppError) as exc_kind:
                    await fac.workshop_donate_blueprint(
                        user,
                        branch="smithing",
                        recipe_id="",
                        label_zh="",
                        inventory_item_id=int(custom.id),
                    )
                assert exc_kind.value.code == ERR_BLUEPRINT_TYPE_MISMATCH

                donated = await fac.workshop_donate_blueprint(
                    user,
                    branch="alchemy",
                    recipe_id="",
                    label_zh="",
                    inventory_item_id=int(custom.id),
                )
                await session.commit()
                assert donated["recipe_id"] == "pill_custom_r5"
                left_custom = (
                    await session.execute(
                        select(InventoryItem).where(
                            InventoryItem.character_id == char.id,
                            InventoryItem.item_id == "bp_custom_alchemy_r5",
                        ),
                    )
                ).scalars().all()
                assert sum(int(r.quantity) for r in left_custom) == 0

    _run(_body())
