"""机缘发/领：后端校验 + 余额/背包/流水/包表落库审计。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import User
from app.db.models.heritage import HeritageClaim, HeritagePacket
from app.db.models.social_trade import CurrencyLedger
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.currency_ledger_service import reset_system_recycle_balance_for_tests
from app.services.gm_service import GmService
from app.services.heritage_service import HeritageService
from app.services.inventory_service import InventoryService
from app.services.realm_config import clear_game_config_cache
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
    monkeypatch.setattr(settings, "chat_system_enabled", True)
    monkeypatch.setattr(settings, "chat_ws_push_enabled", False)
    monkeypatch.setattr(settings, "heritage_system_enabled", True)
    monkeypatch.setattr(settings, "mail_system_enabled", True)
    monkeypatch.setattr(settings, "heritage_expire_sec", 0)
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


def test_heritage_db_audit_stones_items_ledger(tmp_path: Path) -> None:
    """发机缘扣灵石/道具并写包表+流水；开缘入账并写领取行。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "h_audit.db") as factory:
            async with factory() as session:
                sender = await _register(session, "audit_s@example.com", "审甲")
                claimer = await _register(session, "audit_c@example.com", "审乙")
                await GmService(session).gm_set_character(sender, spirit_stones=5_000)
                await session.commit()

                sch = await character_service.get_character_by_user_id(session, sender.id)
                cch = await character_service.get_character_by_user_id(session, claimer.id)
                inv = InventoryService(session)
                await inv.add_item(
                    sch.id,
                    item_type="consumable",
                    item_id="stamina_pill_minor",
                    quantity=5,
                )
                await session.commit()
                await session.refresh(sch)

                stones_before = int(sch.spirit_stones)
                pill_before = int((await inv.material_counts(sch.id)).get("stamina_pill_minor", 0))
                assert pill_before == 5

                svc = HeritageService(session)
                created = await svc.create(
                    sender,
                    channel_ref="world",
                    mode="fixed",
                    share_count=2,
                    spirit_stones=200,
                    items=[{"item_id": "stamina_pill_minor", "quantity": 2}],
                    note_zh="审计机缘",
                )
                await session.commit()

                pid = int(created["packet"]["id"])
                await session.refresh(sch)
                # —— 发：角色余额/背包变化 ——
                assert int(sch.spirit_stones) == stones_before - 200
                pill_after_send = int(
                    (await inv.material_counts(sch.id)).get("stamina_pill_minor", 0),
                )
                assert pill_after_send == pill_before - 2

                # —— 发：包表落库 ——
                row = await session.get(HeritagePacket, pid)
                assert row is not None
                assert row.status == "open"
                assert int(row.spirit_stones_total) == 200
                assert int(row.share_count) == 2
                assert int(row.shares_claimed) == 0
                assert "stamina_pill_minor" in (row.items_json or "")
                assert row.shares_plan_json and row.shares_plan_json != "[]"

                # —— 发：灵石流水 ——
                ledgers = (
                    await session.execute(
                        select(CurrencyLedger).where(
                            CurrencyLedger.character_id == sch.id,
                            CurrencyLedger.reason == "heritage_send",
                        ),
                    )
                ).scalars().all()
                assert len(list(ledgers)) >= 1
                assert any(int(x.delta) == -200 for x in ledgers)

                # —— 领：第二人开缘 ——
                claimer_stones_before = int(cch.spirit_stones)
                got = await svc.claim(claimer, pid)
                await session.commit()
                await session.refresh(cch)

                claimed_stones = int(got["claimed"]["spirit_stones"])
                assert claimed_stones == 100  # fixed 均分
                assert int(cch.spirit_stones) == claimer_stones_before + claimed_stones
                claim_items = got["claimed"]["items"] or []
                assert sum(int(i["quantity"]) for i in claim_items) == 1

                pill_claimer = int(
                    (await inv.material_counts(cch.id)).get("stamina_pill_minor", 0),
                )
                assert pill_claimer == 1

                # —— 领：领取行 + 流水 ——
                claims = (
                    await session.execute(
                        select(HeritageClaim).where(HeritageClaim.packet_id == pid),
                    )
                ).scalars().all()
                assert len(list(claims)) == 1
                assert int(claims[0].character_id) == int(cch.id)
                assert int(claims[0].spirit_stones) == claimed_stones

                claim_ledgers = (
                    await session.execute(
                        select(CurrencyLedger).where(
                            CurrencyLedger.character_id == cch.id,
                            CurrencyLedger.reason == "heritage_claim",
                        ),
                    )
                ).scalars().all()
                assert any(int(x.delta) == claimed_stones for x in claim_ledgers)

                await session.refresh(row)
                assert int(row.shares_claimed) == 1
                assert row.status == "open"

    _run(_body())


