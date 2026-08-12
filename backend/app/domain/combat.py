"""
战力领域：境界底 × 品阶倍 × 功法/体质加算；ATTR CombatAttrBlock / LifeAttrBlock。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CombatStats:
    """最终战力与面板摘要组件（兼容旧调用方）。"""

    atk: int
    hp: int


@dataclass(frozen=True)
class AttrDef:
    """单属性注册表项。"""

    key: str
    label_zh: str
    help_zh: str
    category: str
    engine: bool = False
    panel: bool = True
    formula_enabled: bool = True
    default: float = 0.0


# 战斗 final 核心键（含抗性）；别名另附
COMBAT_FINAL_KEYS: tuple[str, ...] = (
    "hp",
    "phys_atk",
    "phys_def",
    "magic_atk",
    "magic_def",
    "speed",
    "mp",
    "hit",
    "dodge",
    "resist_metal",
    "resist_wood",
    "resist_water",
    "resist_fire",
    "resist_earth",
    "resist_wind",
    "resist_thunder",
)

PRIMARY_KEYS: tuple[str, ...] = (
    "strength",
    "agility",
    "intelligence",
    "comprehension",
    "bone_root",
)

LIFE_KEYS: tuple[str, ...] = (
    "comprehension",
    "stamina",
    "resist_heart_demon",
    "resist_tribulation",
    "breath_efficiency",
    "endurance",
    "craft_dexterity",
    "precision",
    "temperament",
)


class CombatCalculator:
    """
    战力纯计算器（无 DB IO）。

    调用方负责查询品阶倍率与功法/体质加算后再传入。
    """

    @staticmethod
    def compute(
        *,
        base_atk: int,
        base_hp: int,
        grade_atk_mul: float = 1.0,
        grade_hp_mul: float = 1.0,
        technique_atk: int = 0,
        technique_hp: int = 0,
        constitution_atk: int = 0,
        constitution_hp: int = 0,
    ) -> CombatStats:
        """
        计算含品阶/功法/体质修正后的 atk/hp。

        品阶倍率先作用于境界底数，再叠加算。

        Args:
            base_atk: 境界基础攻击。
            base_hp: 境界基础生命。
            grade_atk_mul: 品阶攻击倍率。
            grade_hp_mul: 品阶生命倍率。
            technique_atk: 功法攻击加算。
            technique_hp: 功法生命加算。
            constitution_atk: 体质攻击加算。
            constitution_hp: 体质生命加算。

        Returns:
            CombatStats: 最终 atk / hp。
        """
        graded_atk = int(base_atk * grade_atk_mul)
        graded_hp = int(base_hp * grade_hp_mul)
        return CombatStats(
            atk=graded_atk + technique_atk + constitution_atk,
            hp=graded_hp + technique_hp + constitution_hp,
        )


@dataclass
class CombatAttrAssembleInput:
    """组装 CombatAttrBlock 所需的已解析贡献源。"""

    realm_phys_atk: int
    realm_hp: int
    realm_speed: int
    rein_mult: float
    grade_atk_mul: float
    grade_hp_mul: float
    technique_phys_atk: int = 0
    technique_hp: int = 0
    constitution_phys_atk: int = 0
    constitution_hp: int = 0
    primary: dict[str, int] = field(default_factory=dict)
    primary_map: dict[str, dict[str, float]] = field(default_factory=dict)
    defaults: dict[str, float] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    channels: dict[str, dict[str, Any]] = field(default_factory=dict)
    schema_version: int = 2
    entity_kind: str = "player"
    growth: dict[str, Any] | None = None


def _floor_num(value: float) -> int:
    """向下取整为 int（对负值仍用 int 截断，占位非负）。"""
    return int(value)


def map_primary_deltas(
    primary: dict[str, int],
    primary_map: dict[str, dict[str, float]],
) -> dict[str, float]:
    """
    将主键经配置系数映射为战斗键加算。

    Args:
        primary: 主键当前值。
        primary_map: 主键 → {战斗键: 系数}。

    Returns:
        dict[str, float]: 战斗键加算量（未取整）。
    """
    deltas: dict[str, float] = {}
    for pk, coeff_map in primary_map.items():
        base = float(primary.get(pk, 0) or 0)
        if not isinstance(coeff_map, dict):
            continue
        for combat_key, coeff in coeff_map.items():
            deltas[str(combat_key)] = deltas.get(str(combat_key), 0.0) + base * float(coeff)
    return deltas


def assemble_combat_attr_block(inp: CombatAttrAssembleInput) -> dict[str, Any]:
    """
    按 ATTR 叠层顺序组装 CombatAttrBlock（dict，可直接进 CharacterPublic）。

    公式占位::
        graded = floor(realm_base × rein_mult × grade_mul)
        final  = max(floor_min, graded + primary_map + Σ additive)

    Args:
        inp: 已解析贡献源。

    Returns:
        dict: schema_version / final / primary / labels / breakdown / growth。
    """
    # 步骤 1～2：境界底 × 轮回
    rein_atk = _floor_num(inp.realm_phys_atk * inp.rein_mult)
    rein_hp = _floor_num(inp.realm_hp * inp.rein_mult)
    rein_speed = _floor_num(inp.realm_speed * inp.rein_mult)

    # 步骤 3：品阶倍
    graded_atk = _floor_num(rein_atk * inp.grade_atk_mul)
    graded_hp = _floor_num(rein_hp * inp.grade_hp_mul)
    graded_speed = max(1, rein_speed)

    # 步骤 4：主键映射
    primary_deltas = map_primary_deltas(inp.primary, inp.primary_map)
    primary_atk = _floor_num(primary_deltas.get("phys_atk", 0.0))
    primary_hp = _floor_num(primary_deltas.get("hp", 0.0))
    primary_speed = _floor_num(primary_deltas.get("speed", 0.0))
    primary_def = _floor_num(primary_deltas.get("phys_def", 0.0))
    primary_magic = _floor_num(primary_deltas.get("magic_atk", 0.0))
    primary_mp = _floor_num(primary_deltas.get("mp", 0.0))
    primary_hit = _floor_num(primary_deltas.get("hit", 0.0))
    primary_dodge = _floor_num(primary_deltas.get("dodge", 0.0))

    # 步骤 5～6：功法/体质加算（装备等通道关闭 → 0）
    phys_atk = max(
        0,
        graded_atk + primary_atk + inp.technique_phys_atk + inp.constitution_phys_atk,
    )
    hp = max(1, graded_hp + primary_hp + inp.technique_hp + inp.constitution_hp)
    speed = max(1, graded_speed + primary_speed)
    phys_def = max(0, _floor_num(float(inp.defaults.get("phys_def", 0))) + primary_def)
    magic_atk = max(0, _floor_num(float(inp.defaults.get("magic_atk", 0))) + primary_magic)
    magic_def = max(0, _floor_num(float(inp.defaults.get("magic_def", 0))))
    mp = max(0, _floor_num(float(inp.defaults.get("mp", 0))) + primary_mp)
    hit = max(0, _floor_num(float(inp.defaults.get("hit", 0))) + primary_hit)
    dodge = max(0, _floor_num(float(inp.defaults.get("dodge", 0))) + primary_dodge)

    resist_defaults = {
        k: _floor_num(float(inp.defaults.get(k, 0)))
        for k in (
            "resist_metal",
            "resist_wood",
            "resist_water",
            "resist_fire",
            "resist_earth",
            "resist_wind",
            "resist_thunder",
        )
    }

    final: dict[str, Any] = {
        "hp": hp,
        "phys_atk": phys_atk,
        "phys_def": phys_def,
        "magic_atk": magic_atk,
        "magic_def": magic_def,
        "speed": speed,
        "mp": mp,
        "hit": hit,
        "dodge": dodge,
        **resist_defaults,
        # 迁移期别名：引擎仍读 atk/defense
        "atk": phys_atk,
        "defense": phys_def,
    }

    labels = dict(inp.labels)
    if "atk" not in labels and "phys_atk" in labels:
        labels["atk"] = labels["phys_atk"]
    if "defense" not in labels and "phys_def" in labels:
        labels["defense"] = labels["phys_def"]

    breakdown: list[dict[str, Any]] = [
        {
            "source": "realm",
            "label_zh": "境界根基",
            "phys_atk": inp.realm_phys_atk,
            "hp": inp.realm_hp,
            "speed": inp.realm_speed,
        },
    ]
    if abs(inp.rein_mult - 1.0) > 1e-9:
        breakdown.append(
            {
                "source": "reincarnation",
                "label_zh": "轮回乘区",
                "combat_attr_multiplier": inp.rein_mult,
            },
        )
    breakdown.append(
        {
            "source": "grade",
            "label_zh": "突破品阶",
            "phys_atk_mul": inp.grade_atk_mul,
            "hp_mul": inp.grade_hp_mul,
        },
    )
    if any(v for v in primary_deltas.values()):
        breakdown.append(
            {
                "source": "primary_map",
                "label_zh": "根基映射",
                **{k: _floor_num(v) for k, v in primary_deltas.items() if abs(v) > 1e-9},
            },
        )
    if inp.technique_phys_atk or inp.technique_hp:
        breakdown.append(
            {
                "source": "technique",
                "label_zh": "功法",
                "phys_atk": inp.technique_phys_atk,
                "hp": inp.technique_hp,
            },
        )
    if inp.constitution_phys_atk or inp.constitution_hp:
        breakdown.append(
            {
                "source": "constitution",
                "label_zh": "体质",
                "phys_atk": inp.constitution_phys_atk,
                "hp": inp.constitution_hp,
            },
        )
    for ch_id, ch_body in inp.channels.items():
        enabled = bool(ch_body.get("enabled", False))
        breakdown.append(
            {
                "source": str(ch_id),
                "label_zh": str(ch_body.get("label_zh") or ch_id),
                "enabled": enabled,
                **(
                    {"note_zh": "通道未开启"}
                    if not enabled
                    else {}
                ),
            },
        )

    return {
        "schema_version": int(inp.schema_version),
        "entity_kind": inp.entity_kind,
        "final": final,
        "primary": {k: int(inp.primary.get(k, 0) or 0) for k in PRIMARY_KEYS},
        "labels": labels,
        "breakdown": breakdown,
        "growth": inp.growth or {},
    }


def assemble_life_attr_block(
    *,
    values: dict[str, float | int],
    labels: dict[str, str],
    schema_version: int = 2,
    breakdown: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    组装 LifeAttrBlock。

    Args:
        values: 生活键取值。
        labels: 中文 label。
        schema_version: schema 版本。
        breakdown: 可选来源拆解。

    Returns:
        dict: life 面板块。
    """
    final: dict[str, Any] = {}
    for key in LIFE_KEYS:
        raw = values.get(key, 0)
        if key == "breath_efficiency":
            final[key] = float(raw)
        else:
            final[key] = int(raw)
    life_labels = {k: labels[k] for k in LIFE_KEYS if k in labels}
    return {
        "schema_version": int(schema_version),
        "final": final,
        "labels": life_labels,
        "breakdown": list(breakdown or []),
    }
