"""P3 藏经阁：自研功法上供、审核、学习。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.constants.technique import TECHNIQUE_SOURCE_SECT
from app.constants.technique_craft import (
    CARD_MANUAL_ID,
    ERR_CRAFT_LEARN,
    ERR_SCRIPTURE_DONATE,
)
from app.core.config import get_settings
from app.db.models import User
from app.db.models.inventory_item import InventoryItem
from app.db.models.research import PrivateTechnique
from app.db.models.sect import Sect, SectDonationReview, SectMember, SectScriptureEntry
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


async def _founder_sect_with_manual(
    session,
    *,
    email: str,
    name_zh: str,
    sect_name: str,
    specialty: str = "sword",
) -> tuple:
    """Create founder + sect, finalize spell, print one manual. Returns context tuple."""
    founder = await _prepare_researcher(session, email, name_zh)
    user = await session.get(User, founder.user_id)
    assert user is not None
    await GmService(session).gm_set_character(user, spirit_stones=200_000)
    await session.commit()
    await SectService(session).create(
        user,
        name=sect_name,
        motto=None,
        specialty=specialty,
    )
    await session.commit()
    await session.refresh(founder)
    member = (
        await session.execute(
            select(SectMember).where(SectMember.character_id == founder.id)
        )
    ).scalar_one()
    craft_svc = TechniqueCraftService(session)
    tech_id = await _finalize_spell_attack(session, founder, craft_svc)
    craft = get_game_config().research.technique_craft
    founder.cultivation_points = int(craft.print_manual_cost_cultivation) * 4
    await session.commit()
    await session.refresh(founder)
    printed = await craft_svc.print_manual(founder, tech_id)
    await session.commit()
    row = (
        await session.execute(
            select(InventoryItem).where(
                InventoryItem.character_id == founder.id,
                InventoryItem.item_id == CARD_MANUAL_ID,
                InventoryItem.quantity > 0,
            )
        )
    ).scalar_one()
    return founder, user, member, craft_svc, tech_id, printed["snapshot"], str(row.item_uid)


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


def test_scripture_review_reject_returns_manual(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject returns one tech_manual with snapshot meta to the donor."""
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "sect_rev_rej.db") as factory:
            async with factory() as session:
                (
                    founder,
                    user,
                    _member,
                    _craft,
                    _tech_id,
                    snapshot,
                    item_uid,
                ) = await _founder_sect_with_manual(
                    session,
                    email="sectrevrej@test.com",
                    name_zh="审拒甲",
                    sect_name="审拒试炼宗",
                )
                donated = await SectFacilityService(session).scripture_donate(
                    user, item_uid=item_uid
                )
                await session.commit()
                review_id = int(donated["review_id"])

                out = await SectFacilityService(session).review_donation(
                    user, review_id=review_id, approve=False
                )
                await session.commit()
                assert "拒绝" in str(out.get("message") or "")

                review = await session.get(SectDonationReview, review_id)
                assert review is not None
                assert review.status == "rejected"

                returned = (
                    await session.execute(
                        select(InventoryItem).where(
                            InventoryItem.character_id == founder.id,
                            InventoryItem.item_id == CARD_MANUAL_ID,
                            InventoryItem.quantity > 0,
                        )
                    )
                ).scalars().all()
                assert len(returned) == 1
                meta = InventoryService._parse_row_meta(returned[0])
                assert meta.get("manual_kind") == "technique"
                assert meta.get("origin_technique_id") == snapshot["origin_technique_id"]
                assert int(meta.get("author_character_id") or 0) == int(
                    snapshot["author_character_id"]
                )
                assert "payload" in meta and "stats" in meta and "affix_ids" in meta

    _run(_body())


