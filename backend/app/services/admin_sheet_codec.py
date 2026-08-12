"""
嵌套配置域：运营表格 ↔ 域 JSON 编解码。

表格写入路径：前端提交 sheets.rows → ``sheets_to_payload`` → 草稿 JSON → 校验/发布。
JSON 写入路径：直接 PUT draft，不经本模块。
"""

from __future__ import annotations

from typing import Any, Callable

from app.schemas.common import AppError
from app.services.admin_field_schema import (
    AVATAR_SCHEMA,
    DICE_SCHEMA,
    IDLE_SCHEMA,
    REALMS_SCHEMA,
    DomainEditSchema,
    get_domain_edit_schema,
)

_IDLE_GLOBAL_HELP = {
    "tick_seconds": ("Tick 秒数", "每次挂机结算的墙钟秒数"),
    "clamp_min": ("加成下限", "bonus_channels 乘积下限"),
    "clamp_max": ("加成上限", "bonus_channels 乘积上限"),
}

_DICE_SCALAR_HELP: dict[tuple[str, str], tuple[str, str]] = {
    ("fallback_bounds", "min"): ("回落下限", "无境界上下文时的骰子下限"),
    ("fallback_bounds", "max"): ("回落上限", "无境界上下文时的骰子上限"),
    ("monster_default", "min"): ("怪物下限", "PVE 防守侧默认下限"),
    ("monster_default", "max"): ("怪物上限", "PVE 防守侧默认上限"),
    ("clamp", "absolute_min"): ("绝对下限", "全局钳制最小值"),
    ("clamp", "absolute_max"): ("绝对上限", "全局钳制最大值"),
    ("breakthrough", "use_legacy_success_rate"): (
        "沿用突破成功率",
        "true=用 breakthrough.yaml 成功率映射",
    ),
    ("combat", "use_midpoint_normalizer"): (
        "中点正态化伤害",
        "true=伤害因子=roll/mid(lo,hi)",
    ),
}

_DIRECTION_RATE_KEYS = {
    "spirit": "cultivation_per_tick",
    "body": "body_tempering_per_tick",
    "crafting": "crafting_exp_per_tick",
}


