"""
四象环境 / 天气战斗载荷与战报 enrichment（M3-D07）。

职责边界（与 formation_rules 解耦）:
    - ``formation_rules``：对抗骰点、覆盖规则、效果面板 atk/hp；
    - 本模块：catalog 查询、combat 乘区合并、命中/伤害乘区钩子、事件中文 enrichment。

引擎只吃 ``FormationsConfig.catalogs_plain()`` 产出的纯 dict（对齐嘲讽 snapshot）。

纯度纪律（写死）：本模块不得 import FastAPI / SQLAlchemy / pydantic。
"""

from __future__ import annotations

from typing import Any

from app.domain.formation_rules import resolved_content_id_for_side

# 环境/天气 combat 缺省乘区（全部 1.0 = 无修正）
DEFAULT_COMBAT: dict[str, float] = {
    "ranged_hit_mul": 1.0,
    "physical_damage_mul": 1.0,
    "magic_damage_mul": 1.0,
}

# 四象层机读名 → 中文（enrich 写入 layer_label_zh，渲染/前端共用）
LAYER_LABEL_ZH: dict[str, str] = {
    "environment": "环境",
    "weather": "天气",
    "effect": "场上效果",
}


def default_side_combat() -> dict[str, float]:
    """空载荷副本（开战初值 / 无 catalog 时）。"""
    return dict(DEFAULT_COMBAT)


def catalog_entry(
    catalogs: dict[str, dict[str, Any]] | None,
    layer_name: str,
    content_id: str | None,
) -> dict[str, Any]:
    """
    查四象内容目录条目。

    参数:
        catalogs: ``{environment|weather|effect: {id: {label_zh, combat, ...}}}``。
        layer_name: 层名。
        content_id: 内容 id。

    返回:
        条目 dict；缺失时为空 dict。
    """
    if not content_id or not catalogs:
        return {}
    layer_cat = catalogs.get(layer_name) or {}
    entry = layer_cat.get(str(content_id))
    return dict(entry) if isinstance(entry, dict) else {}


def label_zh_for(
    catalogs: dict[str, dict[str, Any]] | None,
    layer_name: str,
    content_id: str | None,
) -> str | None:
    """取内容中文名；无目录时回落 None（渲染层不得静默打英文 id）。"""
    if not content_id:
        return None
    entry = catalog_entry(catalogs, layer_name, content_id)
    label = entry.get("label_zh")
    return str(label) if label else None


def combat_from_entry(entry: dict[str, Any]) -> dict[str, float]:
    """从 catalog 条目抽取 combat 乘区（缺省 1.0）。"""
    raw = entry.get("combat") if isinstance(entry.get("combat"), dict) else {}
    out = dict(DEFAULT_COMBAT)
    for key in DEFAULT_COMBAT:
        if key in raw and raw[key] is not None:
            out[key] = float(raw[key])
    return out


def merge_combat_payloads(*payloads: dict[str, float]) -> dict[str, float]:
    """多层 combat 乘区相乘合并。"""
    out = dict(DEFAULT_COMBAT)
    for payload in payloads:
        for key in DEFAULT_COMBAT:
            out[key] = float(out[key]) * float(payload.get(key, 1.0))
    return out


def combat_payload_for_side(
    layer_results: list[dict[str, Any]],
    catalogs: dict[str, dict[str, Any]] | None,
    side: int,
) -> dict[str, float]:
    """
    合并某侧生效的环境 + 天气 combat 载荷（效果层不进此表）。

    覆盖规则与 ``effect_multipliers_for_side`` 一致：全场用赢家；split 用己方。
    """
    parts: list[dict[str, float]] = []
    for layer_name in ("environment", "weather"):
        layer_result = next(
            (item for item in layer_results if item.get("layer") == layer_name),
            None,
        )
        if layer_result is None:
            continue
        content_id = resolved_content_id_for_side(layer_result, side)
        entry = catalog_entry(catalogs, layer_name, content_id)
        parts.append(combat_from_entry(entry))
    if not parts:
        return default_side_combat()
    return merge_combat_payloads(*parts)