def test_heritage_sequential_packets_claimable(tmp_path: Path) -> None:
    """连续多发包后各包可分别开缘；purge 后 id 复用也不应误判已开过。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "h_seq.db") as factory:
            async with factory() as session:
                a = await _register(session, "seq_a@example.com", "连甲")
                b = await _register(session, "seq_b@example.com", "连乙")
                await GmService(session).gm_set_character(a, spirit_stones=20_000)
                await session.commit()
                svc = HeritageService(session)

                # 连续发 3 包（各 1 份），乙逐个开缘均应成功
                pids: list[int] = []
                for i in range(3):
                    created = await svc.create(
                        a,
                        channel_ref="world",
                        mode="fixed",
                        share_count=1,
                        spirit_stones=100,
                        items=[],
                        note_zh=f"连发{i}",
                    )
                    await session.commit()
                    pids.append(int(created["packet"]["id"]))

                assert len(set(pids)) == 3
                for pid in pids:
                    got = await svc.claim(b, pid)
                    await session.commit()
                    assert int(got["claimed"]["spirit_stones"]) == 100

                # purge 后残留领取行 + id 复用：显式清 claim 后新包仍可领
                # 再发一包（可能复用旧 id），乙应仍能开缘
                created4 = await svc.create(
                    a,
                    channel_ref="world",
                    mode="fixed",
                    share_count=1,
                    spirit_stones=50,
                    items=[],
                    note_zh="复用后",
                )
                await session.commit()
                pid4 = int(created4["packet"]["id"])
                got4 = await svc.claim(b, pid4)
                await session.commit()
                assert int(got4["claimed"]["spirit_stones"]) == 50

                # 甲连续自领自己发的两包（各 1 份）
                p5 = await svc.create(
                    a,
                    channel_ref="world",
                    mode="fixed",
                    share_count=1,
                    spirit_stones=30,
                    items=[],
                )
                await session.commit()
                p6 = await svc.create(
                    a,
                    channel_ref="world",
                    mode="fixed",
                    share_count=1,
                    spirit_stones=40,
                    items=[],
                )
                await session.commit()
                id5 = int(p5["packet"]["id"])
                id6 = int(p6["packet"]["id"])
                assert id5 != id6
                await svc.claim(a, id5)
                await session.commit()
                await svc.claim(a, id6)
                await session.commit()

                # 领完 purge 后领取行须清空（否则旧库 id 复用会误判已开过）
                created7 = await svc.create(
                    a,
                    channel_ref="world",
                    mode="fixed",
                    share_count=1,
                    spirit_stones=25,
                    items=[],
                )
                await session.commit()
                pid7 = int(created7["packet"]["id"])
                await svc.claim(b, pid7)
                await session.commit()
                after_purge = (
                    await session.execute(
                        select(HeritageClaim).where(HeritageClaim.packet_id == pid7),
                    )
                ).scalars().all()
                assert after_purge == []
                assert await session.get(HeritagePacket, pid7) is None

    _run(_body())


def test_heritage_reject_insufficient_and_bound(tmp_path: Path) -> None:
    """灵石不足 / 道具不足 / 绑定物：后端拒绝且不落有效包。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "h_reject.db") as factory:
            async with factory() as session:
                user = await _register(session, "rej@example.com", "拒甲")
                user_id = int(user.id)
                await GmService(session).gm_set_character(user, spirit_stones=50)
                await session.commit()
                svc = HeritageService(session)

                # 灵石不足
                with pytest.raises(AppError) as exc_stone:
                    await svc.create(
                        user,
                        channel_ref="world",
                        mode="fixed",
                        share_count=1,
                        spirit_stones=500,
                        items=[],
                    )
                assert "不足" in str(exc_stone.value.message)
                await session.rollback()

                packets = (
                    await session.execute(select(HeritagePacket))
                ).scalars().all()
                assert list(packets) == []

                # 道具不足
                user = await session.get(User, user_id)
                assert user is not None
                with pytest.raises(AppError) as exc_item:
                    await svc.create(
                        user,
                        channel_ref="world",
                        mode="fixed",
                        share_count=1,
                        spirit_stones=0,
                        items=[{"item_id": "stamina_pill_minor", "quantity": 9}],
                    )
                assert exc_item.value.code == 40055
                await session.rollback()

                # 绑定物
                user = await session.get(User, user_id)
                assert user is not None
                ch = await character_service.get_character_by_user_id(session, user_id)
                await InventoryService(session).add_item(
                    ch.id,
                    item_type="consumable",
                    item_id="bound_spirit_token",
                    quantity=1,
                )
                await session.commit()
                with pytest.raises(AppError) as exc_bound:
                    await svc.create(
                        user,
                        channel_ref="world",
                        mode="fixed",
                        share_count=1,
                        spirit_stones=0,
                        items=[{"item_id": "bound_spirit_token", "quantity": 1}],
                    )
                assert exc_bound.value.code == 40111
                await session.rollback()

                # 拒发后余额未变
                ch = await character_service.get_character_by_user_id(session, user_id)
                assert int(ch.spirit_stones) == 50
                counts = await InventoryService(session).material_counts(ch.id)
                assert int(counts.get("bound_spirit_token", 0)) == 1

    _run(_body())
