"""P3 藏经阁：自研功法上供、审核、学习。"""

from __future__ import annotations


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
