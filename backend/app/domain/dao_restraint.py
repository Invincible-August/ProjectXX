"""
大道上位克制查询纯函数。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class DaoRestraintEdge:
    """一条克制边。"""

    attacker: str
    defender: str
    damage_mul: float
    label_zh: str


def find_restraint(
    edges: Sequence[DaoRestraintEdge],
    *,
    attacker_dao_id: str | None,
    defender_dao_id: str | None,
) -> DaoRestraintEdge | None:
    """
    查找攻方道对守方道的克制边。

    Args:
        edges: 克制表。
        attacker_dao_id: 攻方本命/运用道。
        defender_dao_id: 守方本命道。

    Returns:
        匹配边或 None。
    """
    if not attacker_dao_id or not defender_dao_id:
        return None
    for edge in edges:
        if edge.attacker == attacker_dao_id and edge.defender == defender_dao_id:
            return edge
    return None


def restraint_battle_event(
    edge: DaoRestraintEdge,
    *,
    attacker_label: str,
    defender_label: str,
) -> dict:
    """
    构造战报事件（机读英文 type + 中文文案）。

    Args:
        edge: 克制边。
        attacker_label: 攻方道中文名。
        defender_label: 守方道中文名。

    Returns:
        事件 dict。
    """
    mul = float(edge.damage_mul)
    text = f"{attacker_label} 克制 {defender_label}（伤害×{mul:.2f}）"
    return {
        "type": "dao_restraint",
        "subtype": "apex",
        "attacker_dao_id": edge.attacker,
        "defender_dao_id": edge.defender,
        "damage_mul": mul,
        "label_zh": edge.label_zh,
        "battle_text": text,
        "summary": text,
    }


def index_edges(edges: Sequence[DaoRestraintEdge]) -> Mapping[tuple[str, str], DaoRestraintEdge]:
    """(attacker, defender) → edge。"""
    return {(e.attacker, e.defender): e for e in edges}
