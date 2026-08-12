"""
阵法四象对抗结算（M3战斗成型设计.md §5.3 · S6）。

本模块只负责：
    - 环境 / 天气 / 效果三层 **对抗骰点与覆盖规则**；
    - 效果层面板 atk/hp 乘区；
    - ``resolved_content_id_for_side``（覆盖 → 生效 id，供载荷模块复用）。

环境 / 天气 **combat 载荷** 与战报 enrichment → ``layer_payloads``（M3-D07 解耦）。

纯度纪律：本模块不得 import FastAPI / SQLAlchemy / pydantic。
"""

from __future__ import annotations

from typing import Any

# 三层结算顺序（写死，保证战报稳定）：效果 → 环境 → 天气
LAYER_ORDER = ("effect", "environment", "weather")


def _counter_mul(counters: dict[str, dict[str, float]], own_id: str, other_id: str | None) -> float:
    """查克制系数：own 克 other 时 > 1；无记录 = 1.0。"""
    if not other_id:
        return 1.0
    return counters.get(own_id, {}).get(other_id, 1.0)


def resolve_layer(
    layer_name: str,
    attacker_layer: dict[str, Any] | None,
    defender_layer: dict[str, Any] | None,
    attacker_level: int,
    defender_level: int,
    counters: dict[str, dict[str, float]],
    rng: Any,
    dice_sides: int,
    *,
    attacker_dice_lo: int | None = None,
    attacker_dice_hi: int | None = None,
    defender_dice_lo: int | None = None,
    defender_dice_hi: int | None = None,
) -> dict[str, Any]:
    """
    结算四象中的一层（环境 / 天气 / 效果）。

    参数:
        layer_name: 层名（写入结果便于战报）。
        attacker_layer / defender_layer: 各方该层声明（``{id, force_apply, ...}``）；None 表示不参战。
        attacker_level / defender_level: 双方阵法等级。
        counters: 该层克制表。
        rng: 战斗种子随机源（平局中立列随机、掷骰均出自此）。
        dice_sides: 兼容回落骰面（无区间时用 1..dice_sides）。
        attacker_dice_lo/hi / defender_dice_lo/hi: 修为区间骰；缺省回落。

    返回:
        dict: ``{layer, coverage, ... attacker_dice, defender_dice}``。
    """
    atk_id = str(attacker_layer["id"]) if attacker_layer else None
    def_id = str(defender_layer["id"]) if defender_layer else None
    atk_force = bool(attacker_layer.get("force_apply")) if attacker_layer else False
    def_force = bool(defender_layer.get("force_apply")) if defender_layer else False

    result: dict[str, Any] = {
        "layer": layer_name,
        "attacker_id": atk_id,
        "defender_id": def_id,
        "attacker_score": None,
        "defender_score": None,
        "attacker_dice": None,
        "defender_dice": None,
        "coverage": "none",
        "resolved_full": None,
        "resolved_attacker_half": None,
        "resolved_defender_half": None,
        "resolved_neutral": None,
    }

    # 双方均未声明 → 该层为无
    if atk_id is None and def_id is None:
        return result

    # 双方都强制 → 互抵为无
    if atk_force and def_force:
        result["coverage"] = "cancelled"
        return result

    # 单方强制 → 无视比分覆盖全场
    if atk_force:
        result["coverage"] = "full_attacker"
        result["resolved_full"] = atk_id
        return result
    if def_force:
        result["coverage"] = "full_defender"
        result["resolved_full"] = def_id
        return result

    # 仅一方声明 → 直接覆盖全场
    if def_id is None:
        result["coverage"] = "full_attacker"
        result["resolved_full"] = atk_id
        return result
    if atk_id is None:
        result["coverage"] = "full_defender"
        result["resolved_full"] = def_id
        return result

    # 双方对抗：level × 克制 × 造诣(M3 恒 1.0 占位) × 修为区间骰
    atk_lo = int(attacker_dice_lo) if attacker_dice_lo is not None else 1
    atk_hi = int(attacker_dice_hi) if attacker_dice_hi is not None else int(dice_sides)
    def_lo = int(defender_dice_lo) if defender_dice_lo is not None else 1
    def_hi = int(defender_dice_hi) if defender_dice_hi is not None else int(dice_sides)
    if atk_hi < atk_lo:
        atk_hi = atk_lo
    if def_hi < def_lo:
        def_hi = def_lo
    atk_dice = rng.randint(atk_lo, atk_hi)
    def_dice = rng.randint(def_lo, def_hi)
    atk_score = attacker_level * _counter_mul(counters, atk_id, def_id) * 1.0 * atk_dice
    def_score = defender_level * _counter_mul(counters, def_id, atk_id) * 1.0 * def_dice
    result["attacker_dice"] = atk_dice
    result["defender_dice"] = def_dice
    result["attacker_dice_lo"] = atk_lo
    result["attacker_dice_hi"] = atk_hi
    result["defender_dice_lo"] = def_lo
    result["defender_dice_hi"] = def_hi
    result["attacker_score"] = atk_score
    result["defender_score"] = def_score

    if atk_score > def_score:
        result["coverage"] = "full_attacker"
        result["resolved_full"] = atk_id
    elif def_score > atk_score:
        result["coverage"] = "full_defender"
        result["resolved_full"] = def_id
    else:
        # 比分相同：各自半区用己方；中立列 x=3 用 battle seed 二选一
        result["coverage"] = "split"
        result["resolved_attacker_half"] = atk_id
        result["resolved_defender_half"] = def_id
        result["resolved_neutral"] = atk_id if rng.randint(0, 1) == 0 else def_id
    return result


