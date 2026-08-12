"""M7-V+ 宗门组织：职位申请/任命/唯一/当日锁。"""

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
from app.services.gm_service import GmService
from app.services.realm_config import clear_game_config_cache, get_game_config
from app.services.sect_org_service import SectOrgService
from app.services.sect_service import SectService
from app.domain.sect_org_rules import (
    can_appoint,
    can_self_apply_rank,
    can_upgrade_sect_grade,
    unique_rank_occupied,
)
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
        CreateCharacterRequest(name=name),
    )
    await session.commit()
    return user


def test_sect_org_rules_unit() -> None:
    """纯规则：自升门槛、任命权、唯一职位、升等设施门槛。"""
    ranks = get_game_config().sects.disciple_ranks
    grades = get_game_config().sects.sect_grades

    ok, _ = can_self_apply_rank(
        current_rank="laborer",
        target_rank="outer_disciple",
        contribution=50,
        disciple_ranks=ranks,
    )
    assert ok is True

    ok, reason = can_self_apply_rank(
        current_rank="laborer",
        target_rank="outer_disciple",
        contribution=10,
        disciple_ranks=ranks,
    )
    assert ok is False
    assert reason and "贡献" in reason

    ok, _ = can_appoint(
        actor_rank="founder",
        target_rank="leader",
        disciple_ranks=ranks,
    )
    assert ok is True

    ok, _ = can_appoint(
        actor_rank="outer_elder",
        target_rank="leader",
        disciple_ranks=ranks,
    )
    assert ok is False

    assert unique_rank_occupied(
        target_rank="leader",
        existing_ranks=["leader", "outer_disciple"],
        disciple_ranks=ranks,
    )

    ok, reason, nxt = can_upgrade_sect_grade(
        current_grade="hut",
        facility_levels={"quest_hall": 1, "council_hall": 1},
        sect_grades=grades,
        is_npc=False,
    )
    assert ok is False
    assert nxt == "mountain_gate"

    ok, _, nxt = can_upgrade_sect_grade(
        current_grade="hut",
        facility_levels={"quest_hall": 2, "council_hall": 2},
        sect_grades=grades,
        is_npc=False,
    )
    assert ok is True
    assert nxt == "mountain_gate"

    ok, reason, _ = can_upgrade_sect_grade(
        current_grade="hut",
        facility_levels={"quest_hall": 99, "council_hall": 99},
        sect_grades=grades,
        is_npc=True,
    )
    assert ok is False
    assert reason and "NPC" in reason


def test_sect_create_specialty_and_appoint(tmp_path: Path) -> None:
    """建宗须专精；创派可任命掌门；当日再任命锁。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "sect_org.db") as factory:
            async with factory() as session:
                founder = await _register_char(session, "org_f@example.com", "创派甲")
                await GmService(session).gm_set_character(
                    founder,
                    spirit_stones=200_000,
                )
                await session.commit()

                svc = SectService(session)
                with pytest.raises(AppError):
                    await svc.create(founder, name="无专精宗", motto=None, specialty=None)

                created = await svc.create(
                    founder,
                    name="试炼剑宗",
                    motto="剑心通明",
                    specialty="sword",
                )
                await session.commit()
                assert created["sect"]["rank"] == "founder"
                assert created["sect"]["role_label_zh"] == "创派祖师"

                org = SectOrgService(session)
                overview = await org.overview(founder)
                assert overview["grade"] == "hut"
                assert overview["specialty"] == "sword"
                assert any(f["facility_id"] == "council_hall" for f in overview["facilities"])

                peer = await _register_char(session, "org_p@example.com", "门众乙")
                await GmService(session).gm_set_character(
                    peer,
                    major_realm="qi_refining",
                    spirit_stones=10_000,
                )
                await session.commit()

                from app.db.models import Character
                from app.db.models.sect import Sect, SectMember

                # 手动拉乙入宗
                p_char = (
                    await session.execute(
                        select(Character).where(Character.name == "门众乙"),
                    )
                ).scalar_one()
                sect = (
                    await session.execute(select(Sect).where(Sect.name == "试炼剑宗"))
                ).scalar_one()
                self_mem = SectMember(
                    sect_id=sect.id,
                    character_id=p_char.id,
                    role="member",
                    rank="outer_disciple",
                    contribution=100,
                )
                session.add(self_mem)
                p_char.sect_id = sect.id
                await session.commit()

                appointed = await org.appoint_rank(
                    founder,
                    target_character_id=p_char.id,
                    target_rank="inner_deacon",
                )
                assert appointed["rank"] == "inner_deacon"
                # 当日再任命应锁
                with pytest.raises(AppError) as exc2:
                    await org.appoint_rank(
                        founder,
                        target_character_id=p_char.id,
                        target_rank="inner_elder",
                    )
                assert "今日" in (exc2.value.message or "")

                # 俸禄
                sal = await org.claim_salary(founder)
                assert sal["amount"] > 0
                with pytest.raises(AppError):
                    await org.claim_salary(founder)

                # 战事占位
                with pytest.raises(AppError) as war_exc:
                    await org.start_war_stub(founder, war_kind="sect_war")
                assert war_exc.value.code == 40110

    _run(_body())


def test_sect_grade_facility_upgrade(tmp_path: Path) -> None:
    """设施升级与升宗门等级闭环。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "sect_grade.db") as factory:
            async with factory() as session:
                user = await _register_char(session, "grade@example.com", "升等丙")
                await GmService(session).gm_set_character(
                    user,
                    spirit_stones=500_000,
                )
                await session.commit()
                svc = SectService(session)
                await svc.create(
                    user,
                    name="升等小宗",
                    motto=None,
                    specialty="alchemy",
                )
                await session.commit()
                org = SectOrgService(session)
                # 灌贡献
                from app.db.models.sect import SectMember

                member = (
                    await session.execute(select(SectMember))
                ).scalars().first()
                assert member is not None
                member.contribution = 50_000
                # 灌宗门灵石
                from app.db.models.sect import Sect

                sect = (await session.execute(select(Sect))).scalars().first()
                assert sect is not None
                sect.spirit_stone_pool = 100_000
                await session.commit()

                up1 = await org.upgrade_facility(user, facility_id="quest_hall")
                assert up1["level"] == 2
                up2 = await org.upgrade_facility(user, facility_id="council_hall")
                assert up2["level"] == 2
                graded = await org.upgrade_grade(user)
                assert graded["grade"] == "mountain_gate"

    _run(_body())
