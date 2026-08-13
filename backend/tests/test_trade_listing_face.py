"""M7 L2：道友 + 交易行一口价 + 面交 + 绑定拒绝。"""

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
from app.services.friend_service import FriendService
from app.services.gm_service import GmService
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
    monkeypatch.setattr(settings, "friends_system_enabled", True)
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


def test_friends_apply_accept(tmp_path: Path) -> None:
    """道友双向确认。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "friends.db") as factory:
            async with factory() as session:
                a = await _register(session, "fa@example.com", "友甲")
                b = await _register(session, "fb@example.com", "友乙")
                svc = FriendService(session)
                applied = await svc.apply(a, target_character_id=None, target_name="友乙")
                await session.commit()
                fid = int(applied["friendship_id"])
                accepted = await svc.accept(b, fid)
                await session.commit()
                assert accepted["friend_count"] == 1
                listed = await svc.list_friends(a)
                assert listed["friend_count"] == 1
                assert listed["friends"][0]["peer_name"] == "友乙"

    _run(_body())


def test_trade_listing_buy_and_bound_reject(tmp_path: Path) -> None:
    """一口价成交；绑定物拒上架；手续费入回收。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "listing.db") as factory:
            async with factory() as session:
                seller = await _register(session, "ts@example.com", "商甲")
                buyer = await _register(session, "tb@example.com", "商乙")
                await GmService(session).gm_set_character(
                    seller,
                    spirit_stones=1_000,
                )
                await GmService(session).gm_set_character(
                    buyer,
                    spirit_stones=5_000,
                )
                await session.commit()
                inv = InventoryService(session)
                sch = await character_service.get_character_by_user_id(session, seller.id)
                bch = await character_service.get_character_by_user_id(session, buyer.id)
                await inv.add_item(
                    sch.id,
                    item_type="material",
                    item_id="herb_spirit_grass",
                    quantity=5,
                )
                await inv.add_item(
                    sch.id,
                    item_type="consumable",
                    item_id="bound_spirit_token",
                    quantity=1,
                )
                await session.commit()

                trade = TradeService(session)
                with pytest.raises(AppError) as exc:
                    await trade.create_listing(
                        seller,
                        mode="fixed_price",
                        offer_items=[{"item_id": "bound_spirit_token", "quantity": 1}],
                        price_spirit_stones=100,
                        ask_items=[],
                    )
                assert exc.value.code == 40111

                created = await trade.create_listing(
                    seller,
                    mode="fixed_price",
                    offer_items=[{"item_id": "herb_spirit_grass", "quantity": 2}],
                    price_spirit_stones=1000,
                    ask_items=[],
                )
                await session.commit()
                lid = int(created["listing"]["id"])
                bought = await trade.buy_listing(buyer, lid)
                await session.commit()
                assert bought["listing"]["status"] == "sold"
                await session.refresh(bch)
                await session.refresh(sch)
                # 买方付 1000；卖方得 950（5% 手续费）；回收 50
                assert int(bch.spirit_stones) == 4000
                assert int(sch.spirit_stones) == 1950
                from app.services.currency_ledger_service import system_recycle_balance

                assert system_recycle_balance() == 50
                buyer_counts = await inv.material_counts(bch.id)
                assert buyer_counts.get("herb_spirit_grass", 0) == 2

    _run(_body())


