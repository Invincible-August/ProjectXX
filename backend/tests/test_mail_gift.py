"""M7 L3：邮件领取幂等 + 赠送日限 + 拍卖流拍退邮件。"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.time_utils import now_utc
from app.db.models import User
from app.db.models.mail import MailMessage
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.currency_ledger_service import reset_system_recycle_balance_for_tests
from app.services.friend_service import FriendService
from app.services.gm_service import GmService
from app.services.inventory_service import InventoryService
from app.services.mail_service import MailService
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
    monkeypatch.setattr(settings, "friends_system_enabled", True)
    monkeypatch.setattr(settings, "trade_system_enabled", True)
    monkeypatch.setattr(settings, "mail_system_enabled", True)
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


def test_mail_claim_idempotent(tmp_path: Path) -> None:
    """系统信领取成功；二次领取 40120。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "mail_claim.db") as factory:
            async with factory() as session:
                user = await _register(session, "mc@example.com", "信甲")
                ch = await character_service.get_character_by_user_id(session, user.id)
                await GmService(session).gm_set_character(user, spirit_stones=100)
                await session.commit()
                mail = MailService(session)
                row = await mail.send_system(
                    to_character_id=ch.id,
                    subject_zh="测试附件",
                    body_zh="请领取",
                    reason="test",
                    spirit_stones=50,
                    items=[{"item_id": "herb_spirit_grass", "quantity": 2}],
                )
                await session.commit()
                claimed = await mail.claim(user, row.id)
                await session.commit()
                assert claimed["claimed"]["spirit_stones"] == 50
                await session.refresh(ch)
                assert int(ch.spirit_stones) == 150
                counts = await InventoryService(session).material_counts(ch.id)
                assert counts.get("herb_spirit_grass", 0) == 2
                with pytest.raises(AppError) as exc:
                    await mail.claim(user, row.id)
                assert exc.value.code == 40120

    _run(_body())


def test_gift_requires_friend_and_daily_cap(tmp_path: Path) -> None:
    """非道友拒绝；结友后可赠；日次数上限。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "gift.db") as factory:
            async with factory() as session:
                a = await _register(session, "ga@example.com", "赠甲")
                b = await _register(session, "gb@example.com", "赠乙")
                await GmService(session).gm_set_character(a, spirit_stones=5_000)
                await session.commit()
                mail = MailService(session)
                with pytest.raises(AppError) as exc:
                    await mail.send_gift(
                        a,
                        to_character_id=None,
                        to_name="赠乙",
                        spirit_stones=10,
                        items=[],
                    )
                assert exc.value.code == 40110

                friends = FriendService(session)
                applied = await friends.apply(a, target_character_id=None, target_name="赠乙")
                await session.commit()
                await friends.accept(b, int(applied["friendship_id"]))
                await session.commit()

                ok = await mail.send_gift(
                    a,
                    to_character_id=None,
                    to_name="赠乙",
                    spirit_stones=20,
                    items=[],
                    note_zh="一点心意",
                )
                await session.commit()
                assert ok["mail_id"]
                bch = await character_service.get_character_by_user_id(session, b.id)
                listed = await mail.list_mail(b)
                gifts = [m for m in listed["items"] if m["mail_kind"] == "gift"]
                assert gifts
                await session.refresh(bch)
                before = int(bch.spirit_stones)
                claimed = await mail.claim(b, gifts[0]["id"])
                await session.commit()
                assert claimed["claimed"]["spirit_stones"] == 20
                await session.refresh(bch)
                assert int(bch.spirit_stones) == before + 20

                # 压低日次数上限测拒绝（gift 为可变 dict）
                from app.services.realm_config import get_game_config

                get_game_config().mail.gift["daily_count_cap"] = 1
                with pytest.raises(AppError) as exc2:
                    await mail.send_gift(
                        a,
                        to_character_id=None,
                        to_name="赠乙",
                        spirit_stones=1,
                        items=[],
                    )
                assert "上限" in exc2.value.message

    _run(_body())


def test_auction_unsold_refunds_via_mail(tmp_path: Path) -> None:
    """流拍拍品进系统邮件，领取后入包。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "auction_mail.db") as factory:
            async with factory() as session:
                seller = await _register(session, "as@example.com", "拍甲")
                await GmService(session).gm_set_character(seller, spirit_stones=1_000)
                await session.commit()
                sch = await character_service.get_character_by_user_id(session, seller.id)
                inv = InventoryService(session)
                await inv.add_item(
                    sch.id,
                    item_type="material",
                    item_id="herb_spirit_grass",
                    quantity=3,
                )
                await session.commit()
                trade = TradeService(session)
                created = await trade.create_auction(
                    seller,
                    offer_items=[{"item_id": "herb_spirit_grass", "quantity": 2}],
                    start_price=100,
                    duration_sec=60,
                )
                await session.commit()
                lot_id = int(created["lot"]["id"])
                # 强制到期
                from app.db.models.social_trade import AuctionLot

                lot = await session.get(AuctionLot, lot_id)
                assert lot is not None
                lot.ends_at = now_utc() - timedelta(seconds=5)
                await session.commit()

                await trade.list_auctions(seller)
                await session.commit()
                mails = (
                    await session.execute(
                        select(MailMessage).where(
                            MailMessage.to_character_id == sch.id,
                            MailMessage.reason == "auction_unsold",
                        ),
                    )
                ).scalars().all()
                assert len(list(mails)) == 1
                counts_mid = await inv.material_counts(sch.id)
                assert counts_mid.get("herb_spirit_grass", 0) == 1
                claimed = await MailService(session).claim(seller, mails[0].id)
                await session.commit()
                assert claimed["claimed"]["items"][0]["quantity"] == 2
                counts = await inv.material_counts(sch.id)
                assert counts.get("herb_spirit_grass", 0) == 3

    _run(_body())
