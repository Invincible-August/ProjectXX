"""双修时长转化 / 传功差距纯规则单测。"""

from __future__ import annotations

from app.domain.dual_cultivation_rules import (
    duration_conversion_ratio,
    resolve_extract_settlement,
    resolve_mutual_gain,
    resolve_transfer_settlement,
)


def test_duration_conversion_curve() -> None:
    assert abs(duration_conversion_ratio(1) - 0.01) < 1e-9
    assert abs(duration_conversion_ratio(100) - 1.0) < 1e-9
    assert abs(duration_conversion_ratio(200) - 1.5) < 1e-9


def test_transfer_equal_cultivation_scales_with_duration() -> None:
    one = resolve_transfer_settlement(
        base_transfer=100,
        duration_sec=1,
        yield_mult=1.0,
        giver_cultivation=1000,
        receiver_cultivation=1000,
    )
    assert one["giver_cost"] == 100
    assert one["receiver_delta"] == 1

    hundred = resolve_transfer_settlement(
        base_transfer=100,
        duration_sec=100,
        yield_mult=1.0,
        giver_cultivation=1000,
        receiver_cultivation=1000,
    )
    assert hundred["giver_cost"] == 100
    assert hundred["receiver_delta"] == 100

    two_hundred = resolve_transfer_settlement(
        base_transfer=100,
        duration_sec=200,
        yield_mult=1.0,
        giver_cultivation=1000,
        receiver_cultivation=1000,
    )
    assert two_hundred["giver_cost"] == 100
    assert two_hundred["receiver_delta"] == 150


def test_transfer_giver_stronger_can_go_negative() -> None:
    # gap = (5000-0)/500 = 10；duration_ratio@100=1 → conversion=-9
    result = resolve_transfer_settlement(
        base_transfer=100,
        duration_sec=100,
        yield_mult=1.0,
        giver_cultivation=5000,
        receiver_cultivation=0,
        gap_scale=500,
    )
    assert result["giver_cost"] == 100
    assert result["receiver_delta"] < 0


def test_transfer_receiver_stronger_inflates_giver_cost() -> None:
    result = resolve_transfer_settlement(
        base_transfer=100,
        duration_sec=50,
        yield_mult=1.0,
        giver_cultivation=0,
        receiver_cultivation=5000,
        gap_scale=500,
    )
    assert result["giver_cost"] > 100
    assert result["receiver_delta"] >= 100


def test_mutual_gain_gap_penalty() -> None:
    close = resolve_mutual_gain(
        base_yield=50,
        duration_sec=100,
        yield_mult=1.0,
        cultivation_a=1000,
        cultivation_b=1000,
    )
    far = resolve_mutual_gain(
        base_yield=50,
        duration_sec=100,
        yield_mult=1.0,
        cultivation_a=10000,
        cultivation_b=0,
        gap_scale=500,
    )
    assert close["gain_each"] > far["gain_each"]


def test_extract_initial_conversion_by_gap() -> None:
    """被索取过低→初始0；索取方过低→初始为负；相当→1。"""
    target_low = resolve_extract_settlement(
        base_extract=100,
        duration_sec=100,
        yield_mult=1.0,
        extractor_cultivation=5000,
        target_cultivation=0,
        gap_scale=500,
    )
    assert target_low["initial_conversion"] == 0.0
    # duration_ratio(100)=1 → conversion = 0 + 0 = 0
    assert target_low["extractor_delta"] == 0
    assert target_low["target_cost"] == 100

    extractor_low = resolve_extract_settlement(
        base_extract=100,
        duration_sec=100,
        yield_mult=1.0,
        extractor_cultivation=0,
        target_cultivation=5000,
        gap_scale=500,
    )
    assert extractor_low["initial_conversion"] < 0
    assert extractor_low["extractor_delta"] < 0

    equal = resolve_extract_settlement(
        base_extract=100,
        duration_sec=100,
        yield_mult=1.0,
        extractor_cultivation=1000,
        target_cultivation=1000,
    )
    assert equal["initial_conversion"] == 1.0
    assert equal["extractor_delta"] == 100
