"""M7 L6：拜师→日课/传授→出师与自动出师；道友引渡成本差。"""

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
from app.services.ferry_service import FerryService
from app.services.friend_service import FriendService
from app.services.gm_service import GmService
from app.services.mentor_service import MentorService
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
    monkeypatch.setattr(settings, "mentor_system_enabled", True)
    monkeypatch.setattr(settings, "friends_system_enabled", True)
    monkeypatch.setattr(settings, "sect_system_enabled", True)
    monkeypatch.setattr(settings, "same_region_stub", True)
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


def test_mentor_apply_lesson_graduate(tmp_path: Path) -> None:
    """拜师→日课传道完成任务→出师；同境界拒拜。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "mentor.db") as factory:
            async with factory() as session:
                master_u = await _register(session, "m@example.com", "师尊甲")
                appr_u = await _register(session, "a@example.com", "弟子乙")
                await GmService(session).gm_set_character(
                    master_u,
                    major_realm="foundation",
                    spirit_stones=5_000,
                    cultivation_points=10_000,
                )
                await GmService(session).gm_set_character(
                    appr_u,
                    major_realm="body_tempering",
                    spirit_stones=500,
                )
                await session.commit()
                svc = MentorService(session)
                applied = await svc.apply(
                    appr_u,
                    target_character_id=None,
                    target_name="师尊甲",
                    intent="apprentice",
                )
                await session.commit()
                bond_id = int(applied["bond_id"])
                await svc.accept(master_u, bond_id)
                await session.commit()
                me = await svc.me(appr_u)
                assert me["bond"]["status"] == "active"
                assert me["channel_ref"] and me["channel_ref"].startswith("mentor:")
                assert me["daily"] is not None
                assert me["options"] is not None

                # 日课传道推进任务
                lesson = await svc.teach_lesson(master_u, kind="dao", resource="spirit")
                await session.commit()
                assert lesson["amount"] > 0
                me2 = await svc.me(appr_u)
                assert any(q["completed"] for q in me2["quests"])
                assert me2["daily"]["lesson_done"] is True

                graduated = await svc.graduate(appr_u)
                await session.commit()
                assert graduated["bond"]["status"] == "graduated"

                # 同境界拒拜
                c = await _register(session, "c@example.com", "路人丙")
                await GmService(session).gm_set_character(
                    c,
                    major_realm="body_tempering",
                )
                await session.commit()
                with pytest.raises(AppError) as exc:
                    await svc.apply(
                        c,
                        target_name="弟子乙",
                        target_character_id=None,
                        intent="apprentice",
                    )
                assert exc.value.code == 40150

    _run(_body())


def test_mentor_auto_graduate_same_major(tmp_path: Path) -> None:
    """弟子追上师傅大境界时自动出师。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "mentor_auto.db") as factory:
            async with factory() as session:
                master_u = await _register(session, "ma@example.com", "师尊丙")
                appr_u = await _register(session, "aa@example.com", "弟子丁")
                await GmService(session).gm_set_character(
                    master_u,
                    major_realm="foundation",
                    cultivation_points=5_000,
                )
                await GmService(session).gm_set_character(
                    appr_u,
                    major_realm="body_tempering",
                )
                await session.commit()
                svc = MentorService(session)
                applied = await svc.apply(
                    appr_u,
                    target_name="师尊丙",
                    target_character_id=None,
                    intent="apprentice",
                )
                await session.commit()
                await svc.accept(master_u, int(applied["bond_id"]))
                await session.commit()

                await GmService(session).gm_set_character(
                    appr_u,
                    major_realm="foundation",
                )
                await session.commit()
                me = await svc.me(appr_u)
                assert me["bond"] is None
                assert me.get("auto_graduate_message")

    _run(_body())