def test_scripture_review_approve_grants_contrib_and_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Approve stocks SectScriptureEntry and pays base donate reward only."""
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "sect_rev_ok.db") as factory:
            async with factory() as session:
                (
                    founder,
                    user,
                    member,
                    _craft,
                    _tech_id,
                    snapshot,
                    item_uid,
                ) = await _founder_sect_with_manual(
                    session,
                    email="sectrevok@test.com",
                    name_zh="审通甲",
                    sect_name="审通试炼宗",
                    specialty="sword",
                )
                contrib_before = int(member.contribution)
                scripture = get_game_config().sects.scripture or {}
                reward = int(scripture.get("donate_reward_contrib") or 0)
                learn_cost = int(scripture.get("learn_cost_contrib") or 0)

                donated = await SectFacilityService(session).scripture_donate(
                    user, item_uid=item_uid
                )
                await session.commit()
                review_id = int(donated["review_id"])

                out = await SectFacilityService(session).review_donation(
                    user, review_id=review_id, approve=True
                )
                await session.commit()
                await session.refresh(member)
                assert "通过" in str(out.get("message") or "")

                origin = str(snapshot["origin_technique_id"])
                entry = (
                    await session.execute(
                        select(SectScriptureEntry).where(
                            SectScriptureEntry.technique_id == origin,
                        )
                    )
                ).scalar_one()
                assert entry.label_zh == snapshot["label_zh"]
                assert entry.origin_technique_id == origin
                assert int(entry.author_character_id or 0) == int(founder.id)
                assert entry.source == "self_research"
                assert int(entry.cost_contribution) == learn_cost
                assert entry.payload_json
                assert entry.stats_json
                assert entry.affix_ids_json
                assert entry.specialty_tag is None

                assert int(member.contribution) == contrib_before + reward

                manuals = (
                    await session.execute(
                        select(InventoryItem).where(
                            InventoryItem.character_id == founder.id,
                            InventoryItem.item_id == CARD_MANUAL_ID,
                            InventoryItem.quantity > 0,
                        )
                    )
                ).scalars().all()
                assert manuals == []

    _run(_body())


def test_scripture_review_approve_replaces_same_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Second approve for same origin updates the single entry snapshot/label."""
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "sect_rev_rep.db") as factory:
            async with factory() as session:
                (
                    founder,
                    user,
                    _member,
                    craft_svc,
                    tech_id,
                    snapshot,
                    item_uid,
                ) = await _founder_sect_with_manual(
                    session,
                    email="sectrevrep@test.com",
                    name_zh="审替甲",
                    sect_name="审替试炼宗",
                )
                first = await SectFacilityService(session).scripture_donate(
                    user, item_uid=item_uid
                )
                await session.commit()
                await SectFacilityService(session).review_donation(
                    user, review_id=int(first["review_id"]), approve=True
                )
                await session.commit()

                private = (
                    await session.execute(
                        select(PrivateTechnique).where(
                            PrivateTechnique.technique_id == tech_id
                        )
                    )
                ).scalar_one()
                private.label_zh = "替换后残篇"
                body = json.loads(private.payload_json or "{}")
                body["label_note"] = "replaced"
                private.payload_json = json.dumps(body, ensure_ascii=False)
                await session.commit()
                await session.refresh(founder)
                printed2 = await craft_svc.print_manual(founder, tech_id)
                await session.commit()
                row2 = (
                    await session.execute(
                        select(InventoryItem).where(
                            InventoryItem.character_id == founder.id,
                            InventoryItem.item_id == CARD_MANUAL_ID,
                            InventoryItem.quantity > 0,
                        )
                    )
                ).scalar_one()
                second = await SectFacilityService(session).scripture_donate(
                    user, item_uid=str(row2.item_uid)
                )
                await session.commit()
                await SectFacilityService(session).review_donation(
                    user, review_id=int(second["review_id"]), approve=True
                )
                await session.commit()

                origin = str(snapshot["origin_technique_id"])
                entries = list(
                    (
                        await session.execute(
                            select(SectScriptureEntry).where(
                                SectScriptureEntry.technique_id == origin,
                            )
                        )
                    ).scalars()
                )
                assert len(entries) == 1
                assert entries[0].label_zh == "替换后残篇"
                stored = json.loads(entries[0].payload_json or "{}")
                assert stored.get("label_note") == "replaced"
                assert printed2["snapshot"]["label_zh"] == "替换后残篇"

    _run(_body())


async def _join_sect_as_member(session, *, sect: Sect, peer) -> SectMember:
    """Attach a second character as outer disciple of an existing player sect."""
    member = SectMember(
        sect_id=sect.id,
        character_id=peer.id,
        role="member",
        rank="outer_disciple",
        contribution=0,
    )
    session.add(member)
    peer.sect_id = sect.id
    await session.flush()
    return member


