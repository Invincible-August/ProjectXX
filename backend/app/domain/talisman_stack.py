"""符箓同种类不叠加：取最高优先使用，低效果张仍消耗。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class TalismanLayer:
    """一张已装备符箓解析后的叠层描述。"""

    inventory_item_id: int
    effect_id: str
    stack_group: str
    magnitude: float
    duration_kind: str  # global / attacks / rounds
    duration: int
    attr: str
    trigger: str
    label_zh: str
    use_chance: float
    hit_chance: float
    kind: str  # buff / offensive / curse


def parse_talisman_layer(payload: Mapping[str, Any], effect: Mapping[str, Any] | Any) -> TalismanLayer:
    """
    Combine inventory preload row with effect whitelist into a layer.

    Args:
        payload: peek_preloaded_talismans 单项。
        effect: TalismanEffectDef 或等价 mapping。
    """
    def _get(name: str, default: Any = None) -> Any:
        if isinstance(effect, Mapping):
            return effect.get(name, default)
        return getattr(effect, name, default)

    effect_id = str(payload.get("effect_id") or _get("effect_id") or "")
    stack_group = str(_get("stack_group") or effect_id or "ungrouped")
    duration_kind = str(_get("duration_kind") or "global")
    kind = str(_get("kind") or "buff")
    return TalismanLayer(
        inventory_item_id=int(payload.get("inventory_item_id") or 0),
        effect_id=effect_id,
        stack_group=stack_group,
        magnitude=float(_get("magnitude") or 0.0),
        duration_kind=duration_kind,
        duration=int(_get("duration") or 0),
        attr=str(_get("attr") or "phys_atk"),
        trigger=str(payload.get("trigger") or _get("trigger") or "battle_start"),
        label_zh=str(payload.get("label_zh") or _get("label_zh") or effect_id),
        use_chance=float(_get("use_chance") or 0.0),
        hit_chance=float(_get("hit_chance") or 1.0),
        kind=kind,
    )


def resolve_stack_groups(layers: Sequence[TalismanLayer]) -> dict[str, list[TalismanLayer]]:
    """
    Group layers; each group sorted by magnitude desc then duration_kind priority.

    同组全部计入消耗名单；生效层见 ``active_layers_for_group``。
    """
    grouped: dict[str, list[TalismanLayer]] = {}
    for layer in layers:
        grouped.setdefault(layer.stack_group, []).append(layer)
    for group, rows in grouped.items():
        grouped[group] = sorted(
            rows,
            key=lambda row: (-row.magnitude, _duration_rank(row), -row.duration),
        )
    return grouped


def _duration_rank(layer: TalismanLayer) -> int:
    """global 优先于有限次数/回合，便于取最高覆盖。"""
    if layer.duration_kind == "global":
        return 0
    if layer.duration_kind == "rounds":
        return 1
    return 2


def active_layers_for_group(rows: Sequence[TalismanLayer]) -> list[TalismanLayer]:
    """
    同种类不叠加：当前生效集合。

    - 最高 magnitude 先生效。
    - 若最高是有限次数/回合，其耗尽后回落到组内次高（含全局）。
    - 全局与有限层并存时，全程至少保有全局 magnitude（不会被更低的有限层压下去）。
    """
    if not rows:
        return []
    ordered = list(rows)
    best = ordered[0]
    keep: list[TalismanLayer] = [best]
    globals_ = [row for row in ordered[1:] if row.duration_kind == "global"]
    if best.duration_kind != "global" and globals_:
        # 有限层耗尽后的保底；若保底 magnitude 更低，仍作为 fallback 保留
        keep.append(globals_[0])
    return keep


def current_magnitude(
    active: Sequence[TalismanLayer],
    *,
    attacks_used: int = 0,
    rounds_elapsed: int = 0,
) -> float:
    """
    当前仍有效的最高 magnitude。

    例：+30% 攻（3 次攻击）与 +15% 全局 → 前三次 30%，之后 15%。
    例：+10% 攻 3 回合与 +15% 全局 → 全程至少 15%。
    """
    best = 0.0
    for layer in active:
        if layer.duration_kind == "attacks" and attacks_used >= max(0, layer.duration):
            continue
        if layer.duration_kind == "rounds" and rounds_elapsed >= max(0, layer.duration):
            continue
        if layer.magnitude > best:
            best = layer.magnitude
    return best


def consume_ids(layers: Sequence[TalismanLayer]) -> list[int]:
    """同组全部装备的符箓都消耗，不论是否为当前生效层。"""
    return [layer.inventory_item_id for layer in layers if layer.inventory_item_id]
