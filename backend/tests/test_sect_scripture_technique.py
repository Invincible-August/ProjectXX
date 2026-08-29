"""P3 藏经阁：自研功法上供、审核、学习。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.constants.technique import TECHNIQUE_SOURCE_SECT
from app.constants.technique_craft import CARD_MANUAL_ID, ERR_SCRIPTURE_DONATE
from app.core.config import get_settings
from app.db.models import User
from app.db.models.inventory_item import InventoryItem
from app.db.models.sect import SectDonationReview, SectMember
from app.db.models.technique import CharacterTechnique
from app.schemas.common import AppError
from app.services.gm_service import GmService
from app.services.inventory_service import InventoryService
from app.services.realm_config import clear_game_config_cache, get_game_config
from app.services.sect_facility_service import SectFacilityService
from app.services.sect_service import SectService
from app.services.technique_craft_service import TechniqueCraftService
from app.services.technique_service import TechniqueService
from tests.async_db import open_test_session_factory, run_async as _run
from tests.test_research_technique_finalize import _prepare_researcher
from tests.test_technique_craft import _finalize_spell_attack, _grant_manual


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


def test_scripture_yaml_costs_and_entry_columns() -> None:
    from app.db.models.sect import SectScriptureEntry

    clear_game_config_cache()
    sc = get_game_config().sects.scripture
    assert int(sc.get("donate_reward_contrib") or 0) == 40
    assert int(sc.get("learn_cost_contrib") or 0) == 60
    assert hasattr(SectScriptureEntry, "origin_technique_id")
    assert hasattr(SectScriptureEntry, "payload_json")
    assert hasattr(SectScriptureEntry, "cost_contribution")


def test_learn_from_manual_meta_source_sect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """learn_from_manual_meta(source=sect) stamps CharacterTechnique.source sect."""
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "sect_learn.db") as factory:
            async with factory() as session:
                author = await _prepare_researcher(session, "sectlearna@test.com", "宗学甲")
                learner = await _prepare_researcher(session, "sectlearnb@test.com", "宗学乙")
                svc = TechniqueCraftService(session)
                tech_id = await _finalize_spell_attack(session, author, svc)
                craft = get_game_config().research.technique_craft
                author.cultivation_points = int(craft.print_manual_cost_cultivation) * 2
                await session.commit()
                printed = await svc.print_manual(author, tech_id)
                await session.commit()
                snapshot = printed["snapshot"]
                learner.major_realm = str(snapshot.get("major_rank") or "qi_refining")
                await session.commit()

                out = await svc.learn_from_manual_meta(
                    learner, snapshot, source=TECHNIQUE_SOURCE_SECT
                )
                await session.commit()
                copy_id = str(out["technique_id"])

                learned = (
                    await session.execute(
                        select(CharacterTechnique).where(
                            CharacterTechnique.character_id == learner.id,
                            CharacterTechnique.technique_id == copy_id,
                        )
                    )
                ).scalar_one()
                assert learned.source == "sect"

                listed = await TechniqueService(session).list_my_techniques(learner)
                copy_item = next((t for t in listed if t["id"] == copy_id), None)
                assert copy_item is not None
                assert copy_item["source"] == "sect"
                assert copy_item["cultivable"] is False

    _run(_body())


def test_scripture_donate_consumes_book_and_opens_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Founder prints a manual, donates by item_uid: book gone, pending review, no contrib."""
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "sect_donate_ok.db") as factory:
            async with factory() as session:
                founder = await _prepare_researcher(
                    session, "sectdonatea@test.com", "上缴甲"
                )
                user = await session.get(User, founder.user_id)
                assert user is not None
                await GmService(session).gm_set_character(
                    user, spirit_stones=200_000
                )
                await session.commit()
                await SectService(session).create(
                    user,
                    name="上缴试炼宗",
                    motto=None,
                    specialty="sword",
                )
                await session.commit()
                await session.refresh(founder)

                member = (
                    await session.execute(
                        select(SectMember).where(
                            SectMember.character_id == founder.id
                        )
                    )
                ).scalar_one()
                contrib_before = int(member.contribution)

                craft_svc = TechniqueCraftService(session)
                tech_id = await _finalize_spell_attack(session, founder, craft_svc)
                craft = get_game_config().research.technique_craft
                founder.cultivation_points = int(craft.print_manual_cost_cultivation) * 2
                await session.commit()
                await session.refresh(founder)
                printed = await craft_svc.print_manual(founder, tech_id)
                await session.commit()
                snapshot = printed["snapshot"]

                row = (
                    await session.execute(
                        select(InventoryItem).where(
                            InventoryItem.character_id == founder.id,
                            InventoryItem.item_id == CARD_MANUAL_ID,
                            InventoryItem.quantity > 0,
                        )
                    )
                ).scalar_one()
                item_uid = str(row.item_uid)

                out = await SectFacilityService(session).scripture_donate(
                    user, item_uid=item_uid
                )
                await session.commit()
                await session.refresh(member)

                assert "审核" in str(out.get("message") or "")
                assert int(member.contribution) == contrib_before

                remaining = (
                    await session.execute(
                        select(InventoryItem).where(
                            InventoryItem.character_id == founder.id,
                            InventoryItem.item_id == CARD_MANUAL_ID,
                            InventoryItem.quantity > 0,
                        )
                    )
                ).scalars().all()
                assert remaining == []

                reviews = list(
                    (
                        await session.execute(
                            select(SectDonationReview).where(
                                SectDonationReview.kind == "scripture",
                                SectDonationReview.status == "pending",
                            )
                        )
                    ).scalars()
                )
                assert len(reviews) == 1
                assert int(reviews[0].character_id) == int(founder.id)
                payload = json.loads(reviews[0].payload_json or "{}")
                assert payload.get("origin_technique_id") == snapshot["origin_technique_id"]
                assert payload.get("manual_kind") == "technique"
                assert int(payload.get("author_character_id") or 0) == int(founder.id)
                assert "payload" in payload and "stats" in payload

                with pytest.raises(AppError) as exc:
                    await SectFacilityService(session).scripture_donate(
                        user, item_uid=item_uid
                    )
                assert exc.value.code == 40000

    _run(_body())