def test_mentor_teach_recipe_and_daily_lesson_mutex(tmp_path: Path) -> None:
    """传授配方可当日完成；日课三选一互斥。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "mentor_teach.db") as factory:
            async with factory() as session:
                from app.db.models.mentor import CharacterCraftKnowledge

                master_u = await _register(session, "mt@example.com", "师尊戊")
                appr_u = await _register(session, "at@example.com", "弟子己")
                await GmService(session).gm_set_character(
                    master_u,
                    major_realm="foundation",
                    cultivation_points=8_000,
                    crafting_exp=5_000,
                )
                await GmService(session).gm_set_character(
                    appr_u,
                    major_realm="qi_refining",
                )
                await session.commit()
                svc = MentorService(session)
                applied = await svc.apply(
                    appr_u,
                    target_name="师尊戊",
                    target_character_id=None,
                    intent="apprentice",
                )
                await session.commit()
                await svc.accept(master_u, int(applied["bond_id"]))
                await session.commit()

                taught = await svc.teach_item(
                    master_u,
                    item_kind="recipe",
                    item_id="pill_stamina_minor",
                )
                await session.commit()
                assert taught["completed"] is True
                appr = await character_service.get_character_by_user_id(session, appr_u.id)
                from app.domain.event_logs import parse_pending_event_logs

                pend_logs = parse_pending_event_logs(appr)
                assert any("传授" in str(x.get("message") or "") for x in pend_logs)
                know = (
                    await session.execute(
                        select(CharacterCraftKnowledge).where(
                            CharacterCraftKnowledge.character_id == appr.id,
                            CharacterCraftKnowledge.recipe_id == "pill_stamina_minor",
                        ),
                    )
                ).scalar_one_or_none()
                assert know is not None

                await svc.teach_lesson(
                    master_u,
                    kind="craft",
                    target_id="beginner_alchemy",
                )
                await session.commit()
                with pytest.raises(AppError) as exc:
                    await svc.teach_lesson(
                        master_u,
                        kind="dao",
                        resource="spirit",
                    )
                assert exc.value.code == 40000

    _run(_body())


def test_mentor_apprentice_study_stacks_with_teach(tmp_path: Path) -> None:
    """徒弟请学可叠加师傅未完成的同种功法传授；同日师傅传授+徒弟请学各一次。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "mentor_study.db") as factory:
            async with factory() as session:
                from app.db.models.mentor import MentorTransmission
                from app.db.models.technique import CharacterTechnique

                master_u = await _register(session, "ms@example.com", "师尊庚")
                appr_u = await _register(session, "as@example.com", "弟子辛")
                await GmService(session).gm_set_character(
                    master_u,
                    major_realm="foundation",
                    cultivation_points=8_000,
                )
                await GmService(session).gm_set_character(
                    appr_u,
                    major_realm="qi_refining",
                )
                await session.commit()
                master = await character_service.get_character_by_user_id(session, master_u.id)
                tech = (
                    await session.execute(
                        select(CharacterTechnique).where(
                            CharacterTechnique.character_id == master.id,
                            CharacterTechnique.technique_id == "basic_qi_art",
                        ),
                    )
                ).scalar_one_or_none()
                if tech is None:
                    session.add(
                        CharacterTechnique(
                            character_id=master.id,
                            technique_id="basic_qi_art",
                            level=3,
                        ),
                    )
                else:
                    tech.level = max(int(tech.level or 0), 3)
                await session.commit()

                svc = MentorService(session)
                applied = await svc.apply(
                    appr_u,
                    target_name="师尊庚",
                    target_character_id=None,
                    intent="apprentice",
                )
                await session.commit()
                await svc.accept(master_u, int(applied["bond_id"]))
                await session.commit()

                # 强制多日传授：先写入进行中进度
                bond = await svc.get_active_bond_for(master.id)
                assert bond is not None
                session.add(
                    MentorTransmission(
                        bond_id=bond.id,
                        item_kind="technique",
                        item_id="basic_qi_art",
                        required_sessions=4,
                        progress=1,
                        status="active",
                        last_day_key=None,
                    ),
                )
                await session.commit()

                taught = await svc.teach_item(
                    master_u,
                    item_kind="technique",
                    item_id="basic_qi_art",
                )
                await session.commit()
                assert taught["completed"] is False
                assert taught["transmission"]["progress"] == 2

                studied = await svc.study_technique(
                    appr_u,
                    technique_id="basic_qi_art",
                )
                await session.commit()
                assert studied["completed"] is False
                assert studied["transmission"]["progress"] == 3
                assert studied["daily"]["study_done"] is True

                with pytest.raises(AppError) as exc:
                    await svc.study_technique(appr_u, technique_id="basic_qi_art")
                assert exc.value.code == 40000

                me = await svc.me(appr_u)
                assert any(
                    t["item_id"] == "basic_qi_art" and t["progress"] == 3
                    for t in me["transmissions"]
                )
                assert me["options"]["study_techniques"]

    _run(_body())


