"""结构化表格 ↔ 域 JSON 往返（realms / idle / dice）。"""

from __future__ import annotations

from app.config_source.yaml_source import get_shared_yaml_source
from app.services.admin_sheet_codec import (
    payload_to_sheets,
    sheets_to_payload,
    supports_structured_sheets,
)


def test_supports_balance_sheet_domains() -> None:
    """高危三域支持表格双写。"""
    assert supports_structured_sheets("realms")
    assert supports_structured_sheets("idle")
    assert supports_structured_sheets("dice")
    assert not supports_structured_sheets("pets")


def test_idle_sheet_roundtrip() -> None:
    """挂机 YAML → 表格 → JSON 关键字段不丢。"""
    raw = get_shared_yaml_source().load_raw("idle.yaml", copy=True)
    sheets = payload_to_sheets("idle", raw)
    rebuilt = sheets_to_payload("idle", sheets)
    assert rebuilt["tick_seconds"] == raw["tick_seconds"]
    assert rebuilt["gain_per_tick_by_realm"]["spirit"]["foundation"] == (
        raw["gain_per_tick_by_realm"]["spirit"]["foundation"]
    )
    assert rebuilt["directions"]["body"]["enabled"] is True


def test_dice_realm_bounds_roundtrip() -> None:
    """修为骰境界上下限往返。"""
    raw = get_shared_yaml_source().load_raw("dice.yaml", copy=True)
    sheets = payload_to_sheets("dice", raw)
    rebuilt = sheets_to_payload("dice", sheets)
    assert rebuilt["realm_bounds"]["body_tempering"]["10"] == (
        raw["realm_bounds"]["body_tempering"][10]
        if 10 in raw["realm_bounds"]["body_tempering"]
        else raw["realm_bounds"]["body_tempering"]["10"]
    )
    assert rebuilt["fallback_bounds"]["min"] == raw["fallback_bounds"]["min"]


def test_realms_sheets_rebuild_stages() -> None:
    """境界大境 + 小层组装。"""
    raw = get_shared_yaml_source().load_raw("realms.yaml", copy=True)
    sheets = payload_to_sheets("realms", raw)
    rebuilt = sheets_to_payload("realms", sheets)
    assert "body_tempering" in rebuilt["major_realms"]
    assert rebuilt["major_realms"]["body_tempering"]["name"] == "锻体"
    assert len(rebuilt["major_realms"]["body_tempering"]["stages"]) == len(
        raw["major_realms"]["body_tempering"]["stages"],
    )