async def _approve_scripture_entry(session, user, item_uid: str) -> SectScriptureEntry:
    """Donate + approve; return the stocked scripture entry."""
    donated = await SectFacilityService(session).scripture_donate(
        user, item_uid=item_uid
    )
    await session.commit()
    await SectFacilityService(session).review_donation(
        user, review_id=int(donated["review_id"]), approve=True
    )
    await session.commit()
    entry = (
        await session.execute(select(SectScriptureEntry))
    ).scalar_one()
    return entry


def test_scripture_exchange_learns_sect_copy_and_charges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Approved snapshot exchange grants source=sect copy and charges learn_cost."""
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "sect_ex_ok.db") as factory:
            async with factory() as session:
                (
                    founder,
                    founder_user,
                    _f_member,
                    _craft,
                    _tech_id,
                    snapshot,
                    item_uid,
                ) = await _founder_sect_with_manual(
                    session,
                    email="sectexoka@test.com",
                    name_zh="兑学创",
                    sect_name="兑学试炼宗",
                )
                entry = await _approve_scripture_entry(
                    session, founder_user, item_uid
                )
                learn_cost = int(entry.cost_contribution)
                assert learn_cost > 0

                peer = await _prepare_researcher(
                    session, "sectexokb@test.com", "兑学徒"
                )
                peer_user = await session.get(User, peer.user_id)
                assert peer_user is not None
                sect = await session.get(Sect, entry.sect_id)
                assert sect is not None
                peer_member = await _join_sect_as_member(
                    session, sect=sect, peer=peer
                )
                peer.major_realm = str(
                    snapshot.get("major_rank") or peer.major_realm
                )
                await SectFacilityService(session)._apply_contrib(
                    peer_member,
                    delta=learn_cost + 10,
                    reason="test_grant",
                    note_zh="测试加贡献",
                )
                await session.commit()
                await session.refresh(peer_member)
                contrib_before = int(peer_member.contribution)

                listed = await SectFacilityService(session).scripture_list(peer_user)
                listed_entry = next(
                    (
                        e
                        for e in listed["entries"]
                        if e["technique_id"] == entry.technique_id
                    ),
                    None,
                )
                assert listed_entry is not None
                assert listed_entry["has_snapshot"] is True
                assert listed_entry["owned"] is False
                assert listed_entry["origin_technique_id"] == snapshot[
                    "origin_technique_id"
                ]
                assert int(listed_entry["cost_contribution"]) == learn_cost

                out = await SectFacilityService(session).scripture_exchange(
                    peer_user, technique_id=entry.technique_id
                )
                await session.commit()
                await session.refresh(peer_member)

                assert int(peer_member.contribution) == contrib_before - learn_cost
                copy_id = str(out["technique_id"])
                assert copy_id != entry.technique_id

                learned = (
                    await session.execute(
                        select(CharacterTechnique).where(
                            CharacterTechnique.character_id == peer.id,
                            CharacterTechnique.technique_id == copy_id,
                        )
                    )
                ).scalar_one()
                assert learned.source == TECHNIQUE_SOURCE_SECT

                mine = await TechniqueService(session).list_my_techniques(peer)
                copy_item = next((t for t in mine if t["id"] == copy_id), None)
                assert copy_item is not None
                assert copy_item["source"] == "sect"
                assert copy_item["cultivable"] is False

                listed2 = await SectFacilityService(session).scripture_list(peer_user)
                listed2_entry = next(
                    (
                        e
                        for e in listed2["entries"]
                        if e["technique_id"] == entry.technique_id
                    ),
                    None,
                )
                assert listed2_entry is not None
                assert listed2_entry["owned"] is True

    _run(_body())


def test_scripture_exchange_below_rank_no_charge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Below-rank exchange raises and does not deduct contribution."""
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "sect_ex_rank.db") as factory:
            async with factory() as session:
                founder = await _prepare_researcher(
                    session, "sectexranka@test.com", "兑阶创"
                )
                founder.major_realm = "qi_refining"
                await session.commit()
                founder_user = await session.get(User, founder.user_id)
                assert founder_user is not None
                await GmService(session).gm_set_character(
                    founder_user, spirit_stones=200_000
                )
                await session.commit()
                await SectService(session).create(
                    founder_user,
                    name="兑阶试炼宗",
                    motto=None,
                    specialty="sword",
                )
                await session.commit()
                await session.refresh(founder)

                craft_svc = TechniqueCraftService(session)
                tech_id = await _finalize_spell_attack(session, founder, craft_svc)
                craft = get_game_config().research.technique_craft
                founder.cultivation_points = int(craft.print_manual_cost_cultivation) * 4
                await session.commit()
                printed = await craft_svc.print_manual(founder, tech_id)
                await session.commit()
                assert printed["snapshot"]["major_rank"] == "qi_refining"
                row = (
                    await session.execute(
                        select(InventoryItem).where(
                            InventoryItem.character_id == founder.id,
                            InventoryItem.item_id == CARD_MANUAL_ID,
                            InventoryItem.quantity > 0,
                        )
                    )
                ).scalar_one()
                entry = await _approve_scripture_entry(
                    session, founder_user, str(row.item_uid)
                )
                learn_cost = int(entry.cost_contribution)

                peer = await _prepare_researcher(
                    session, "sectexrankb@test.com", "兑阶徒"
                )
                peer_user = await session.get(User, peer.user_id)
                assert peer_user is not None
                sect = await session.get(Sect, entry.sect_id)
                assert sect is not None
                peer_member = await _join_sect_as_member(
                    session, sect=sect, peer=peer
                )
                peer.major_realm = "body_tempering"
                await SectFacilityService(session)._apply_contrib(
                    peer_member,
                    delta=learn_cost + 20,
                    reason="test_grant",
                    note_zh="测试加贡献",
                )
                await session.commit()
                await session.refresh(peer_member)
                contrib_before = int(peer_member.contribution)

                with pytest.raises(AppError) as exc:
                    await SectFacilityService(session).scripture_exchange(
                        peer_user, technique_id=entry.technique_id
                    )
                assert exc.value.code == ERR_CRAFT_LEARN
                assert "境界不足" in str(exc.value.message)
                await session.refresh(peer_member)
                assert int(peer_member.contribution) == contrib_before

                privates = (
                    await session.execute(
                        select(PrivateTechnique).where(
                            PrivateTechnique.character_id == peer.id,
                        )
                    )
                ).scalars().all()
                assert privates == []

    _run(_body())


