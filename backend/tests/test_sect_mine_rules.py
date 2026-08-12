"""矿脉名额/速率与阵法属性规则单测。"""

from __future__ import annotations

from app.domain.sect_org_rules import mine_max_miners, mine_pool_rate_per_hour


def test_mine_max_miners_scales_with_grade_and_facility() -> None:
    """采矿名额随矿脉等级与宗门等级上升。"""
    cfg = {
        "max_miners_base": 2,
        "max_miners_per_facility_level": 1,
        "max_miners_per_grade_order": 1,
    }
    assert mine_max_miners(grade_order=1, facility_level=0, mine_yield=cfg) == 3
    assert mine_max_miners(grade_order=2, facility_level=3, mine_yield=cfg) == 7


def test_mine_pool_rate_boosts_with_miners() -> None:
    """采矿席位提高宗门入库速率。"""
    cfg = {
        "base_pool_per_hour": 100,
        "per_grade_order": 0,
        "per_facility_level": 0,
        "miner_pool_bonus_pct": 0.1,
    }
    base = mine_pool_rate_per_hour(
        grade_order=1,
        facility_level=0,
        miner_count=0,
        mine_yield=cfg,
    )
    boosted = mine_pool_rate_per_hour(
        grade_order=1,
        facility_level=0,
        miner_count=2,
        mine_yield=cfg,
    )
    assert base == 100.0
    assert boosted == 120.0
