"""M7 L5：机缘 random/fixed、跨频道拒领、过期退邮件。"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.time_utils import now_utc
from app.db.models import User
from app.db.models.heritage import HeritagePacket
from app.db.models.mail import MailMessage
from app.domain.heritage_rules import build_share_plan, split_spirit_fixed, split_spirit_random
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.currency_ledger_service import reset_system_recycle_balance_for_tests
from app.services.gm_service import GmService
from app.services.heritage_service import HeritageService
from app.services.inventory_service import InventoryService
from app.services.mail_service import MailService
from app.services.realm_config import clear_game_config_cache
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


def test_split_rules_sum() -> None:
    """纯规则：random/fixed 拆分之和正确。"""
    import random

    rng = random.Random(42)
    parts = split_spirit_random(100, 5, rng=rng)
    assert sum(parts) == 100
    assert len(parts) == 5
    fixed = split_spirit_fixed(100, 3, remainder_policy="last_share")
    assert sum(fixed) == 100
    plan = build_share_plan(
        spirit_stones=90,
        items=[{"item_id": "stamina_pill_minor", "quantity": 3}],
        share_count=3,
        mode="fixed",
        seed=1,
    )
    assert len(plan) == 3
    assert sum(p["spirit_stones"] for p in plan) == 90
    assert sum(sum(i["quantity"] for i in p["items"]) for p in plan) == 3


def test_world_random_claim(tmp_path: Path) -> None:
    """世界频道拼手气纯灵石；两账号可领；第三方不可跨频（世界人人可领）。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "h_world.db") as factory:
            async with factory() as session:
                a = await _register(session, "ha@example.com", "传甲")
                b = await _register(session, "hb@example.com", "传乙")
                await GmService(session).gm_set_character(a, spirit_stones=5_000)
                await session.commit()
                svc = HeritageService(session)
                created = await svc.create(
                    a,
                    channel_ref="world",
                    mode="random",
                    share_count=2,
                    spirit_stones=200,
                    items=[],
                    note_zh="天下共沾",
                )
                await session.commit()
                pid = int(created["packet"]["id"])
                ach = await character_service.get_character_by_user_id(session, a.id)
                before_a = int(ach.spirit_stones)
                # 发送方也可领（设计未禁）
                c1 = await svc.claim(a, pid)
                await session.commit()
                assert c1["claimed"]["spirit_stones"] >= 0
                c2 = await svc.claim(b, pid)
                await session.commit()
                assert c2["claimed"]["spirit_stones"] >= 0
                assert c1["claimed"]["spirit_stones"] + c2["claimed"]["spirit_stones"] == 200
                with pytest.raises(AppError) as exc:
                    await svc.claim(b, pid)
                assert exc.value.code == 40140
                await session.refresh(ach)
                # 发出时已扣 200；自己领回一份
                assert int(ach.spirit_stones) == before_a + c1["claimed"]["spirit_stones"]

    _run(_body())


def test_sect_fixed_with_pill_and_cross_reject(tmp_path: Path) -> None:
    """宗门定额灵石+丹；散修跨宗拒领。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "h_sect.db") as factory:
            async with factory() as session:
                a = await _register(session, "sa@example.com", "宗传甲")
                b = await _register(session, "sb@example.com", "散修乙")
                await GmService(session).gm_set_character(
                    a,
                    major_realm="qi_refining",
                    spirit_stones=10_000,
                )
                await session.commit()
                ach = await character_service.get_character_by_user_id(session, a.id)
                await InventoryService(session).add_item(
                    ach.id,
                    item_type="consumable",
                    item_id="stamina_pill_minor",
                    quantity=2,
                )
                await session.commit()
                await SectService(session).join(a, template_id="qingyun_zong")
                await session.commit()
                await session.refresh(ach)
                cref = f"sect:{ach.sect_id}"
                svc = HeritageService(session)
                created = await svc.create(
                    a,
                    channel_ref=cref,
                    mode="fixed",
                    share_count=2,
                    spirit_stones=100,
                    items=[{"item_id": "stamina_pill_minor", "quantity": 2}],
                )
                await session.commit()
                pid = int(created["packet"]["id"])
                # 散修不可领宗门机缘
                with pytest.raises(AppError) as exc:
                    await svc.claim(b, pid)
                assert exc.value.code == 40140
                # 同门自领
                got = await svc.claim(a, pid)
                await session.commit()
                assert got["claimed"]["spirit_stones"] == 50
                assert got["claimed"]["items"]

                # 绑定物拒发
                await InventoryService(session).add_item(
                    ach.id,
                    item_type="consumable",
                    item_id="bound_spirit_token",
                    quantity=1,
                )
                await session.commit()
                with pytest.raises(AppError) as exc2:
                    await svc.create(
                        a,
                        channel_ref=cref,
                        mode="fixed",
                        share_count=1,
                        spirit_stones=0,
                        items=[{"item_id": "bound_spirit_token", "quantity": 1}],
                    )
                assert exc2.value.code == 40111

    _run(_body())


def test_heritage_expire_refund_mail(tmp_path: Path) -> None:
    """过期未领退系统邮件。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "h_exp.db") as factory:
            async with factory() as session:
                a = await _register(session, "ea@example.com", "退甲")
                await GmService(session).gm_set_character(a, spirit_stones=3_000)
                await session.commit()
                svc = HeritageService(session)
                created = await svc.create(
                    a,
                    channel_ref="world",
                    mode="fixed",
                    share_count=2,
                    spirit_stones=200,
                    items=[],
                )
                await session.commit()
                pid = int(created["packet"]["id"])
                row = await session.get(HeritagePacket, pid)
                assert row is not None
                row.expires_at = now_utc() - timedelta(seconds=5)
                await session.commit()
                # 触发惰性过期
                listed = await svc.list_active(a, channel_ref="world")
                await session.commit()
                assert listed["items"] == []
                ach = await character_service.get_character_by_user_id(session, a.id)
                mails = (
                    await session.execute(
                        select(MailMessage).where(
                            MailMessage.to_character_id == ach.id,
                            MailMessage.reason == "heritage_expire",
                        ),
                    )
                ).scalars().all()
                assert len(list(mails)) == 1
                claimed = await MailService(session).claim(a, mails[0].id)
                await session.commit()
                assert claimed["claimed"]["spirit_stones"] == 200

    _run(_body())
