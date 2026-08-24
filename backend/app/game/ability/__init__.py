"""
Ability 定义与实例（配置驱动特效正文）。

一期仅数据结构 + 展开骨架；战斗触发解释器见 R4 / M3-D03。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# 冻结枚举（与设计文档对齐；权威在 app.constants.ability）
from app.constants.ability import ABILITY_DOMAINS, ABILITY_KINDS


@dataclass(frozen=True)
class AbilityDef:
    """
    单条能力定义（对应 abilities.yaml 一行）。

    Attributes:
        ability_id: 稳定机读 id。
        label_zh: 中文名。
        domain: 作用域。
        kind: 形态。
        trigger: 触发器（trigger/aura 时有意义）。
        ops: 效果算子列表。
        stackable: 同 id 多来源是否叠层；默认 False。
        chance: 触发概率（0~1）。
        icd_rounds: 内置冷却回合。
        max_per_battle: 场次触发上限。
    """

    ability_id: str
    label_zh: str
    domain: str
    kind: str
    trigger: str | None = None
    ops: tuple[dict[str, Any], ...] = ()
    stackable: bool = False
    chance: float | None = None
    icd_rounds: int | None = None
    max_per_battle: int | None = None

    @classmethod
    def from_mapping(cls, ability_id: str, raw: dict[str, Any]) -> AbilityDef:
        """
        自配置 dict 构建。

        Args:
            ability_id: 键名。
            raw: YAML/DB 行。

        Returns:
            AbilityDef: 校验后的定义。

        Raises:
            ValueError: domain/kind 非法。
        """
        domain = str(raw.get("domain", "combat"))
        kind = str(raw.get("kind", "stat_mod"))
        if domain not in ABILITY_DOMAINS:
            raise ValueError(f"invalid ability domain: {domain}")
        if kind not in ABILITY_KINDS:
            raise ValueError(f"invalid ability kind: {kind}")
        ops_raw = raw.get("ops") or []
        if not isinstance(ops_raw, list):
            raise ValueError("ability ops must be a list")
        return cls(
            ability_id=ability_id,
            label_zh=str(raw.get("label_zh") or ability_id),
            domain=domain,
            kind=kind,
            trigger=raw.get("trigger"),
            ops=tuple(ops_raw),
            stackable=bool(raw.get("stackable", False)),
            chance=float(raw["chance"]) if raw.get("chance") is not None else None,
            icd_rounds=int(raw["icd_rounds"]) if raw.get("icd_rounds") is not None else None,
            max_per_battle=(
                int(raw["max_per_battle"]) if raw.get("max_per_battle") is not None else None
            ),
        )


@dataclass
class AbilityInstance:
    """运行时授予实例（装配期展开结果）。"""

    ability_id: str
    source_type: str
    source_id: str
    defn: AbilityDef | None = None
    runtime: dict[str, Any] = field(default_factory=dict)


@dataclass
class SimpleGrantSource:
    """
    最小 GrantSource 实现（测试与过渡期占位）。

    正式装备/功法应使用专用 Component。
    """

    source_type: str
    source_id: str
    ability_ids: list[str] = field(default_factory=list)

    def list_ability_ids(self) -> list[str]:
        """返回配置的 ability id 列表。"""
        return list(self.ability_ids)


def expand_grants(
    sources: list[Any],
    *,
    ability_catalog: dict[str, AbilityDef] | None = None,
) -> list[AbilityInstance]:
    """
    展开授予列表；同 ability_id 默认不叠（取先到）。

    Args:
        sources: 授予源序列（需有 source_type/source_id/list_ability_ids）。
        ability_catalog: 可选定义表；缺省时 instance.defn 为 None。

    Returns:
        list[AbilityInstance]: 去重后的实例。
    """
    catalog = ability_catalog or {}
    seen: set[str] = set()
    out: list[AbilityInstance] = []
    for src in sources:
        for aid in src.list_ability_ids():
            defn = catalog.get(aid)
            stackable = bool(defn.stackable) if defn is not None else False
            if not stackable and aid in seen:
                continue
            seen.add(aid)
            out.append(
                AbilityInstance(
                    ability_id=aid,
                    source_type=src.source_type,
                    source_id=src.source_id,
                    defn=defn,
                ),
            )
    return out