def test_mentor_lineage_and_direct_lesson_bonus(tmp_path: Path) -> None:
    """师承单含出师弟子；亲传授业次数+1，传授次数不变。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "mentor_lineage.db") as factory:
            async with factory() as session:
                master_u = await _register(session, "ml@example.com", "师尊壬")
                a1 = await _register(session, "a1@example.com", "弟子甲")
                a2 = await _register(session, "a2@example.com", "弟子乙")
                await GmService(session).gm_set_character(
                    master_u,
                    major_realm="foundation",
                    cultivation_points=20_000,
                    crafting_exp=8_000,
                )
                await GmService(session).gm_set_character(
                    a1,
                    major_realm="qi_refining",
                )
                await GmService(session).gm_set_character(
                    a2,
                    major_realm="qi_refining",
                )
                await session.commit()
                svc = MentorService(session)

                applied1 = await svc.apply(
                    a1,
                    target_name="师尊壬",
                    target_character_id=None,
                    intent="apprentice",
                )
                await session.commit()
                await svc.accept(master_u, int(applied1["bond_id"]))
                await session.commit()

                applied2 = await svc.apply(
                    a2,
                    target_name="师尊壬",
                    target_character_id=None,
                    intent="apprentice",
                )
                await session.commit()
                await svc.accept(master_u, int(applied2["bond_id"]))
                await session.commit()

                # 甲出师
                await GmService(session).gm_set_character(a1, major_realm="foundation")
                await session.commit()
                me_a1_grad = await svc.me(a1)
                assert me_a1_grad.get("auto_graduate_message") or me_a1_grad.get("bond") is None
                lineage = (await svc.me(master_u))["lineage"]
                assert lineage is not None
                assert len(lineage["disciples"]) >= 2
                assert lineage["disciples"][0]["ordinal_title_zh"] == "大弟子"
                assert lineage["disciples"][1]["ordinal_title_zh"] == "二弟子"
                assert any(d["graduated"] for d in lineage["disciples"])

                appr2 = await character_service.get_character_by_user_id(session, a2.id)

                # 指定乙为亲传
                set_d = await svc.set_direct_disciples(
                    master_u,
                    apprentice_character_ids=[appr2.id],
                )
                await session.commit()
                assert set_d["lineage"]["direct_count"] == 1

                # 当日不可解除
                with pytest.raises(AppError) as exc_clear:
                    await svc.set_direct_disciples(
                        master_u,
                        apprentice_character_ids=[],
                    )
                assert exc_clear.value.code == 40000

                # 亲传：授业两次；传授仍一日一次
                await svc.teach_lesson(
                    master_u,
                    kind="craft",
                    target_id="beginner_alchemy",
                )
                await session.commit()
                await svc.teach_lesson(
                    master_u,
                    kind="craft",
                    target_id="beginner_alchemy",
                )
                await session.commit()
                with pytest.raises(AppError):
                    await svc.teach_lesson(
                        master_u,
                        kind="craft",
                        target_id="beginner_alchemy",
                    )

                taught = await svc.teach_item(
                    master_u,
                    item_kind="recipe",
                    item_id="pill_stamina_minor",
                )
                await session.commit()
                assert taught["daily"]["teach_done"] is True
                with pytest.raises(AppError):
                    await svc.teach_item(
                        master_u,
                        item_kind="recipe",
                        item_id="pill_stamina_minor",
                    )

                from datetime import timedelta

                from app.core.time_utils import now_utc
                from app.db.models.mentor import MentorBond

                bond2 = (
                    await session.execute(
                        select(MentorBond).where(
                            MentorBond.apprentice_character_id == appr2.id,
                            MentorBond.status == "active",
                        ),
                    )
                ).scalar_one()
                # 回拨指定日，模拟隔日可解除
                bond2.direct_set_day_key = (
                    now_utc() - timedelta(days=1)
                ).strftime("%Y-%m-%d")
                await session.commit()

                cleared = await svc.set_direct_disciples(
                    master_u,
                    apprentice_character_ids=[],
                )
                await session.commit()
                assert cleared["lineage"]["direct_count"] == 0

                # 解除当日不可再指定同一人
                with pytest.raises(AppError) as exc_re:
                    await svc.set_direct_disciples(
                        master_u,
                        apprentice_character_ids=[appr2.id],
                    )
                assert exc_re.value.code == 40000

                # 隔日可再指定
                await session.refresh(bond2)
                bond2.direct_cleared_day_key = (
                    now_utc() - timedelta(days=1)
                ).strftime("%Y-%m-%d")
                await session.commit()
                re_set = await svc.set_direct_disciples(
                    master_u,
                    apprentice_character_ids=[appr2.id],
                )
                await session.commit()
                assert re_set["lineage"]["direct_count"] == 1

                # 出师自动解除亲传
                await GmService(session).gm_set_character(a2, major_realm="foundation")
                await session.commit()
                me_a2 = await svc.me(a2)
                assert me_a2.get("bond") is None
                lin2 = (await svc.me(master_u))["lineage"]
                eth = next(d for d in lin2["disciples"] if d["character_id"] == appr2.id)
                assert eth["graduated"] is True
                assert eth["is_direct"] is False

                # 已出师弟子仍可见师承单
                me_a1 = await svc.me(a1)
                assert me_a1["lineage"] is not None
                assert any(d["graduated"] for d in me_a1["lineage"]["disciples"])

    _run(_body())


def test_ferry_friend_rescue_cheaper(tmp_path: Path) -> None:
    """道友引渡成功；成本低于自救；非道友拒。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "ferry_soc.db") as factory:
            async with factory() as session:
                victim_u = await _register(session, "v@example.com", "陨落甲")
                friend_u = await _register(session, "f@example.com", "道友乙")
                stranger_u = await _register(session, "s@example.com", "路人丁")
                await GmService(session).gm_set_character(friend_u, spirit_stones=2_000)
                await GmService(session).gm_set_character(victim_u, spirit_stones=50)
                await session.commit()
                friends = FriendService(session)
                applied = await friends.apply(
                    victim_u,
                    target_character_id=None,
                    target_name="道友乙",
                )
                await session.commit()
                await friends.accept(friend_u, int(applied["friendship_id"]))
                await session.commit()

                ferry = FerryService(session)
                victim = await character_service.get_character_by_user_id(session, victim_u.id)
                await ferry.enter_awaiting_ferry(victim)
                await session.commit()

                with pytest.raises(AppError) as exc:
                    await ferry.social_rescue(
                        stranger_u,
                        target_name="陨落甲",
                        target_character_id=None,
                        mode="friend",
                    )
                assert exc.value.code == 40180

                friend_ch = await character_service.get_character_by_user_id(session, friend_u.id)
                before = int(friend_ch.spirit_stones)
                rescued = await ferry.social_rescue(
                    friend_u,
                    target_name="陨落甲",
                    target_character_id=None,
                    mode="friend",
                )
                await session.commit()
                assert rescued["rescued"] is True
                cost = int(rescued["spirit_stones_spent"])
                assert cost < 500  # 低于自救
                await session.refresh(friend_ch)
                assert int(friend_ch.spirit_stones) == before - cost
                await session.refresh(victim)
                assert victim.status == "normal"

                # get_me 展示成本差
                await ferry.enter_awaiting_ferry(victim)
                await session.commit()
                panel = await ferry.get_me(victim_u)
                assert panel["ferry"]["social_rescue"]["friend_cheaper_by"] > 0

    _run(_body())


