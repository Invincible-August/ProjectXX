"""
炼体大境 / 淬体规则（结构对齐主修层·期）。

挂机只涨淬体度池；「投入淬体」写入 ``body_temper_progress``；
淬体 attempt 有成功率、失败回退进度；永不渡劫。
扩境：配置 ``next_major`` + 新 ``body_temper_majors`` 条目即可。
"""

from __future__ import annotations

import random
from typing import Any


def major_order_index(major_key: str, unlock_majors: tuple[str, ...]) -> int:
    """
    主修在炼体对照解锁序上的下标；未知为 -1。

    Args:
        major_key: 角色当前大境界键。
        unlock_majors: ``body_temper_unlock_majors``。

    Returns:
        int: 下标或 -1。
    """
    try:
        return unlock_majors.index(major_key)
    except ValueError:
        return -1


def stage_unlocked(
    *,
    character_major: str,
    unlock_major: str,
    unlock_majors: tuple[str, ...],
) -> bool:
    """主修是否已达对照解锁要求。"""
    char_idx = major_order_index(character_major, unlock_majors)
    need_idx = major_order_index(unlock_major, unlock_majors)
    if need_idx < 0:
        return False
    return char_idx >= need_idx


def _ensure_layer_fields(character: Any, cfg: Any) -> tuple[str, int, str]:
    """
    规范化角色炼体大境 / 层字段，缺省补默认。

    Returns:
        tuple: (major_id, layer_num, layer_label)。
    """
    major_id = str(getattr(character, "body_temper_stage", None) or cfg.default_major_id)
    if major_id not in cfg.majors:
        major_id = cfg.default_major_id
    major = cfg.majors[major_id]
    layer = int(getattr(character, "body_temper_layer", None) or 1)
    layer_cfg = major.stage_by_number(layer)
    if layer_cfg is None:
        layer = major.stages[0].stage
        layer_cfg = major.stages[0]
    label = str(getattr(character, "body_temper_layer_label", None) or layer_cfg.label)
    if label != layer_cfg.label:
        label = layer_cfg.label
    character.body_temper_stage = major_id
    character.body_temper_layer = layer
    character.body_temper_layer_label = label
    return major_id, layer, label


def build_body_temper_display(major_name: str, layer_label: str) -> str:
    """拼接炼体展示串（如「炼皮一层」「通脉初期」）。"""
    from app.services.realm_config import STAGE_LABEL_NAMES

    stage_name = STAGE_LABEL_NAMES.get(layer_label, layer_label)
    return f"{major_name}{stage_name}"


def current_progress_required(character: Any) -> int:
    """当前档淬体进度门槛。"""
    from app.services.realm_config import get_game_config

    cfg = get_game_config().body_temper
    major_id, layer, _ = _ensure_layer_fields(character, cfg)
    major = cfg.majors[major_id]
    layer_cfg = major.stage_by_number(layer)
    assert layer_cfg is not None
    return max(0, int(layer_cfg.progress_required))


def apply_body_temper_progress(character: Any, gained: int = 0) -> None:
    """
    将淬体进度写入角色（仅累计，不自动晋级）。

    进度封顶为当前层/期 ``progress_required``。

    Args:
        character: 角色 ORM。
        gained: 本次新增进度。
    """
    from app.services.realm_config import get_game_config

    cfg = get_game_config().body_temper
    if not cfg.majors:
        return
    _ensure_layer_fields(character, cfg)
    need = current_progress_required(character)
    progress = int(getattr(character, "body_temper_progress", 0) or 0) + max(0, int(gained or 0))
    if need > 0:
        progress = min(progress, need)
    character.body_temper_progress = progress


def _clamp_rate(rate: float, clamp: tuple[float, float]) -> float:
    """钳制成功率。"""
    lo, hi = clamp
    return max(float(lo), min(float(hi), float(rate)))