def test_face_trade_commit_and_timeout_unlock(tmp_path: Path) -> None:
    """面交：接受→草稿→锁定托管→双方确认→成交。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "face.db") as factory:
            async with factory() as session:
                a = await _register(session, "face_a@example.com", "面甲")
                b = await _register(session, "face_b@example.com", "面乙")
                await GmService(session).gm_set_character(a, spirit_stones=500)
                await GmService(session).gm_set_character(b, spirit_stones=500)
                await session.commit()
                inv = InventoryService(session)
                ach = await character_service.get_character_by_user_id(session, a.id)
                bch = await character_service.get_character_by_user_id(session, b.id)
                await inv.add_item(
                    ach.id,
                    item_type="material",
                    item_id="ore_iron_raw",
                    quantity=3,
                )
                await inv.add_item(
                    bch.id,
                    item_type="material",
                    item_id="wood_spirit",
                    quantity=2,
                )
                await session.commit()

                # 面交须道友
                friends = FriendService(session)
                applied = await friends.apply(a, target_character_id=None, target_name="面乙")
                await session.commit()
                await friends.accept(b, int(applied["friendship_id"]))
                await session.commit()

                trade = TradeService(session)
                invited = await trade.face_invite(
                    a,
                    peer_character_id=None,
                    peer_name="面乙",
                )
                await session.commit()
                assert invited["session"]["status"] == "pending_invite"
                sid = int(invited["session"]["id"])
                ver = int(invited["session"]["version"])

                accepted = await trade.face_accept(b, sid)
                await session.commit()
                assert accepted["session"]["status"] == "browsing"
                ver = int(accepted["session"]["version"])

                # 草稿不扣背包 / 灵石
                o1 = await trade.face_set_offer(
                    a,
                    sid,
                    items=[{"item_id": "ore_iron_raw", "quantity": 1}],
                    spirit_stones=50,
                    version=ver,
                )
                await session.commit()
                await session.refresh(ach)
                a_counts_draft = await inv.material_counts(ach.id)
                assert a_counts_draft.get("ore_iron_raw", 0) == 3
                assert int(ach.spirit_stones) == 500
                ver = int(o1["session"]["version"])
                assert o1["session"]["status"] == "browsing"
                assert o1["session"]["initiator_locked"] is False

                o2 = await trade.face_set_offer(
                    b,
                    sid,
                    items=[{"item_id": "wood_spirit", "quantity": 1}],
                    spirit_stones=0,
                    version=ver,
                )
                await session.commit()
                ver = int(o2["session"]["version"])

                lock_a = await trade.face_lock(a, sid, version=ver)
                await session.commit()
                ver = int(lock_a["session"]["version"])
                await session.refresh(ach)
                assert int(ach.spirit_stones) == 450  # locked: -50
                a_counts_locked = await inv.material_counts(ach.id)
                assert a_counts_locked.get("ore_iron_raw", 0) == 2
                assert lock_a["session"]["initiator_locked"] is True
                assert lock_a["session"]["status"] == "browsing"  # peer not locked yet

                lock_b = await trade.face_lock(b, sid, version=ver)
                await session.commit()
                ver = int(lock_b["session"]["version"])
                assert lock_b["session"]["status"] == "locking"
                assert lock_b["session"]["peer_locked"] is True

                await trade.face_confirm(a, sid, version=ver)
                await session.commit()
                done = await trade.face_confirm(b, sid, version=ver)
                await session.commit()
                assert done["session"]["status"] == "committed"
                await session.refresh(ach)
                await session.refresh(bch)
                a_counts = await inv.material_counts(ach.id)
                b_counts = await inv.material_counts(bch.id)
                assert a_counts.get("wood_spirit", 0) == 1
                assert b_counts.get("ore_iron_raw", 0) == 1
                assert int(bch.spirit_stones) == 550  # +50 from A

    _run(_body())



def test_face_peer_offer_keeps_other_lock(tmp_path: Path) -> None:
    """一方已锁定后，另一方改草稿不得拆掉对方锁定/托管。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "face_lock_keep.db") as factory:
            async with factory() as session:
                a = await _register(session, "lk_a@example.com", "锁甲")
                b = await _register(session, "lk_b@example.com", "锁乙")
                await GmService(session).gm_set_character(a, spirit_stones=500)
                await GmService(session).gm_set_character(b, spirit_stones=500)
                await session.commit()
                inv = InventoryService(session)
                ach = await character_service.get_character_by_user_id(session, a.id)
                bch = await character_service.get_character_by_user_id(session, b.id)
                await inv.add_item(
                    ach.id,
                    item_type="material",
                    item_id="ore_iron_raw",
                    quantity=2,
                )
                await inv.add_item(
                    bch.id,
                    item_type="material",
                    item_id="wood_spirit",
                    quantity=2,
                )
                await session.commit()
                friends = FriendService(session)
                applied = await friends.apply(a, target_character_id=None, target_name="锁乙")
                await session.commit()
                await friends.accept(b, int(applied["friendship_id"]))
                await session.commit()

                trade = TradeService(session)
                invited = await trade.face_invite(a, peer_character_id=None, peer_name="锁乙")
                await session.commit()
                sid = int(invited["session"]["id"])
                await trade.face_accept(b, sid)
                await session.commit()
                ver = int((await trade.face_get(a, sid))["session"]["version"])

                o1 = await trade.face_set_offer(
                    a,
                    sid,
                    items=[{"item_id": "ore_iron_raw", "quantity": 1}],
                    spirit_stones=50,
                    version=ver,
                )
                await session.commit()
                ver = int(o1["session"]["version"])
                lock_a = await trade.face_lock(a, sid, version=ver)
                await session.commit()
                ver = int(lock_a["session"]["version"])
                assert lock_a["session"]["initiator_locked"] is True
                await session.refresh(ach)
                stones_after_lock = int(ach.spirit_stones)

                # B 改草稿：A 仍应锁定且托管未退回
                o2 = await trade.face_set_offer(
                    b,
                    sid,
                    items=[{"item_id": "wood_spirit", "quantity": 1}],
                    spirit_stones=0,
                    version=ver,
                )
                await session.commit()
                assert o2["session"]["initiator_locked"] is True
                assert o2["session"]["peer_locked"] is False
                assert o2["session"]["you_are"] == "peer"
                await session.refresh(ach)
                assert int(ach.spirit_stones) == stones_after_lock
                a_counts = await inv.material_counts(ach.id)
                assert a_counts.get("ore_iron_raw", 0) == 1

                # 推送给对方的视角校验：以 A 视角拉取
                pub_a = (await trade.face_get(a, sid))["session"]
                assert pub_a["you_are"] == "initiator"
                assert pub_a["initiator_locked"] is True

    _run(_body())


