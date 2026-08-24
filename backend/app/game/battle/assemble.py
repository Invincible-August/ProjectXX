"""
开战组装：Character 门面 → 引擎 setup unit dict（S1-2）。

产出字段与现行 AutochessService._attacker_units 对齐（atk/hp/side/uid 前缀）。
"""

from __future__ import annotations

from typing import Any

from app.constants.battle import (
    ATTACKER_UID_PREFIX,
    BATTLE_SIDE_ATTACKER,
    BATTLE_SIDE_DEFENDER,
    DEFENDER_UID_PREFIX,
    MIN_COMBAT_STAT,
    PIECE_KIND_MAIN,
    PIECE_KIND_MONSTER,
    PIECE_KIND_PUPPET,
    TRIAL_PUPPET_UID_PREFIX,
)
from app.game.battle.seed import BattleUnitSeed
from app.game.character.base import Character


def engine_atk_hp_from_seed(seed: BattleUnitSeed) -> tuple[int, int]:
    """
    自 BattleUnitSeed 提取引擎 atk/hp（兼容 phys_atk 与旧 atk 键）。

    Args:
        seed: 开战种子。

    Returns:
        tuple[int, int]: (atk, hp)，均至少为 MIN_COMBAT_STAT（hp 允许已由上游保证）。
    """
    stats = seed.stats or {}
    atk = int(stats.get("phys_atk") or stats.get("atk") or 0)
    hp = int(stats.get("hp") or 0)
    return max(MIN_COMBAT_STAT, atk), max(MIN_COMBAT_STAT, hp)


def seed_to_engine_unit(
    seed: BattleUnitSeed,
    *,
    defaults: Any,
    dice_payload: dict[str, Any] | None = None,
    name: str | None = None,
    side: int | None = None,
    uid: str | None = None,
) -> dict[str, Any]:
    """
    将领域种子转为现行 ``simulate_battle`` 单位 dict。

    Args:
        seed: Character.on_battle_enter 产出。
        defaults: board.unit_defaults 行（需 speed/attack_range/attack_kind/can_fly）。
        dice_payload: 修为骰区间载荷。
        name: 覆盖显示名。
        side: 覆盖 side（默认按攻守前缀推断）。
        uid: 覆盖完整 uid（默认 a_/d_ + unit_uid）。

    Returns:
        dict[str, Any]: 引擎单位行。
    """
    atk, hp = engine_atk_hp_from_seed(seed)
    resolved_side = (
        int(side)
        if side is not None
        else (
            BATTLE_SIDE_ATTACKER
            if seed.side in {"attacker", str(BATTLE_SIDE_ATTACKER)}
            else BATTLE_SIDE_DEFENDER
        )
    )
    if uid is not None:
        resolved_uid = uid
    elif resolved_side == BATTLE_SIDE_ATTACKER:
        resolved_uid = f"{ATTACKER_UID_PREFIX}{seed.unit_uid}"
    else:
        resolved_uid = f"{DEFENDER_UID_PREFIX}{seed.unit_uid}"

    speed = int(seed.stats.get("speed") or getattr(defaults, "speed", 10))
    row: dict[str, Any] = {
        "uid": resolved_uid,
        "kind": seed.unit_kind,
        "name": name or (seed.meta or {}).get("name") or seed.unit_kind,
        "side": resolved_side,
        "x": int(seed.x),
        "y": int(seed.y),
        "atk": atk,
        "hp": hp,
        "speed": speed,
        "attack_range": getattr(defaults, "attack_range", 1),
        "attack_kind": getattr(defaults, "attack_kind", "melee"),
        "can_fly": bool(getattr(defaults, "can_fly", False)),
    }
    if dice_payload:
        row.update(dice_payload)
    return row


def scale_atk_hp(base_atk: int, base_hp: int, *, atk_ratio: float, hp_ratio: float) -> tuple[int, int]:
    """
    按 board 比例折算派生棋子战力，并施加下限。

    Args:
        base_atk: 本体物攻。
        base_hp: 本体生命。
        atk_ratio: 攻击比例。
        hp_ratio: 生命比例。

    Returns:
        tuple[int, int]: (atk, hp)。
    """
    return (
        max(MIN_COMBAT_STAT, int(base_atk * atk_ratio)),
        max(MIN_COMBAT_STAT, int(base_hp * hp_ratio)),
    )


def is_trial_puppet_uid(unit_uid: str) -> bool:
    """是否为试炼木傀 unit_uid（``puppet_1`` … ``puppet_N``，后缀须为纯数字）。"""
    raw = str(unit_uid)
    if not raw.startswith(TRIAL_PUPPET_UID_PREFIX):
        return False
    suffix = raw[len(TRIAL_PUPPET_UID_PREFIX) :]
    return bool(suffix) and suffix.isdigit()


def build_scaled_puppet_seed(
    *,
    unit_uid: str,
    side: str,
    x: int,
    y: int,
    main_atk: int,
    main_hp: int,
    atk_ratio: float,
    hp_ratio: float,
    speed: int,
    label_zh: str,
    ephemeral: bool,
) -> BattleUnitSeed:
    """由本体战力比例构造傀儡种子（真傀/试炼共用路径）。"""
    atk, hp = scale_atk_hp(main_atk, main_hp, atk_ratio=atk_ratio, hp_ratio=hp_ratio)
    from app.game.character.puppet import PuppetCharacter

    puppet = PuppetCharacter(
        def_id=unit_uid,
        stats={"hp": hp, "phys_atk": atk, "speed": speed, "mp": 0},
        ephemeral=ephemeral,
        label_zh=label_zh,
    )
    return puppet.on_battle_enter(unit_uid=unit_uid, side=side, x=x, y=y)


# 再导出常用 kind，减少 assemble 调用方魔法字面量
__all__ = [
    "engine_atk_hp_from_seed",
    "seed_to_engine_unit",
    "scale_atk_hp",
    "is_trial_puppet_uid",
    "build_scaled_puppet_seed",
    "PIECE_KIND_MAIN",
    "PIECE_KIND_PUPPET",
    "PIECE_KIND_MONSTER",
    "BATTLE_SIDE_ATTACKER",
    "BATTLE_SIDE_DEFENDER",
]
