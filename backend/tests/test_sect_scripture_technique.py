"""P3 藏经阁：自研功法上供、审核、学习。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.constants.technique import TECHNIQUE_SOURCE_SECT
from app.db.models.technique import CharacterTechnique
from app.services.realm_config import get_game_config
from app.services.technique_craft_service import TechniqueCraftService
from app.services.technique_service import TechniqueService
from tests.async_db import open_test_session_factory, run_async as _run
from tests.test_research_technique_finalize import _prepare_researcher
from tests.test_technique_craft import _finalize_spell_attack


def test_scripture_yaml_costs_and_entry_columns() -> None:
    from app.db.models.sect import SectScriptureEntry
    from app.services.realm_config import clear_game_config_cache, get_game_config

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