def test_catalog_exchange_still_placeholder(tmp_path: Path) -> None:
    """YAML catalog exchange stays placeholder and creates no PrivateTechnique."""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "sect_ex_cat.db") as factory:
            async with factory() as session:
                founder = await _prepare_researcher(
                    session, "sectexcat@test.com", "兑目创"
                )
                user = await session.get(User, founder.user_id)
                assert user is not None
                await GmService(session).gm_set_character(
                    user, spirit_stones=200_000
                )
                await session.commit()
                await SectService(session).create(
                    user,
                    name="兑目试炼宗",
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
                catalog = dict(
                    (get_game_config().sects.scripture or {}).get("catalog") or {}
                )
                tid = "basic_breath"
                assert tid in catalog
                cost = int(catalog[tid].get("cost_contribution") or 60)
                await SectFacilityService(session)._apply_contrib(
                    member,
                    delta=cost + 5,
                    reason="test_grant",
                    note_zh="测试加贡献",
                )
                await session.commit()
                await session.refresh(member)
                contrib_before = int(member.contribution)
                privates_before = (
                    await session.execute(
                        select(PrivateTechnique).where(
                            PrivateTechnique.character_id == founder.id,
                        )
                    )
                ).scalars().all()

                out = await SectFacilityService(session).scripture_exchange(
                    user, technique_id=tid
                )
                await session.commit()
                await session.refresh(member)

                assert "占位授予" in str(out.get("message") or "")
                assert out.get("technique_id") == tid
                assert int(member.contribution) == contrib_before - cost
                privates_after = (
                    await session.execute(
                        select(PrivateTechnique).where(
                            PrivateTechnique.character_id == founder.id,
                        )
                    )
                ).scalars().all()
                assert len(privates_after) == len(privates_before)

    _run(_body())
