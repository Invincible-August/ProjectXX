"""M7：NPC 坊市固定货架购买 / 出售换灵石。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.currency_ledger_service import reset_system_recycle_balance_for_tests
from app.services.inventory_service import InventoryService
from app.services.realm_config import clear_game_config_cache
from app.services.trade_service import TradeService
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
    monkeypatch.setattr(settings, "trade_system_enabled", True)
    clear_game_config_cache()
    reset_system_recycle_balance_for_tests()
    yield
    clear_game_config_cache()
    reset_system_recycle_balance_for_tests()


async def _register(session, email: str, name: str):
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


def test_bazaar_buy_and_sell(tmp_path: Path) -> None:
    """固定货架可买；持有后可按收购价卖回。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "bazaar.db") as factory:
            async with factory() as session:
                user = await _register(session, "bz@example.com", "坊市客")
                svc = TradeService(session)
                catalog = await svc.list_bazaar(user)
                assert catalog["items"], "货架不可为空"
                target = next(
                    (x for x in catalog["items"] if x["item_id"] == "herb_spirit_grass"),
                    catalog["items"][0],
                )
                item_id = str(target["item_id"])
                buy_price = int(target["buy_price"])
                sell_price = int(target["sell_price"])
                assert buy_price > 0 and sell_price > 0

                from app.db.models.character import Character

                ch = (
                    await session.execute(select(Character).where(Character.user_id == user.id))
                ).scalar_one()
                before = int(ch.spirit_stones)

                bought = await svc.bazaar_buy(user, item_id=item_id, quantity=2)
                await session.commit()
                assert bought["spirit_stones_spent"] == buy_price * 2
                assert int(bought["spirit_stones"]) == before - buy_price * 2

                inv = InventoryService(session)
                bags = await inv.list_bags(ch)
                owned = sum(
                    int(r["quantity"])
                    for r in bags["normal_items"]
                    if r["item_id"] == item_id
                )
                assert owned >= 2

                sold = await svc.bazaar_sell(user, item_id=item_id, quantity=1)
                await session.commit()
                assert sold["spirit_stones_gained"] == sell_price
                assert int(sold["spirit_stones"]) == before - buy_price * 2 + sell_price

    _run(_body())


def test_bazaar_rejects_bound(tmp_path: Path) -> None:
    """绑定物不可卖给坊市（即使误配货架）。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "bazaar_bound.db") as factory:
            async with factory() as session:
                user = await _register(session, "bd@example.com", "绑定客")
                from app.db.models.character import Character

                ch = (
                    await session.execute(select(Character).where(Character.user_id == user.id))
                ).scalar_one()
                inv = InventoryService(session)
                await inv.add_item(
                    ch.id,
                    item_type="consumable",
                    item_id="bound_spirit_token",
                    quantity=3,
                )
                await session.commit()

                # 临时把绑定物挂到货架（仅本用例内存配置）
                from app.services import realm_config as rc

                cfg = rc.get_game_config()
                bazaar = dict(cfg.trade.bazaar or {})
                items = dict(bazaar.get("items") or {})
                items["bound_spirit_token"] = {
                    "label_zh": "绑定灵符",
                    "buy_price": 10,
                    "sell_price": 5,
                }
                bazaar["items"] = items
                object.__setattr__(cfg.trade, "bazaar", bazaar)

                svc = TradeService(session)
                with pytest.raises(AppError) as ei:
                    await svc.bazaar_sell(user, item_id="bound_spirit_token", quantity=1)
                assert "绑定" in str(ei.value.message)

    _run(_body())