def resolve_battlefield(
    attacker_formation: dict[str, Any] | None,
    defender_formation: dict[str, Any] | None,
    counters_by_layer: dict[str, dict[str, dict[str, float]]],
    rng: Any,
    dice_sides: int,
    *,
    attacker_dice_lo: int | None = None,
    attacker_dice_hi: int | None = None,
    defender_dice_lo: int | None = None,
    defender_dice_hi: int | None = None,
) -> list[dict[str, Any]]:
    """
    按固定顺序结算三层四象对抗。

    参数:
        attacker_formation / defender_formation: 阵法定义的普通 dict 形态。
        counters_by_layer: 各层克制表。
        rng: 战斗随机源。
        dice_sides: 兼容回落骰面。
        attacker_dice_* / defender_dice_*: 双方修为区间。

    返回:
        list[dict]: 每层一条结算结果（机读；中文 enrichment 见 ``layer_payloads``）。
    """
    atk = attacker_formation or {}
    dfd = defender_formation or {}
    results: list[dict[str, Any]] = []
    for layer_name in LAYER_ORDER:
        results.append(
            resolve_layer(
                layer_name,
                atk.get(layer_name),
                dfd.get(layer_name),
                int(atk.get("level", 0)),
                int(dfd.get("level", 0)),
                counters_by_layer.get(layer_name, {}),
                rng,
                dice_sides,
                attacker_dice_lo=attacker_dice_lo,
                attacker_dice_hi=attacker_dice_hi,
                defender_dice_lo=defender_dice_lo,
                defender_dice_hi=defender_dice_hi,
            ),
        )
    return results


def resolved_content_id_for_side(
    layer_result: dict[str, Any],
    side: int,
) -> str | None:
    """
    按覆盖规则取某一侧生效的内容 id（环境 / 天气 / 效果通用）。

    参数:
        layer_result: 单层 ``resolve_layer`` 结果。
        side: ``0`` 进攻方 / ``1`` 防守方。

    返回:
        生效 id；无 / 互抵时为 None。
    """
    coverage = layer_result.get("coverage")
    if coverage == "full_attacker":
        return layer_result.get("resolved_full")
    if coverage == "full_defender":
        return layer_result.get("resolved_full")
    if coverage == "split":
        if side == 0:
            return layer_result.get("resolved_attacker_half")
        return layer_result.get("resolved_defender_half")
    return None


def effect_multipliers_for_side(
    layer_results: list[dict[str, Any]],
    attacker_formation: dict[str, Any] | None,
    defender_formation: dict[str, Any] | None,
    side: int,
) -> tuple[float, float]:
    """
    根据效果层结算结果，取某一侧单位应套用的 (atk_mul, hp_mul)。

    覆盖全场 → 赢家效果作用于双方；平局 split → 各自半区用己方效果
    （单位开战时都在己方半区，按所属侧套用）。
    """
    effect_result = next(
        (item for item in layer_results if item["layer"] == "effect"),
        None,
    )
    if effect_result is None:
        return 1.0, 1.0

    def _muls(formation: dict[str, Any] | None) -> tuple[float, float]:
        """从阵法定义抽取效果层乘区。"""
        if not formation or not formation.get("effect"):
            return 1.0, 1.0
        eff = formation["effect"]
        return float(eff.get("atk_mul", 1.0)), float(eff.get("hp_mul", 1.0))

    content_side = side
    # 全场覆盖时双方都吃赢家阵法行内乘区；split 才按所属侧
    coverage = effect_result["coverage"]
    if coverage == "full_attacker":
        return _muls(attacker_formation)
    if coverage == "full_defender":
        return _muls(defender_formation)
    if coverage == "split":
        return _muls(attacker_formation if content_side == 0 else defender_formation)
    # none / cancelled → 无效果
    return 1.0, 1.0