def test_scripture_donate_rejects_non_author(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-author holding a printed book cannot donate; book stays."""
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "sect_donate_na.db") as factory:
            async with factory() as session:
                founder = await _prepare_researcher(
                    session, "sectdonatenaf@test.com", "上缴创"
                )
                peer = await _prepare_researcher(
                    session, "sectdonatenap@test.com", "上缴徒"
                )
                founder_user = await session.get(User, founder.user_id)
                peer_user = await session.get(User, peer.user_id)
                assert founder_user is not None and peer_user is not None
                await GmService(session).gm_set_character(
                    founder_user, spirit_stones=200_000
                )
                await session.commit()
                await SectService(session).create(
                    founder_user,
                    name="非作者试炼宗",
                    motto=None,
                    specialty="sword",
                )
                await session.commit()
                await session.refresh(founder)

                from app.db.models.sect import Sect

                sect = (
                    await session.execute(
                        select(Sect).where(Sect.name == "非作者试炼宗")
                    )
                ).scalar_one()
                session.add(
                    SectMember(
                        sect_id=sect.id,
                        character_id=peer.id,
                        role="member",
                        rank="outer_disciple",
                        contribution=0,
                    )
                )
                peer.sect_id = sect.id
                await session.commit()

                craft_svc = TechniqueCraftService(session)
                tech_id = await _finalize_spell_attack(session, founder, craft_svc)
                craft = get_game_config().research.technique_craft
                founder.cultivation_points = int(craft.print_manual_cost_cultivation) * 2
                await session.commit()
                await session.refresh(founder)
                printed = await craft_svc.print_manual(founder, tech_id)
                await session.commit()
                snapshot = printed["snapshot"]

                author_row = (
                    await session.execute(
                        select(InventoryItem).where(
                            InventoryItem.character_id == founder.id,
                            InventoryItem.item_id == CARD_MANUAL_ID,
                            InventoryItem.quantity > 0,
                        )
                    )
                ).scalar_one()
                await InventoryService(session).remove_one_by_uid(
                    founder.id, str(author_row.item_uid)
                )
                peer_uid = await _grant_manual(session, peer.id, snapshot)
                await session.commit()

                with pytest.raises(AppError) as exc:
                    await SectFacilityService(session).scripture_donate(
                        peer_user, item_uid=peer_uid
                    )
                assert exc.value.code == ERR_SCRIPTURE_DONATE
                assert "仅创作者可上缴" in str(exc.value.message)

                still = (
                    await session.execute(
                        select(InventoryItem).where(
                            InventoryItem.item_uid == peer_uid,
                            InventoryItem.quantity > 0,
                        )
                    )
                ).scalar_one_or_none()
                assert still is not None

    _run(_body())