def quench_readiness(character: Any) -> dict[str, Any]:
    """
    淬体预览：始终给出下一档目标与进阶方式；再判断当前可否发起。

    Args:
        character: 角色 ORM。

    Returns:
        dict: can_quench / advance_type / success_rate / from/to display 等。
    """
    from app.services.realm_config import get_game_config

    cfg = get_game_config().body_temper
    major_id, layer, label = _ensure_layer_fields(character, cfg)
    major = cfg.majors[major_id]
    layer_cfg = major.stage_by_number(layer)
    assert layer_cfg is not None
    progress = int(getattr(character, "body_temper_progress", 0) or 0)
    need = max(0, int(layer_cfg.progress_required))
    from_display = build_body_temper_display(major.name, label)

    base: dict[str, Any] = {
        "from_stage": major_id,
        "from_stage_name": major.name,
        "from_layer": layer,
        "from_layer_label": label,
        "from_display": from_display,
        "progress": progress,
        "required": need,
        "to_stage": None,
        "to_stage_name": None,
        "to_layer": None,
        "to_layer_label": None,
        "to_display": None,
        "advance_type": None,
        "advance_type_label_zh": None,
        "success_rate": 0.0,
        "fail_progress_keep_ratio": 0.0,
        "needs_tribulation": False,
    }

    # —— 先解析「下一档是什么」（进度未满也展示，避免目标和类型空白）——
    if layer < major.max_stage():
        next_layer_cfg = major.stage_by_number(layer + 1)
        if next_layer_cfg is None:
            return {**base, "can_quench": False, "reason": "下档配置缺失"}
        to_display = build_body_temper_display(major.name, next_layer_cfg.label)
        rate = _clamp_rate(cfg.layer_advance.success_rate, cfg.success_rate_clamp)
        type_zh = (
            "同境升层（如一层→二层）"
            if major.stage_mode == "layers"
            else "同境升期（如初期→中期）"
        )
        base.update(
            {
                "advance_type": "layer",
                "advance_type_label_zh": type_zh,
                "to_stage": major_id,
                "to_stage_name": major.name,
                "to_layer": next_layer_cfg.stage,
                "to_layer_label": next_layer_cfg.label,
                "to_display": to_display,
                "success_rate": rate,
                "fail_progress_keep_ratio": cfg.layer_advance.fail_progress_keep_ratio,
            },
        )
        if progress < need:
            return {
                **base,
                "can_quench": False,
                "reason": f"淬体进度不足（{progress}/{need}）",
            }
        return {**base, "can_quench": True, "reason": None}

    # 本境圆满 → 下一炼体大境（扩境口：next_major）
    if not major.next_major:
        return {
            **base,
            "can_quench": False,
            "reason": f"已达{major.name}圆满（当前炼体链终点；后续扩境后可继续）",
            "advance_type_label_zh": "已达当前炼体链终点",
        }

    next_major = cfg.majors.get(major.next_major)
    if next_major is None:
        return {**base, "can_quench": False, "reason": "下境配置缺失"}

    first = next_major.stages[0]
    to_display = build_body_temper_display(next_major.name, first.label)
    rate = _clamp_rate(cfg.major_advance.success_rate, cfg.success_rate_clamp)
    base.update(
        {
            "advance_type": "major",
            "advance_type_label_zh": f"跨入下一炼体境（→{next_major.name}）",
            "to_stage": next_major.key,
            "to_stage_name": next_major.name,
            "to_layer": first.stage,
            "to_layer_label": first.label,
            "to_display": to_display,
            "success_rate": rate,
            "fail_progress_keep_ratio": cfg.major_advance.fail_progress_keep_ratio,
        },
    )

    if progress < need:
        return {
            **base,
            "can_quench": False,
            "reason": f"淬体进度不足（{progress}/{need}）",
        }

    if not stage_unlocked(
        character_major=str(character.major_realm),
        unlock_major=next_major.unlock_major,
        unlock_majors=cfg.unlock_majors,
    ):
        major_cfg = get_game_config().realms.get(next_major.unlock_major)
        unlock_label = major_cfg.name if major_cfg else next_major.unlock_major
        return {
            **base,
            "can_quench": False,
            "reason": f"主修须达{unlock_label}方可淬体至{next_major.name}",
        }

    return {**base, "can_quench": True, "reason": None}