def apply_side_combat_to_state(
    state: Any,
    layer_results: list[dict[str, Any]],
    catalogs: dict[str, dict[str, Any]] | None,
) -> None:
    """
    将两侧 combat 载荷写入 ``BattleState.side_combat``（引擎构建钩子）。

    参数:
        state: 须有 ``side_combat`` 列表（长度 ≥ 2）。
        layer_results: 四象对抗结果。
        catalogs: 内容目录纯 dict。
    """
    for side in (0, 1):
        state.side_combat[side] = combat_payload_for_side(layer_results, catalogs, side)


def hit_rate_with_combat(
    base_rate: float,
    *,
    is_melee: bool,
    combat: dict[str, float],
) -> float:
    """
    命中基础率套环境/天气远程命中乘区。

    近战不吃 ``ranged_hit_mul``；结果不在此 clamp（由调用方与 extra/dodge 一并处理）。
    """
    rate = float(base_rate)
    if not is_melee:
        rate *= float(combat.get("ranged_hit_mul", 1.0))
    return rate


def damage_mul_for_attack_kind(
    attack_kind: str,
    combat: dict[str, float],
) -> float:
    """
    按攻击类别取物理/法术伤害乘区（可叠乘）。

    ``*_physical`` 吃 physical；``*_magic`` 吃 magic。
    """
    mul = 1.0
    if "physical" in attack_kind:
        mul *= float(combat.get("physical_damage_mul", 1.0))
    if "magic" in attack_kind:
        mul *= float(combat.get("magic_damage_mul", 1.0))
    return mul


def combat_notes_zh(combat: dict[str, float]) -> list[str]:
    """把非 1.0 的 combat 乘区译成中文说明（战报用）。"""
    notes: list[str] = []
    mapping = (
        ("ranged_hit_mul", "远程命中"),
        ("physical_damage_mul", "物理伤害"),
        ("magic_damage_mul", "法术伤害"),
    )
    for key, label in mapping:
        value = float(combat.get(key, 1.0))
        if abs(value - 1.0) > 1e-9:
            text = f"{value:.4f}".rstrip("0").rstrip(".")
            notes.append(f"{label}×{text}")
    return notes


def enrich_battlefield_layer_events(
    layer_results: list[dict[str, Any]],
    catalogs: dict[str, dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """
    为四象事件补中文名与 combat_notes（机读 id 仍保留）。

    写入字段:
        ``layer_label_zh``、各方 ``*_label_zh``、``combat_notes``。
        前端 / ``battle_text`` 应优先读这些字段，避免双端维护层名表。
    """
    enriched: list[dict[str, Any]] = []
    for item in layer_results:
        row = dict(item)
        layer_name = str(row.get("layer") or "")
        row["layer_label_zh"] = LAYER_LABEL_ZH.get(layer_name, layer_name)
        atk_id = row.get("attacker_id")
        def_id = row.get("defender_id")
        row["attacker_label_zh"] = label_zh_for(catalogs, layer_name, atk_id)
        row["defender_label_zh"] = label_zh_for(catalogs, layer_name, def_id)
        for key in (
            "resolved_full",
            "resolved_attacker_half",
            "resolved_defender_half",
            "resolved_neutral",
        ):
            cid = row.get(key)
            row[f"{key}_label_zh"] = label_zh_for(catalogs, layer_name, cid)

        notes: list[str] = []
        if layer_name in ("environment", "weather") and row.get("coverage") in (
            "full_attacker",
            "full_defender",
        ):
            entry = catalog_entry(catalogs, layer_name, row.get("resolved_full"))
            notes = combat_notes_zh(combat_from_entry(entry))
        elif layer_name in ("environment", "weather") and row.get("coverage") == "split":
            for half_key, prefix in (
                ("resolved_attacker_half", "己方"),
                ("resolved_defender_half", "敌方"),
            ):
                entry = catalog_entry(catalogs, layer_name, row.get(half_key))
                for note in combat_notes_zh(combat_from_entry(entry)):
                    notes.append(f"{prefix}{note}")
        row["combat_notes"] = notes
        enriched.append(row)
    return enriched