def _as_bool(value: Any) -> bool:
    """宽松布尔解析。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "是"}:
        return True
    if text in {"0", "false", "no", "n", "否", ""}:
        return False
    raise AppError(code=40000, message=f"无法解析布尔值: {value!r}", http_status=400)


def _as_int(value: Any) -> int:
    """整数解析。"""
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise AppError(code=40000, message=f"须为整数: {value!r}", http_status=400) from exc


def _as_float(value: Any) -> float:
    """浮点解析。"""
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise AppError(code=40000, message=f"须为数字: {value!r}", http_status=400) from exc


def _as_null_str(value: Any) -> str | None:
    """空串 / null / None → None。"""
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.lower() in {"null", "none"}:
        return None
    return text


def _sheet_map(sheets: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """sheet_id → rows。"""
    result: dict[str, list[dict[str, Any]]] = {}
    for sheet in sheets:
        if not isinstance(sheet, dict):
            continue
        sheet_id = str(sheet.get("sheet_id") or "").strip()
        rows = sheet.get("rows")
        if not sheet_id or not isinstance(rows, list):
            continue
        result[sheet_id] = [row for row in rows if isinstance(row, dict)]
    return result


def _require_rows(mapped: dict[str, list[dict[str, Any]]], sheet_id: str) -> list[dict[str, Any]]:
    """取表行；缺表则空列表（允许部分提交时由调用方决定）。"""
    return mapped.get(sheet_id, [])


# ----- realms -----


def realms_payload_to_sheets(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """境界 JSON → 表格。"""
    majors_root = payload.get("major_realms")
    if not isinstance(majors_root, dict):
        majors_root = {}
    major_rows: list[dict[str, Any]] = []
    stage_rows: list[dict[str, Any]] = []
    for major_id, body in majors_root.items():
        if not isinstance(body, dict):
            continue
        next_major = body.get("next_major")
        major_rows.append(
            {
                "id": str(major_id),
                "name": body.get("name", ""),
                "stage_mode": body.get("stage_mode", "layers"),
                "next_major": "" if next_major is None else str(next_major),
            },
        )
        stages = body.get("stages")
        if not isinstance(stages, list):
            continue
        for stage_body in stages:
            if not isinstance(stage_body, dict):
                continue
            stage_rows.append(
                {
                    "major_id": str(major_id),
                    "stage": stage_body.get("stage"),
                    "label": stage_body.get("label", ""),
                    "cultivation_required": stage_body.get("cultivation_required", 0),
                    "base_atk": stage_body.get("base_atk", 0),
                    "base_hp": stage_body.get("base_hp", 0),
                },
            )

    order_raw = payload.get("body_temper_unlock_majors") or payload.get(
        "body_temper_major_order",
    )
    body_order_rows: list[dict[str, Any]] = []
    if isinstance(order_raw, list):
        for idx, major_id in enumerate(order_raw, start=1):
            body_order_rows.append({"order": idx, "major_id": str(major_id)})

    bt_majors_root = payload.get("body_temper_majors")
    bt_major_rows: list[dict[str, Any]] = []
    bt_layer_rows: list[dict[str, Any]] = []
    if isinstance(bt_majors_root, dict):
        for major_id, body in bt_majors_root.items():
            if not isinstance(body, dict):
                continue
            next_major = body.get("next_major")
            bt_major_rows.append(
                {
                    "id": str(major_id),
                    "name": body.get("name", ""),
                    "stage_mode": body.get("stage_mode", "layers"),
                    "unlock_major": body.get("unlock_major", ""),
                    "next_major": "" if next_major is None else str(next_major),
                },
            )
            stages = body.get("stages")
            if not isinstance(stages, list):
                continue
            for stage_body in stages:
                if not isinstance(stage_body, dict):
                    continue
                bt_layer_rows.append(
                    {
                        "major_id": str(major_id),
                        "stage": stage_body.get("stage"),
                        "label": stage_body.get("label", ""),
                        "progress_required": stage_body.get("progress_required", 0),
                    },
                )

    quench_root = payload.get("body_temper_quench") or {}
    quench_rows: list[dict[str, Any]] = []
    if isinstance(quench_root, dict):
        for rule_id in ("layer_advance", "major_advance"):
            body = quench_root.get(rule_id) or {}
            if not isinstance(body, dict):
                continue
            quench_rows.append(
                {
                    "rule_id": rule_id,
                    "success_rate": body.get("success_rate"),
                    "fail_progress_keep_ratio": body.get("fail_progress_keep_ratio"),
                    "clamp_min": None,
                    "clamp_max": None,
                },
            )
        clamp = quench_root.get("success_rate_clamp") or {}
        if isinstance(clamp, dict):
            quench_rows.append(
                {
                    "rule_id": "clamp",
                    "success_rate": None,
                    "fail_progress_keep_ratio": None,
                    "clamp_min": clamp.get("min"),
                    "clamp_max": clamp.get("max"),
                },
            )

    return [
        {**REALMS_SCHEMA.sheets[0].to_dict(), "rows": major_rows},
        {**REALMS_SCHEMA.sheets[1].to_dict(), "rows": stage_rows},
        {**REALMS_SCHEMA.sheets[2].to_dict(), "rows": body_order_rows},
        {**REALMS_SCHEMA.sheets[3].to_dict(), "rows": bt_major_rows},
        {**REALMS_SCHEMA.sheets[4].to_dict(), "rows": bt_layer_rows},
        {**REALMS_SCHEMA.sheets[5].to_dict(), "rows": quench_rows},
    ]


def realms_sheets_to_payload(sheets: list[dict[str, Any]]) -> dict[str, Any]:
    """境界表格 → 域 JSON。"""
    mapped = _sheet_map(sheets)
    major_rows = _require_rows(mapped, "majors")
    stage_rows = _require_rows(mapped, "stages")
    if not major_rows:
        raise AppError(code=40000, message="境界表 majors 不能为空", http_status=400)

    major_realms: dict[str, Any] = {}
    for row in major_rows:
        major_id = str(row.get("id") or "").strip()
        if not major_id:
            raise AppError(code=40000, message="大境界 id 不能为空", http_status=400)
        stage_mode = str(row.get("stage_mode") or "layers").strip()
        if stage_mode not in {"layers", "phases"}:
            raise AppError(
                code=40000,
                message=f"stage_mode 仅支持 layers/phases: {major_id}",
                http_status=400,
            )
        major_realms[major_id] = {
            "name": str(row.get("name") or major_id),
            "stage_mode": stage_mode,
            "next_major": _as_null_str(row.get("next_major")),
            "stages": [],
        }

    stages_by_major: dict[str, list[dict[str, Any]]] = {key: [] for key in major_realms}
    for row in stage_rows:
        major_id = str(row.get("major_id") or "").strip()
        if major_id not in major_realms:
            raise AppError(
                code=40000,
                message=f"小层引用未知大境界: {major_id}",
                http_status=400,
            )
        stages_by_major[major_id].append(
            {
                "stage": _as_int(row.get("stage")),
                "label": str(row.get("label") or ""),
                "cultivation_required": _as_int(row.get("cultivation_required")),
                "base_atk": _as_int(row.get("base_atk")),
                "base_hp": _as_int(row.get("base_hp")),
            },
        )

    for major_id, stages in stages_by_major.items():
        stages.sort(key=lambda item: int(item["stage"]))
        major_realms[major_id]["stages"] = stages

    order_rows = _require_rows(mapped, "body_temper_order")
    order_rows_sorted = sorted(order_rows, key=lambda row: _as_int(row.get("order")))
    body_temper_unlock_majors = [
        str(row.get("major_id") or "").strip()
        for row in order_rows_sorted
        if str(row.get("major_id") or "").strip()
    ]

    bt_major_rows = _require_rows(mapped, "body_temper_majors")
    body_temper_majors: dict[str, Any] = {}
    for row in bt_major_rows:
        major_id = str(row.get("id") or "").strip()
        if not major_id:
            raise AppError(code=40000, message="炼体境 id 不能为空", http_status=400)
        stage_mode = str(row.get("stage_mode") or "layers").strip()
        body_temper_majors[major_id] = {
            "name": str(row.get("name") or major_id),
            "stage_mode": stage_mode,
            "unlock_major": str(row.get("unlock_major") or "").strip(),
            "next_major": _as_null_str(row.get("next_major")),
            "stages": [],
        }

    bt_layers = _require_rows(mapped, "body_temper_layers")
    layers_by_major: dict[str, list[dict[str, Any]]] = {
        key: [] for key in body_temper_majors
    }
    for row in bt_layers:
        major_id = str(row.get("major_id") or "").strip()
        if major_id not in body_temper_majors:
            raise AppError(
                code=40000,
                message=f"炼体层引用未知炼体境: {major_id}",
                http_status=400,
            )
        layers_by_major[major_id].append(
            {
                "stage": _as_int(row.get("stage")),
                "label": str(row.get("label") or ""),
                "progress_required": _as_int(row.get("progress_required")),
            },
        )
    for major_id, layers in layers_by_major.items():
        layers.sort(key=lambda item: int(item["stage"]))
        body_temper_majors[major_id]["stages"] = layers

    quench_rows = _require_rows(mapped, "body_temper_quench")
    body_temper_quench: dict[str, Any] = {}
    for row in quench_rows:
        rule_id = str(row.get("rule_id") or "").strip()
        if rule_id == "clamp":
            body_temper_quench["success_rate_clamp"] = {
                "min": float(
                    row.get("clamp_min") if row.get("clamp_min") is not None else 0.05,
                ),
                "max": float(
                    row.get("clamp_max") if row.get("clamp_max") is not None else 0.95,
                ),
            }
        elif rule_id in {"layer_advance", "major_advance"}:
            body_temper_quench[rule_id] = {
                "success_rate": float(row.get("success_rate") or 0),
                "fail_progress_keep_ratio": float(
                    row.get("fail_progress_keep_ratio") or 0,
                ),
            }

    result: dict[str, Any] = {"major_realms": major_realms}
    if body_temper_unlock_majors:
        result["body_temper_unlock_majors"] = body_temper_unlock_majors
    if body_temper_majors:
        result["body_temper_majors"] = body_temper_majors
    if body_temper_quench:
        result["body_temper_quench"] = body_temper_quench
    return result


# ----- idle -----


def idle_payload_to_sheets(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """挂机 JSON → 表格。"""
    global_rows: list[dict[str, Any]] = []
    for key in ("tick_seconds", "clamp_min", "clamp_max"):
        label_zh, help_zh = _IDLE_GLOBAL_HELP[key]
        global_rows.append(
            {
                "key": key,
                "label_zh": label_zh,
                "value": payload.get(key),
                "help_zh": help_zh,
            },
        )

    cost_root = payload.get("spirit_stone_cost_by_realm")
    cost_rows: list[dict[str, Any]] = []
    if isinstance(cost_root, dict):
        for major_id, cost in cost_root.items():
            cost_rows.append({"major_realm": str(major_id), "cost": cost})

    directions_root = payload.get("directions")
    direction_rows: list[dict[str, Any]] = []
    if isinstance(directions_root, dict):
        for direction, body in directions_root.items():
            if not isinstance(body, dict):
                continue
            rate_key = _DIRECTION_RATE_KEYS.get(str(direction), "cultivation_per_tick")
            # 兼容自定义键：取第一个 *_per_tick
            for key in body:
                if str(key).endswith("_per_tick"):
                    rate_key = str(key)
                    break
            direction_rows.append(
                {
                    "direction": str(direction),
                    "enabled": bool(body.get("enabled", True)),
                    "rate_key": rate_key,
                    "rate_value": body.get(rate_key, 0),
                },
            )

    gain_root = payload.get("gain_per_tick_by_realm")
    gain_rows: list[dict[str, Any]] = []
    if isinstance(gain_root, dict):
        for direction, realm_map in gain_root.items():
            if not isinstance(realm_map, dict):
                continue
            for major_id, gain in realm_map.items():
                gain_rows.append(
                    {
                        "direction": str(direction),
                        "major_realm": str(major_id),
                        "gain": gain,
                    },
                )

    channel_root = payload.get("bonus_channels")
    channel_rows: list[dict[str, Any]] = []
    if isinstance(channel_root, dict):
        for channel, body in channel_root.items():
            if not isinstance(body, dict):
                continue
            channel_rows.append(
                {
                    "channel": str(channel),
                    "enabled": bool(body.get("enabled", False)),
                    "default_mult": body.get("default_mult", 1.0),
                },
            )

    sheet_defs = {sheet.sheet_id: sheet for sheet in IDLE_SCHEMA.sheets}
    return [
        {**sheet_defs["globals"].to_dict(), "rows": global_rows},
        {**sheet_defs["spirit_stone_cost"].to_dict(), "rows": cost_rows},
        {**sheet_defs["directions"].to_dict(), "rows": direction_rows},
        {**sheet_defs["gain_per_tick"].to_dict(), "rows": gain_rows},
        {**sheet_defs["bonus_channels"].to_dict(), "rows": channel_rows},
    ]


def idle_sheets_to_payload(sheets: list[dict[str, Any]]) -> dict[str, Any]:
    """挂机表格 → 域 JSON。"""
    mapped = _sheet_map(sheets)
    payload: dict[str, Any] = {
        "tick_seconds": 60,
        "clamp_min": 0.5,
        "clamp_max": 2.0,
        "spirit_stone_cost_by_realm": {},
        "directions": {},
        "gain_per_tick_by_realm": {},
        "bonus_channels": {},
    }

    for row in _require_rows(mapped, "globals"):
        key = str(row.get("key") or "").strip()
        if key == "tick_seconds":
            payload[key] = _as_int(row.get("value"))
        elif key in {"clamp_min", "clamp_max"}:
            payload[key] = _as_float(row.get("value"))

    for row in _require_rows(mapped, "spirit_stone_cost"):
        major = str(row.get("major_realm") or "").strip()
        if not major:
            continue
        payload["spirit_stone_cost_by_realm"][major] = _as_int(row.get("cost"))

    for row in _require_rows(mapped, "directions"):
        direction = str(row.get("direction") or "").strip()
        if not direction:
            continue
        rate_key = str(row.get("rate_key") or _DIRECTION_RATE_KEYS.get(direction, "cultivation_per_tick"))
        payload["directions"][direction] = {
            "enabled": _as_bool(row.get("enabled")),
            rate_key: _as_int(row.get("rate_value")),
        }

    for row in _require_rows(mapped, "gain_per_tick"):
        direction = str(row.get("direction") or "").strip()
        major = str(row.get("major_realm") or "").strip()
        if not direction or not major:
            continue
        bucket = payload["gain_per_tick_by_realm"].setdefault(direction, {})
        bucket[major] = _as_int(row.get("gain"))

    for row in _require_rows(mapped, "bonus_channels"):
        channel = str(row.get("channel") or "").strip()
        if not channel:
            continue
        payload["bonus_channels"][channel] = {
            "enabled": _as_bool(row.get("enabled")),
            "default_mult": _as_float(row.get("default_mult")),
        }

    if not payload["directions"]:
        raise AppError(code=40000, message="挂机三向表不能为空", http_status=400)
    if not payload["gain_per_tick_by_realm"]:
        raise AppError(code=40000, message="境界基础产出表不能为空", http_status=400)
    return payload


# ----- dice -----


def dice_payload_to_sheets(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """修为骰 JSON → 表格。"""
    scalar_rows: list[dict[str, Any]] = []
    for group, fields in (
        ("fallback_bounds", ("min", "max")),
        ("monster_default", ("min", "max")),
        ("clamp", ("absolute_min", "absolute_max")),
        ("breakthrough", ("use_legacy_success_rate",)),
        ("combat", ("use_midpoint_normalizer",)),
    ):
        body = payload.get(group)
        if not isinstance(body, dict):
            body = {}
        for field in fields:
            label_zh, help_zh = _DICE_SCALAR_HELP.get((group, field), (field, ""))
            scalar_rows.append(
                {
                    "group": group,
                    "field": field,
                    "label_zh": label_zh,
                    "value": body.get(field),
                    "help_zh": help_zh,
                },
            )

    bounds_rows: list[dict[str, Any]] = []
    bounds_root = payload.get("realm_bounds")
    if isinstance(bounds_root, dict):
        for major, stages in bounds_root.items():
            if not isinstance(stages, dict):
                continue
            for stage, body in stages.items():
                if not isinstance(body, dict):
                    continue
                bounds_rows.append(
                    {
                        "major_realm": str(major),
                        "stage": int(stage) if str(stage).isdigit() else stage,
                        "min": body.get("min"),
                        "max": body.get("max"),
                    },
                )

    body_bonus_rows: list[dict[str, Any]] = []
    bonus_root = payload.get("body_realm_bonus")
    if isinstance(bonus_root, dict):
        for major, stages in bonus_root.items():
            if not isinstance(stages, dict):
                continue
            for stage, body in stages.items():
                if not isinstance(body, dict):
                    continue
                body_bonus_rows.append(
                    {
                        "major_realm": str(major),
                        "stage": int(stage) if str(stage).isdigit() else stage,
                        "min_bonus": body.get("min_bonus"),
                        "max_bonus": body.get("max_bonus"),
                    },
                )

    fate_rows: list[dict[str, Any]] = []
    fate_list = payload.get("fate_luck_tiers")
    if isinstance(fate_list, list):
        for index, body in enumerate(fate_list):
            if not isinstance(body, dict):
                continue
            fate_rows.append(
                {
                    "row_index": index,
                    "min_luck": body.get("min_luck"),
                    "max_luck": body.get("max_luck"),
                    "min_bonus": body.get("min_bonus"),
                    "max_bonus": body.get("max_bonus"),
                },
            )

    channel_rows: list[dict[str, Any]] = []
    channels = payload.get("bonus_channels")
    if isinstance(channels, dict):
        for channel, body in channels.items():
            if not isinstance(body, dict):
                continue
            channel_rows.append(
                {
                    "channel": str(channel),
                    "enabled": bool(body.get("enabled", False)),
                },
            )

    purpose_rows: list[dict[str, Any]] = []
    purposes = payload.get("purposes")
    if isinstance(purposes, list):
        for purpose in purposes:
            purpose_rows.append({"purpose": str(purpose)})

    sheet_defs = {sheet.sheet_id: sheet for sheet in DICE_SCHEMA.sheets}
    return [
        {**sheet_defs["scalar_groups"].to_dict(), "rows": scalar_rows},
        {**sheet_defs["realm_bounds"].to_dict(), "rows": bounds_rows},
        {**sheet_defs["body_realm_bonus"].to_dict(), "rows": body_bonus_rows},
        {**sheet_defs["fate_luck_tiers"].to_dict(), "rows": fate_rows},
        {**sheet_defs["bonus_channels"].to_dict(), "rows": channel_rows},
        {**sheet_defs["purposes"].to_dict(), "rows": purpose_rows},
    ]


def dice_sheets_to_payload(sheets: list[dict[str, Any]]) -> dict[str, Any]:
    """修为骰表格 → 域 JSON。"""
    mapped = _sheet_map(sheets)
    payload: dict[str, Any] = {
        "fallback_bounds": {},
        "monster_default": {},
        "clamp": {},
        "breakthrough": {},
        "combat": {},
        "purposes": [],
        "bonus_channels": {},
        "fate_luck_tiers": [],
        "body_realm_bonus": {},
        "realm_bounds": {},
    }

    bool_fields = {
        ("breakthrough", "use_legacy_success_rate"),
        ("combat", "use_midpoint_normalizer"),
    }
    for row in _require_rows(mapped, "scalar_groups"):
        group = str(row.get("group") or "").strip()
        field = str(row.get("field") or "").strip()
        if not group or not field:
            continue
        bucket = payload.setdefault(group, {})
        if not isinstance(bucket, dict):
            raise AppError(code=40000, message=f"分组须为 object: {group}", http_status=400)
        raw = row.get("value")
        if (group, field) in bool_fields:
            bucket[field] = _as_bool(raw)
        else:
            bucket[field] = _as_int(raw)

    for row in _require_rows(mapped, "realm_bounds"):
        major = str(row.get("major_realm") or "").strip()
        if not major:
            continue
        stage = str(_as_int(row.get("stage")))
        payload["realm_bounds"].setdefault(major, {})[stage] = {
            "min": _as_int(row.get("min")),
            "max": _as_int(row.get("max")),
        }

    for row in _require_rows(mapped, "body_realm_bonus"):
        major = str(row.get("major_realm") or "").strip()
        if not major:
            continue
        stage = str(_as_int(row.get("stage")))
        payload["body_realm_bonus"].setdefault(major, {})[stage] = {
            "min_bonus": _as_int(row.get("min_bonus")),
            "max_bonus": _as_int(row.get("max_bonus")),
        }

    fate_rows = sorted(
        _require_rows(mapped, "fate_luck_tiers"),
        key=lambda item: _as_int(item.get("row_index", 0)),
    )
    for row in fate_rows:
        payload["fate_luck_tiers"].append(
            {
                "min_luck": _as_int(row.get("min_luck")),
                "max_luck": _as_int(row.get("max_luck")),
                "min_bonus": _as_int(row.get("min_bonus")),
                "max_bonus": _as_int(row.get("max_bonus")),
            },
        )

    for row in _require_rows(mapped, "bonus_channels"):
        channel = str(row.get("channel") or "").strip()
        if not channel:
            continue
        payload["bonus_channels"][channel] = {"enabled": _as_bool(row.get("enabled"))}

    for row in _require_rows(mapped, "purposes"):
        purpose = str(row.get("purpose") or "").strip()
        if purpose:
            payload["purposes"].append(purpose)

    if not payload["realm_bounds"]:
        raise AppError(code=40000, message="境界默认上下限表不能为空", http_status=400)
    return payload


# ----- avatar -----

_AVATAR_GLOBAL_HELP: dict[str, tuple[str, str]] = {
    "unlock_major_realm": ("凝练门槛", "最低大境界 id"),
    "max_avatars": ("化身上限", "定案必须为 1"),
    "initial_stat_ratio": ("初始属性比例", "相对本体"),
    "material_mod_placeholder": ("材料修正", "占位乘区"),
    "condense_spirit_stone_cost": ("凝练灵石", "整数"),
    "spirit_stone_cost_per_tick_ratio": ("耗石比例", "相对本体同境"),
}

_AVATAR_TRANSFER_HELP: dict[str, tuple[str, str]] = {
    "allow": ("允许资源", "逗号分隔，如 cultivation_points"),
    "deny": ("拒绝资源", "逗号分隔"),
    "retention_ratio": ("保留率", "(0,1]；到账=floor(gross×ratio)"),
    "min_amount": ("最小互传", "整数"),
    "summary": ("玩家说明", "显性展示"),
}

_AVATAR_STAMINA_HELP: dict[str, tuple[str, str]] = {
    "base_cap": ("基础体力上限", "整数"),
    "daily_action_cap": ("日行动上限", "整数"),
    "recovery.per_hour": ("每小时恢复", "点数"),
    "recovery.summary": ("恢复说明", "玩家可见"),
    "allow_stamina_transfer": ("允许互传体力", "bool；默认 false"),
}


def avatar_payload_to_sheets(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """化身域 JSON → 运营表格。"""
    global_rows: list[dict[str, Any]] = []
    for key, (label_zh, help_zh) in _AVATAR_GLOBAL_HELP.items():
        if key in payload:
            global_rows.append(
                {
                    "key": key,
                    "label_zh": label_zh,
                    "value": payload.get(key),
                    "help_zh": help_zh,
                },
            )

    feature_rows: list[dict[str, Any]] = []
    features = payload.get("feature_unlocks") or {}
    if isinstance(features, dict):
        for feature_id, body in features.items():
            if not isinstance(body, dict):
                continue
            feature_rows.append(
                {
                    "feature_id": str(feature_id),
                    "min_major": body.get("min_major", ""),
                    "label_zh": body.get("label_zh", feature_id),
                    "summary": body.get("summary", ""),
                },
            )

    transfer_raw = payload.get("transfer") or {}
    transfer_rows: list[dict[str, Any]] = []
    if isinstance(transfer_raw, dict):
        for key, (label_zh, help_zh) in _AVATAR_TRANSFER_HELP.items():
            val = transfer_raw.get(key)
            if isinstance(val, (list, tuple)):
                val = ",".join(str(x) for x in val)
            transfer_rows.append(
                {
                    "key": key,
                    "label_zh": label_zh,
                    "value": val,
                    "help_zh": help_zh,
                },
            )

    stamina_raw = payload.get("stamina") or {}
    stamina_rows: list[dict[str, Any]] = []
    if isinstance(stamina_raw, dict):
        recovery = stamina_raw.get("recovery") or {}
        flat = {
            "base_cap": stamina_raw.get("base_cap"),
            "daily_action_cap": stamina_raw.get("daily_action_cap"),
            "recovery.per_hour": recovery.get("per_hour") if isinstance(recovery, dict) else None,
            "recovery.summary": recovery.get("summary") if isinstance(recovery, dict) else None,
            "allow_stamina_transfer": stamina_raw.get("allow_stamina_transfer"),
        }
        for key, (label_zh, help_zh) in _AVATAR_STAMINA_HELP.items():
            stamina_rows.append(
                {
                    "key": key,
                    "label_zh": label_zh,
                    "value": flat.get(key),
                    "help_zh": help_zh,
                },
            )

    action_rows: list[dict[str, Any]] = []
    costs = stamina_raw.get("action_costs") if isinstance(stamina_raw, dict) else {}
    if isinstance(costs, dict):
        for action_id, cost in costs.items():
            action_rows.append({"action_id": str(action_id), "cost": cost})

    idle_rows: list[dict[str, Any]] = []
    idle = payload.get("idle") or {}
    if isinstance(idle, dict):
        for direction, body in idle.items():
            if not isinstance(body, dict):
                continue
            gain = (
                body.get("cultivation_per_tick")
                or body.get("body_tempering_per_tick")
                or body.get("crafting_exp_per_tick")
                or 0
            )
            idle_rows.append(
                {
                    "direction": str(direction),
                    "enabled": bool(body.get("enabled", True)),
                    "gain_per_tick": gain,
                },
            )

    sheet_defs = {sheet.sheet_id: sheet for sheet in AVATAR_SCHEMA.sheets}
    return [
        {**sheet_defs["globals"].to_dict(), "rows": global_rows},
        {**sheet_defs["feature_unlocks"].to_dict(), "rows": feature_rows},
        {**sheet_defs["transfer"].to_dict(), "rows": transfer_rows},
        {**sheet_defs["stamina"].to_dict(), "rows": stamina_rows},
        {**sheet_defs["action_costs"].to_dict(), "rows": action_rows},
        {**sheet_defs["idle_rates"].to_dict(), "rows": idle_rows},
    ]


def avatar_sheets_to_payload(sheets: list[dict[str, Any]]) -> dict[str, Any]:
    """化身运营表格 → 域 JSON。"""
    mapped = _sheet_map(sheets)
    payload: dict[str, Any] = {
        "unlock_major_realm": "jindan",
        "max_avatars": 1,
        "initial_stat_ratio": 0.5,
        "material_mod_placeholder": 1.0,
        "condense_spirit_stone_cost": 1000,
        "spirit_stone_cost_per_tick_ratio": 0.8,
        "feature_unlocks": {},
        "transfer": {
            "allow": ["cultivation_points"],
            "deny": ["body_tempering_points", "crafting_exp"],
            "retention_ratio": 0.8,
            "retention_by_major": {},
            "min_amount": 1,
            "summary": "",
        },
        "stamina": {
            "base_cap": 100,
            "cap_by_major": {},
            "daily_action_cap": 10,
            "recovery": {"per_hour": 5, "summary": ""},
            "action_costs": {},
            "allow_stamina_transfer": False,
        },
        "idle": {},
    }

    for row in _require_rows(mapped, "globals"):
        key = str(row.get("key") or "").strip()
        if not key:
            continue
        val = row.get("value")
        if key in {
            "max_avatars",
            "condense_spirit_stone_cost",
        }:
            payload[key] = _as_int(val)
        elif key in {"initial_stat_ratio", "material_mod_placeholder", "spirit_stone_cost_per_tick_ratio"}:
            payload[key] = _as_float(val)
        else:
            payload[key] = str(val).strip() if val is not None else ""

    for row in _require_rows(mapped, "feature_unlocks"):
        feature_id = str(row.get("feature_id") or "").strip()
        if not feature_id:
            continue
        payload["feature_unlocks"][feature_id] = {
            "min_major": str(row.get("min_major") or "").strip(),
            "label_zh": str(row.get("label_zh") or feature_id),
            "summary": str(row.get("summary") or ""),
        }

    for row in _require_rows(mapped, "transfer"):
        key = str(row.get("key") or "").strip()
        val = row.get("value")
        if key in {"allow", "deny"}:
            text = str(val or "")
            payload["transfer"][key] = [p.strip() for p in text.split(",") if p.strip()]
        elif key == "retention_ratio":
            payload["transfer"][key] = _as_float(val)
        elif key == "min_amount":
            payload["transfer"][key] = _as_int(val)
        elif key == "summary":
            payload["transfer"][key] = str(val or "")

    for row in _require_rows(mapped, "stamina"):
        key = str(row.get("key") or "").strip()
        val = row.get("value")
        if key == "base_cap" or key == "daily_action_cap":
            payload["stamina"][key] = _as_int(val)
        elif key == "recovery.per_hour":
            payload["stamina"]["recovery"]["per_hour"] = _as_float(val)
        elif key == "recovery.summary":
            payload["stamina"]["recovery"]["summary"] = str(val or "")
        elif key == "allow_stamina_transfer":
            payload["stamina"][key] = _as_bool(val)

    for row in _require_rows(mapped, "action_costs"):
        action_id = str(row.get("action_id") or "").strip()
        if action_id:
            payload["stamina"]["action_costs"][action_id] = _as_int(row.get("cost"))

    rate_keys = {
        "spirit": "cultivation_per_tick",
        "body": "body_tempering_per_tick",
        "crafting": "crafting_exp_per_tick",
    }
    for row in _require_rows(mapped, "idle_rates"):
        direction = str(row.get("direction") or "").strip()
        if not direction:
            continue
        body: dict[str, Any] = {rate_keys.get(direction, "cultivation_per_tick"): _as_int(row.get("gain_per_tick"))}
        if direction == "body":
            body["enabled"] = _as_bool(row.get("enabled", True))
        payload["idle"][direction] = body

    if int(payload.get("max_avatars", 1)) != 1:
        raise AppError(code=40000, message="avatar.max_avatars 必须为 1", http_status=400)
    if not payload["feature_unlocks"]:
        raise AppError(code=40000, message="feature_unlocks 不能为空", http_status=400)
    return payload


_PAYLOAD_TO_SHEETS: dict[str, Callable[[dict[str, Any]], list[dict[str, Any]]]] = {
    "realms": realms_payload_to_sheets,
    "idle": idle_payload_to_sheets,
    "dice": dice_payload_to_sheets,
    "avatar": avatar_payload_to_sheets,
}

_SHEETS_TO_PAYLOAD: dict[str, Callable[[list[dict[str, Any]]], dict[str, Any]]] = {
    "realms": realms_sheets_to_payload,
    "idle": idle_sheets_to_payload,
    "dice": dice_sheets_to_payload,
    "avatar": avatar_sheets_to_payload,
}


def supports_structured_sheets(domain_id: str) -> bool:
    """是否支持嵌套表格双写。"""
    return domain_id in _SHEETS_TO_PAYLOAD


def payload_to_sheets(domain_id: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """域 JSON → 带中文列头的表格。"""
    converter = _PAYLOAD_TO_SHEETS.get(domain_id)
    if converter is None:
        raise AppError(code=40056, message=f"域 {domain_id} 无结构化表格", http_status=400)
    return converter(payload)


def sheets_to_payload(domain_id: str, sheets: list[dict[str, Any]]) -> dict[str, Any]:
    """运营表格 → 域 JSON（后端 format）。"""
    converter = _SHEETS_TO_PAYLOAD.get(domain_id)
    if converter is None:
        raise AppError(code=40056, message=f"域 {domain_id} 无结构化表格", http_status=400)
    if not isinstance(sheets, list):
        raise AppError(code=40000, message="sheets 须为数组", http_status=400)
    return converter(sheets)


def schema_for_domain(domain_id: str) -> DomainEditSchema | None:
    """暴露 schema 查找。"""
    return get_domain_edit_schema(domain_id)