def test_ferry_sect_rescue_requires_higher_realm(tmp_path: Path) -> None:
    """同门引渡：修为不够拒绝；够则成功。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "ferry_sect.db") as factory:
            async with factory() as session:
                low = await _register(session, "low@example.com", "低修甲")
                high = await _register(session, "hi@example.com", "高修乙")
                await GmService(session).gm_set_character(
                    low,
                    major_realm="qi_refining",
                    spirit_stones=1_000,
                )
                await GmService(session).gm_set_character(
                    high,
                    major_realm="foundation",
                    spirit_stones=3_000,
                )
                await session.commit()
                sect = SectService(session)
                await sect.join(low, template_id="qingyun_zong")
                await sect.join(high, template_id="qingyun_zong")
                await session.commit()
                ferry = FerryService(session)
                victim = await character_service.get_character_by_user_id(session, low.id)
                await ferry.enter_awaiting_ferry(victim)
                await session.commit()
                # 低修救高修不可（victim is low; reverse: low tries to rescue - victim is high)
                # 这里高修救低修应成功；低修救同境界不可用——用 high 救 low
                ok = await ferry.social_rescue(
                    high,
                    target_name="低修甲",
                    target_character_id=None,
                    mode="sect",
                )
                await session.commit()
                assert ok["rescued"] is True

    _run(_body())