def test_face_trade_vessel_offer_create_and_mutex(tmp_path: Path) -> None:
    """面交要约炉鼎：单侧可设；成交建关系；双方互斥。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "face_vessel.db") as factory:
            async with factory() as session:
                a = await _register(session, "fv_a@example.com", "炉交甲")
                b = await _register(session, "fv_b@example.com", "炉交乙")
                await GmService(session).gm_set_character(a, spirit_stones=200)
                await GmService(session).gm_set_character(b, spirit_stones=200)
                await session.commit()
                friends = FriendService(session)
                applied = await friends.apply(a, target_character_id=None, target_name="炉交乙")
                await session.commit()
                await friends.accept(b, int(applied["friendship_id"]))
                await session.commit()

                trade = TradeService(session)
                invited = await trade.face_invite(
                    a,
                    peer_character_id=None,
                    peer_name="炉交乙",
                )
                await session.commit()
                sid = int(invited["session"]["id"])
                ver = int(invited["session"]["version"])
                await trade.face_accept(b, sid)
                await session.commit()
                pub = await trade.face_get(a, sid)
                ver = int(pub["session"]["version"])

                o1 = await trade.face_set_offer(
                    a,
                    sid,
                    items=[],
                    spirit_stones=0,
                    version=ver,
                    vessel_offer={"hours": 24},
                )
                await session.commit()
                assert o1["session"]["initiator_offer"]["vessel_offer"]["hours"] == 24
                ver = int(o1["session"]["version"])

                with pytest.raises(AppError) as mutex_err:
                    await trade.face_set_offer(
                        b,
                        sid,
                        items=[],
                        spirit_stones=0,
                        version=ver,
                        vessel_offer={"hours": 12},
                    )
                assert "仅一方" in mutex_err.value.message

                o2 = await trade.face_set_offer(
                    b,
                    sid,
                    items=[],
                    spirit_stones=10,
                    version=ver,
                )
                await session.commit()
                ver = int(o2["session"]["version"])
                await trade.face_lock(a, sid, version=ver)
                await session.commit()
                pub = await trade.face_get(b, sid)
                ver = int(pub["session"]["version"])
                await trade.face_lock(b, sid, version=ver)
                await session.commit()
                pub = await trade.face_get(a, sid)
                ver = int(pub["session"]["version"])
                await trade.face_confirm(a, sid, version=ver)
                await session.commit()
                pub = await trade.face_get(b, sid)
                ver = int(pub["session"]["version"])
                done = await trade.face_confirm(b, sid, version=ver)
                await session.commit()
                assert done["session"]["status"] == "committed"
                assert done.get("vessel")
                assert done["vessel"]["extended"] is False

                from app.services.bond_service import BondService

                bonds = BondService(session)
                listed = await bonds.list_bonds(b)
                assert listed["vessel_count"] == 1
                assert listed["vessels"][0]["peer_name"] == "炉交甲"
                master = await bonds.list_bonds(a)
                assert master["my_master"] is not None
                assert master["my_master"]["peer_name"] == "炉交乙"

                # 主人不可再要约成为炉鼎；炉鼎方可延长
                invited2 = await trade.face_invite(
                    a,
                    peer_character_id=None,
                    peer_name="炉交乙",
                )
                await session.commit()
                sid2 = int(invited2["session"]["id"])
                await trade.face_accept(b, sid2)
                await session.commit()
                pub2 = await trade.face_get(b, sid2)
                assert pub2["session"]["vessel_context"]["can_offer_extend"] is False
                assert pub2["session"]["vessel_context"]["can_offer_become"] is False
                assert pub2["session"]["vessel_context"]["relation"] == "i_am_master"
                pub2a = await trade.face_get(a, sid2)
                assert pub2a["session"]["vessel_context"]["relation"] == "i_am_vessel"
                assert pub2a["session"]["vessel_context"]["can_offer_extend"] is True
                with pytest.raises(AppError):
                    await trade.face_set_offer(
                        b,
                        sid2,
                        items=[],
                        spirit_stones=0,
                        version=int(pub2["session"]["version"]),
                        vessel_offer={"hours": 5},
                    )
                # 炉鼎方可延长
                ext = await trade.face_set_offer(
                    a,
                    sid2,
                    items=[],
                    spirit_stones=0,
                    version=int(pub2a["session"]["version"]),
                    vessel_offer={"hours": 5},
                )
                await session.commit()
                assert ext["session"]["initiator_offer"]["vessel_offer"]["hours"] == 5

    _run(_body())


def test_companions_cannot_become_each_others_vessel(tmp_path: Path) -> None:
    """互为道侣不可面交要约互为炉鼎。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "comp_vessel.db") as factory:
            async with factory() as session:
                a = await _register(session, "cv_a@example.com", "侣甲")
                b = await _register(session, "cv_b@example.com", "侣乙")
                await GmService(session).gm_set_character(a, spirit_stones=200)
                await GmService(session).gm_set_character(b, spirit_stones=200)
                await session.commit()
                friends = FriendService(session)
                applied = await friends.apply(a, target_character_id=None, target_name="侣乙")
                await session.commit()
                await friends.accept(b, int(applied["friendship_id"]))
                await session.commit()

                from app.services.bond_service import BondService

                bonds = BondService(session)
                c_applied = await bonds.apply_companion(
                    a,
                    target_character_id=None,
                    target_name="侣乙",
                )
                await session.commit()
                await bonds.accept(b, int(c_applied["bond_id"]))
                await session.commit()

                trade = TradeService(session)
                invited = await trade.face_invite(
                    a,
                    peer_character_id=None,
                    peer_name="侣乙",
                )
                await session.commit()
                sid = int(invited["session"]["id"])
                await trade.face_accept(b, sid)
                await session.commit()
                pub = await trade.face_get(a, sid)
                assert pub["session"]["vessel_context"]["are_companions"] is True
                assert pub["session"]["vessel_context"]["can_offer_become"] is False
                with pytest.raises(AppError) as err:
                    await trade.face_set_offer(
                        a,
                        sid,
                        items=[],
                        spirit_stones=0,
                        version=int(pub["session"]["version"]),
                        vessel_offer={"hours": 24},
                    )
                assert "道侣" in err.value.message

    _run(_body())


