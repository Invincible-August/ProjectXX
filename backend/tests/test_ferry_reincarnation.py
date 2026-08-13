"""待引渡与轮回测试（M5 E5）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.models import User
from app.db.models.constitution import ConstitutionItem
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.services import auth_service, character_service
from app.services.ferry_service import FerryService
from app.services.realm_config import clear_game_config_cache
from app.services.reincarnation_service import ReincarnationService
from tests.async_db import open_test_session_factory, run_async as _run


@pytest.fixture(autouse=True)
def _cfg(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    clear_game_config_cache()
    yield
    clear_game_config_cache()


async def _prepare(session, email: str, name: str) -> User:
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


def test_self_rescue_and_reincarnation_keeps_constitution(tmp_path: Path) -> None:
    """自救回 normal；再陨落后轮回保留体质、境界回锻体一层。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "ferry.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "ferry@example.com", "引渡者")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.major_realm = "yuanying"
                character.realm_stage = 4
                character.realm_stage_label = "perfection"
                character.spirit_stones = 5000
                # 体质行：轮回后应仍在
                session.add(
                    ConstitutionItem(
                        character_id=character.id,
                        def_id="test_constitution",
                        quality="mortal",
                        grade="mortal",
                        kind="body",
                    ),
                )
                await session.commit()

                ferry = FerryService(session)
                await ferry.enter_awaiting_ferry(character)
                await session.commit()
                assert character.status == "awaiting_ferry"

                rescued = await ferry.self_rescue(user)
                await session.commit()
                assert rescued["rescued"] is True
                assert character.status == "normal"

                await ferry.enter_awaiting_ferry(character)
                await session.commit()
                result = await ferry.enter_reincarnation(user)
                await session.commit()
                assert result["to_major"] == "body_tempering"
                assert character.realm_stage == 1
                assert character.reincarnation_count == 1
                assert character.status == "reincarnating"

                items = (
                    await session.execute(
                        select(ConstitutionItem).where(
                            ConstitutionItem.character_id == character.id,
                            ConstitutionItem.def_id == "test_constitution",
                        ),
                    )
                ).scalars().all()
                assert len(items) == 1

                newborn = await ReincarnationService(session).complete_newborn(
                    user,
                    spirit_root_ids=["thunder_root"],
                    legacy_ids=["memory_fragment_minor"],
                    constitution_path="sturdy_body",
                )
                await session.commit()
                assert newborn["completed"] is True
                assert character.status == "normal"
                assert "thunder_root" in (character.spirit_root_tags_json or "")

    _run(_body())


def test_altar_reincarnation(tmp_path: Path) -> None:
    """祭坛主动轮回扣石并重置。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "altar.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "altar@example.com", "祭坛者")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.major_realm = "huashen"
                character.peak_major_realm = "huashen"
                character.realm_stage = 1
                character.realm_stage_label = "early"
                character.spirit_stones = 5000
                await session.commit()
                result = await ReincarnationService(session).altar(user)
                await session.commit()
                assert result["path"] == "altar"
                assert character.major_realm == "body_tempering"
                assert character.status == "reincarnating"
                assert result.get("needs_newborn_setup") is True

                # 商店：扣轮回点换灵石
                character.reincarnation_points = 20
                await session.commit()
                shop = await ReincarnationService(session).shop_buy(
                    user,
                    item_id="spirit_stones_pack_small",
                )
                await session.commit()
                assert shop["reincarnation_points"] == 15
                assert character.spirit_stones >= 200

                done = await ReincarnationService(session).complete_newborn(
                    user,
                    spirit_root_ids=["fire_root"],
                    legacy_ids=[],
                    constitution_path=None,
                )
                await session.commit()
                assert done["completed"] is True
                assert character.status == "normal"

    _run(_body())


def test_altar_blocked_below_huashen(tmp_path: Path) -> None:
    """化神期以下祭坛主动轮回 → 40068。"""
    from app.schemas.common import AppError

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "altar_gate.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "altar_low@example.com", "未化神者")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.major_realm = "yuanying"
                character.peak_major_realm = "yuanying"
                character.spirit_stones = 5000
                await session.commit()
                preview = await ReincarnationService(session).preview(user, path="altar")
                assert preview["can_altar"] is False
                assert "化神" in str(preview.get("altar_block_reason") or "")
                with pytest.raises(AppError) as exc:
                    await ReincarnationService(session).altar(user)
                assert exc.value.code == 40068

    _run(_body())


def test_ferry_rescue_targets_universal_and_kin(tmp_path: Path) -> None:
    """普渡名单仅道友；亲友名单含道友。"""
    from app.services.friend_service import FriendService
    from app.services.gm_service import GmService

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "ferry_targets.db") as factory:
            async with factory() as session:
                a = await _prepare(session, "rt_a@example.com", "救甲")
                b = await _prepare(session, "rt_b@example.com", "救乙")
                await GmService(session).gm_set_character(a, spirit_stones=5000)
                await session.commit()
                friends = FriendService(session)
                applied = await friends.apply(a, target_character_id=None, target_name="救乙")
                await session.commit()
                await friends.accept(b, int(applied["friendship_id"]))
                await session.commit()
                bch = await character_service.get_character_by_user_id(session, b.id)
                assert bch is not None
                ferry = FerryService(session)
                await ferry.enter_awaiting_ferry(bch)
                await session.commit()

                universal = await ferry.list_rescue_targets(a, category="universal")
                assert universal["category"] == "universal"
                assert len(universal["items"]) == 1
                assert universal["items"][0]["name"] == "救乙"
                assert universal["items"][0]["rescue_mode"] == "friend"

                kin = await ferry.list_rescue_targets(a, category="kin")
                assert kin["category"] == "kin"
                assert any(x["name"] == "救乙" for x in kin["items"])
                assert kin["items"][0]["rescue_mode"] == "kin"

                rescued = await ferry.social_rescue(
                    a,
                    target_character_id=bch.id,
                    target_name=None,
                    mode="kin",
                )
                await session.commit()
                assert rescued["rescued"] is True
                await session.refresh(bch)
                assert bch.status == "normal"

    _run(_body())
