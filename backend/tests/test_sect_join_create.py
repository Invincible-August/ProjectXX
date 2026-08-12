"""M7 L1 宗门：拜入 / 自建 / 贡献轮回归零。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import SectMember, User
from app.db.models.sect import SectContributionLedger
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.gm_service import GmService
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
    monkeypatch.setattr(settings, "pets_enabled", True)
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


def test_sect_join_npc_and_create(tmp_path: Path) -> None:
    """散修可拜入 NPC；另一账号有钱可自建。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "sect_join.db") as factory:
            async with factory() as session:
                user_a = await _register_char(session, "sect_a@example.com", "宗测甲")
                # 青云宗门槛 qi_refining；GM 抬境界
                await GmService(session).gm_set_character(
                    user_a,
                    major_realm="qi_refining",
                    spirit_stones=10_000,
                )
                await session.commit()

                svc = SectService(session)
                npc = await svc.list_npc(user_a)
                assert any(i["template_id"] == "qingyun_zong" for i in npc["items"])

                joined = await svc.join(user_a, template_id="qingyun_zong")
                await session.commit()
                assert joined["sect"]["in_sect"] is True
                assert joined["sect"]["name"]
                assert int(joined["sect"]["contrib"]) >= 10

                # 不可重复拜入
                with pytest.raises(AppError) as exc:
                    await svc.join(user_a, template_id="qingyun_zong")
                assert exc.value.code == 40101

                # 自建：另一账号
                user_b = await _register_char(session, "sect_b@example.com", "宗测乙")
                await GmService(session).gm_set_character(
                    user_b,
                    spirit_stones=200_000,
                )
                await session.commit()
                created = await svc.create(
                    user_b,
                    name="试炼小宗",
                    motto="有钱即可",
                )
                await session.commit()
                assert created["sect"]["in_sect"] is True
                assert created["sect"]["role"] == "founder"
                assert created["sect"]["role_label_zh"] == "祖师"

                # 灵石不足建宗
                user_c = await _register_char(session, "sect_c@example.com", "宗测丙")
                await GmService(session).gm_set_character(user_c, spirit_stones=10)
                await session.commit()
                with pytest.raises(AppError) as exc2:
                    await svc.create(user_c, name="穷宗", motto=None)
                assert exc2.value.code == 40102

    _run(_body())


def test_sect_quest_and_contrib_zero(tmp_path: Path) -> None:
    """接交任务涨贡献；轮回归零钩子清贡献。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "sect_quest.db") as factory:
            async with factory() as session:
                user = await _register_char(session, "sect_q@example.com", "宗测丁")
                await GmService(session).gm_set_character(
                    user,
                    major_realm="qi_refining",
                    spirit_stones=5_000,
                )
                await session.commit()
                svc = SectService(session)
                await svc.join(user, template_id="qingyun_zong")
                await session.commit()

                await svc.accept_quest(
                    user,
                    quest_id="daily_patrol",
                    assignee="body",
                )
                await session.commit()
                done = await svc.complete_quest(
                    user,
                    quest_id="daily_patrol",
                    assignee="body",
                )
                await session.commit()
                assert int(done["reward_contribution"]) == 30
                assert int(done["sect"]["contrib"]) >= 40

                character = await character_service.get_character_by_user_id(
                    session,
                    user.id,
                )
                member = (
                    await session.execute(
                        select(SectMember).where(
                            SectMember.character_id == character.id,
                        ),
                    )
                ).scalar_one()
                before = int(member.contribution)
                assert before > 0

                zeroed = await svc.zero_contribution_on_reincarnation(character.id)
                await session.commit()
                assert zeroed["zeroed"] is True
                assert zeroed["before"] == before
                await session.refresh(member)
                assert int(member.contribution) == 0

                ledgers = (
                    await session.execute(
                        select(SectContributionLedger).where(
                            SectContributionLedger.character_id == character.id,
                            SectContributionLedger.reason == "reincarnation_zero",
                        ),
                    )
                ).scalars().all()
                assert len(ledgers) >= 1

    _run(_body())


def test_sect_pet_exchange_whitelist(tmp_path: Path) -> None:
    """白名单可兑；非法物种拒绝。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "sect_pet.db") as factory:
            async with factory() as session:
                user = await _register_char(session, "sect_p@example.com", "宗测戊")
                # 金丹档开兑宠功能（NPC 等效）
                await GmService(session).gm_set_character(
                    user,
                    force_jindan=True,
                    spirit_stones=5_000,
                )
                await session.commit()
                svc = SectService(session)
                await svc.join(user, template_id="lingshou_zong")
                await session.commit()

                # 灌贡献
                character = await character_service.get_character_by_user_id(
                    session,
                    user.id,
                )
                member = (
                    await session.execute(
                        select(SectMember).where(
                            SectMember.character_id == character.id,
                        ),
                    )
                ).scalar_one()
                member.contribution = 1000
                await session.commit()

                with pytest.raises(AppError) as exc:
                    await svc.exchange_pet(user, species_id="not_a_real_pet")
                assert "白名单" in exc.value.message or "未知" in exc.value.message

                ok = await svc.exchange_pet(user, species_id="test_pet_fox")
                await session.commit()
                assert ok["pet"]["species_id"] == "test_pet_fox"
                assert int(ok["sect"]["contrib"]) == 1000 - 500

    _run(_body())
