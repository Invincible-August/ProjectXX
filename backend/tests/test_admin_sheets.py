"""结构化表格 ↔ 域 JSON 往返（realms / idle / dice）。"""

from __future__ import annotations

from app.config_source.yaml_source import get_shared_yaml_source
from app.services.admin_sheet_codec import (
    payload_to_sheets,
    sheets_to_payload,
    supports_structured_sheets,
)


def test_supports_balance_sheet_domains() -> None:
    """高危三域 + 大道目录支持表格双写。"""
    assert supports_structured_sheets("realms")
    assert supports_structured_sheets("idle")
    assert supports_structured_sheets("dice")
    assert supports_structured_sheets("dao")
    assert supports_structured_sheets("dao_restraint")
    assert not supports_structured_sheets("pets")


def test_dao_sheet_roundtrip_and_delete() -> None:
    """道目录 YAML → 网格 → JSON；删行后 entries 变短（整段替换语义）。"""
    from app.config_source.merge import merge_domain_overlay

    raw = get_shared_yaml_source().load_raw("dao.yaml", copy=True)
    sheets = payload_to_sheets("dao", raw)
    assert sheets[0]["sheet_id"] == "entries"
    assert len(sheets[0]["rows"]) == len(raw["entries"])

    # 删掉一行再写回
    rows = [r for r in sheets[0]["rows"] if r["dao_id"] != "dao_void"]
    rebuilt = sheets_to_payload("dao", [{"sheet_id": "entries", "rows": rows}])
    assert "dao_void" not in rebuilt["entries"]
    assert "dao_void" not in rebuilt["labels"]
    assert "dao_flame" in rebuilt["entries"]
    assert rebuilt["labels"]["dao_flame"] == rebuilt["entries"]["dao_flame"]["label_zh"]

    # 覆盖合并后 YAML 底表里的 dao_void 也应消失
    merged = merge_domain_overlay("dao", raw, rebuilt)
    assert "dao_void" not in merged["entries"]
    assert "open" in merged  # 其它键仍来自 YAML


def test_dao_restraint_sheet_roundtrip() -> None:
    """克制边往返。"""
    raw = get_shared_yaml_source().load_raw("dao_restraint.yaml", copy=True)
    sheets = payload_to_sheets("dao_restraint", raw)
    rebuilt = sheets_to_payload("dao_restraint", sheets)
    assert rebuilt["edges"][0]["attacker"] == raw["edges"][0]["attacker"]
    assert float(rebuilt["edges"][0]["damage_mul"]) == float(raw["edges"][0]["damage_mul"])


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