def attempt_quench(
    character: Any,
    *,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """
    执行淬体（有成功率；失败按 keep_ratio 回退进度；无渡劫）。

    Args:
        character: 角色 ORM。
        rng: 可选随机源（单测注入）。

    Returns:
        dict: success / message / roll 信息 / from/to。
    """
    ready = quench_readiness(character)
    if not ready["can_quench"]:
        return {
            **ready,
            "success": False,
            "message": str(ready.get("reason") or "不可淬体"),
            "rolled": None,
        }

    roller = rng if rng is not None else random.Random()
    rate = float(ready["success_rate"])
    roll = roller.random()
    success = roll < rate
    from_display = str(ready["from_display"])
    to_display = str(ready["to_display"])

    if not success:
        keep = float(ready["fail_progress_keep_ratio"])
        before = int(character.body_temper_progress)
        kept = int(before * keep)
        character.body_temper_progress = max(0, kept)
        return {
            **ready,
            "success": False,
            "message": f"淬体失败，进度保留 {kept}/{before}（目标原为{to_display}）",
            "rolled": roll,
            "progress_after_fail": kept,
        }

    character.body_temper_stage = str(ready["to_stage"])
    character.body_temper_layer = int(ready["to_layer"])
    character.body_temper_layer_label = str(ready["to_layer_label"])
    character.body_temper_progress = 0
    return {
        **ready,
        "success": True,
        "message": f"淬体成功，{from_display}→{to_display}",
        "rolled": roll,
        "from_display": from_display,
        "to_display": to_display,
    }


def build_body_temper_public(character: Any) -> dict[str, Any]:
    """
    组装角色面板炼体 / 淬体字段。

    Args:
        character: 角色 ORM。

    Returns:
        dict: 展示与进度字段。
    """
    from app.services.realm_config import get_game_config

    cfg = get_game_config().body_temper
    major_id, layer, label = _ensure_layer_fields(character, cfg)
    major = cfg.majors[major_id]
    layer_cfg = major.stage_by_number(layer)
    assert layer_cfg is not None
    progress = int(getattr(character, "body_temper_progress", 0) or 0)
    need = max(0, int(layer_cfg.progress_required))
    display = build_body_temper_display(major.name, label)
    ready = quench_readiness(character)

    capped = bool(
        not ready["can_quench"]
        and need > 0
        and progress >= need
        and "主修" in str(ready.get("reason") or ""),
    )
    at_chain_end = bool(
        not ready["can_quench"]
        and need > 0
        and progress >= need
        and "终点" in str(ready.get("reason") or ""),
    )

    if ready["can_quench"]:
        to_next = 0
        ratio = 1.0
        display_full = f"{display} · 可淬体至{ready.get('to_display')}"
    elif capped:
        to_next = 0
        ratio = 1.0
        display_full = str(ready.get("reason") or display)
    elif at_chain_end:
        to_next = None
        ratio = 1.0
        display_full = f"{display}（炼体链当前终点）"
    else:
        to_next = max(0, need - progress) if need > 0 else None
        ratio = 0.0 if need <= 0 else min(1.0, progress / need)
        display_full = display

    return {
        "body_temper_stage": major_id,
        "body_temper_stage_name": major.name,
        "body_temper_layer": layer,
        "body_temper_layer_label": label,
        "body_temper_progress": progress,
        "body_temper_to_next": to_next,
        "body_temper_progress_ratio": float(ratio),
        "body_temper_display": display_full,
        "body_temper_capped": capped,
        "body_temper_ready_to_quench": bool(ready["can_quench"]),
        "body_temper_next_stage_name": ready.get("to_display") or ready.get("to_stage_name"),
    }