def test_face_trade_reject_invite(tmp_path: Path) -> None:
    """受邀方拒绝 pending_invite。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "face_reject.db") as factory:
            async with factory() as session:
                a = await _register(session, "fr_a@example.com", "拒甲")
                b = await _register(session, "fr_b@example.com", "拒乙")
                friends = FriendService(session)
                applied = await friends.apply(a, target_character_id=None, target_name="拒乙")
                await session.commit()
                await friends.accept(b, int(applied["friendship_id"]))
                await session.commit()
                trade = TradeService(session)
                invited = await trade.face_invite(
                    a,
                    peer_character_id=None,
                    peer_name="拒乙",
                )
                await session.commit()
                sid = int(invited["session"]["id"])
                pending = await trade.face_list_pending(b)
                assert len(pending["items"]) == 1
                assert int(pending["items"][0]["session_id"]) == sid
                opts = await trade.face_invite_options(a)
                assert opts["face_max_item_lines"] == 16
                assert any(x["name"] == "拒乙" for x in opts["friends"])
                rejected = await trade.face_reject(b, sid)
                await session.commit()
                assert rejected["session"]["status"] == "cancelled"
                pending2 = await trade.face_list_pending(b)
                assert pending2["items"] == []

    _run(_body())


def test_face_offer_max_sixteen_lines(tmp_path: Path) -> None:
    """单侧报价最多 16 种道具。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "face_16.db") as factory:
            async with factory() as session:
                a = await _register(session, "f16_a@example.com", "十六甲")
                b = await _register(session, "f16_b@example.com", "十六乙")
                friends = FriendService(session)
                applied = await friends.apply(a, target_character_id=None, target_name="十六乙")
                await session.commit()
                await friends.accept(b, int(applied["friendship_id"]))
                await session.commit()
                trade = TradeService(session)
                invited = await trade.face_invite(
                    a,
                    peer_character_id=None,
                    peer_name="十六乙",
                )
                await session.commit()
                sid = int(invited["session"]["id"])
                await trade.face_accept(b, sid)
                await session.commit()
                got = await trade.face_get(a, sid)
                ver = int(got["session"]["version"])
                lines = [{"item_id": "ore_iron_raw", "quantity": 1}] * 17
                with pytest.raises(AppError) as ei:
                    await trade.face_set_offer(
                        a,
                        sid,
                        items=lines,
                        spirit_stones=0,
                        version=ver,
                    )
                assert ei.value.http_status == 400

    _run(_body())
