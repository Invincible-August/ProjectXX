"""
战力领域：境界底 × 品阶倍 × 功法/体质加算；ATTR CombatAttrBlock / LifeAttrBlock。

叠层权威（与 ATTR 设计一致）::
    graded = floor(realm_base × rein_mult × grade_mul)
    after_primary = graded + map_primary(...)
    final = max(floor_min, after_primary + Σ additive_sources)
别名 ``atk``/``defense`` 仅迁移期读写映射，不另算一套数。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


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

# 对外摘要（道友卡/列表）子集；键名与 schema 一致，禁止 mag_atk 等缩写分叉
PUBLIC_COMBAT_SUMMARY_KEYS: tuple[str, ...] = (
    "phys_atk",
    "magic_atk",
    "hp",
    "phys_def",
    "magic_def",
    "speed",
)

# 引擎当前消费的核心键（物法公式未拆前 atk←phys_atk）
ENGINE_CORE_KEYS: tuple[str, ...] = ("hp", "phys_atk", "speed", "mp")

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

# 叠层后下限（hp/speed 至少 1；攻防等 ≥ 0）
FLOOR_MINS: dict[str, int] = {
    "hp": 1,
    "speed": 1,
}

# 默认迁移期别名（可被 YAML aliases 覆盖）
DEFAULT_ALIASES: dict[str, str] = {
    "atk": "phys_atk",
    "defense": "phys_def",
}


@dataclass(frozen=True)
class AdditiveSource:
    """
    一层加算贡献（功法 / 体质 / 装备通道等）。

    Attributes:
        source_id: breakdown.source 机读键。
        label_zh: 玩家可见来源名。
        amounts: 战斗键 → 加算量（已取整前可为 float）。
        enabled: 通道是否开启；关闭时仍可进 breakdown 提示。
        note_zh: 关闭或说明文案。
    """

    source_id: str
    label_zh: str
    amounts: Mapping[str, float] = field(default_factory=dict)
    enabled: bool = True
    note_zh: str | None = None


class CombatCalculator:
    """
    战力纯计算器（无 DB IO）。

    内部委托 ``assemble_combat_attr_block``，保证与 ATTR 面板同源。
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
        rein_mult: float = 1.0,
    ) -> CombatStats:
        """
        计算含品阶/功法/体质修正后的 atk/hp。

        Args:
            base_atk: 境界基础攻击（= phys_atk 源）。
            base_hp: 境界基础生命。
            grade_atk_mul: 品阶攻击倍率。
            grade_hp_mul: 品阶生命倍率。
            technique_atk: 功法攻击加算。
            technique_hp: 功法生命加算。
            constitution_atk: 体质攻击加算。
            constitution_hp: 体质生命加算。
            rein_mult: 轮回乘区（默认 1.0）。

        Returns:
            CombatStats: 最终 atk / hp。
        """
        block = assemble_combat_attr_block(
            CombatAttrAssembleInput(
                realm_phys_atk=base_atk,
                realm_hp=base_hp,
                realm_speed=1,
                rein_mult=rein_mult,
                grade_atk_mul=grade_atk_mul,
                grade_hp_mul=grade_hp_mul,
                additive_sources=(
                    AdditiveSource(
                        source_id="technique",
                        label_zh="功法",
                        amounts={"phys_atk": technique_atk, "hp": technique_hp},
                    ),
                    AdditiveSource(
                        source_id="constitution",
                        label_zh="体质",
                        amounts={"phys_atk": constitution_atk, "hp": constitution_hp},
                    ),
                ),
            ),
        )
        final = block["final"]
        return CombatStats(atk=int(final["phys_atk"]), hp=int(final["hp"]))


@dataclass
class CombatAttrAssembleInput:
    """组装 CombatAttrBlock 所需的已解析贡献源。"""

    realm_phys_atk: int
    realm_hp: int
    realm_speed: int
    rein_mult: float
    grade_atk_mul: float
    grade_hp_mul: float
    # 兼容旧字段：未传 additive_sources 时仍可从这两对拼一层
    technique_phys_atk: int = 0
    technique_hp: int = 0
    constitution_phys_atk: int = 0
    constitution_hp: int = 0
    additive_sources: tuple[AdditiveSource, ...] = ()
    primary: dict[str, int] = field(default_factory=dict)
    primary_map: dict[str, dict[str, float]] = field(default_factory=dict)
    defaults: dict[str, float] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)
    channels: dict[str, dict[str, Any]] = field(default_factory=dict)
    schema_version: int = 2
    entity_kind: str = "player"
    growth: dict[str, Any] | None = None
    # entity_profiles[kind] → 允许的 category 列表；空则不过滤 labels
    allowed_categories: tuple[str, ...] = ()
    attr_categories: dict[str, str] = field(default_factory=dict)


def _floor_num(value: float) -> int:
    """向下取整为 int（占位非负场景用 int 截断即可）。"""
    return int(value)


def _clamp_key(key: str, value: float) -> int:
    """按 FLOOR_MINS 钳制单键。"""
    floored = _floor_num(value)
    return max(FLOOR_MINS.get(key, 0), floored)


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
            ck = str(combat_key)
            deltas[ck] = deltas.get(ck, 0.0) + base * float(coeff)
    return deltas


def sum_additive_amounts(
    sources: tuple[AdditiveSource, ...] | list[AdditiveSource],
) -> dict[str, float]:
    """
    合并各加算层（仅 enabled=True 计入数值）。

    Args:
        sources: 加算层列表。

    Returns:
        dict[str, float]: 战斗键合计加算。
    """
    totals: dict[str, float] = {}
    for src in sources:
        if not src.enabled:
            continue
        for key, amount in src.amounts.items():
            totals[str(key)] = totals.get(str(key), 0.0) + float(amount)
    return totals


def apply_aliases(
    final: dict[str, Any],
    aliases: Mapping[str, str] | None = None,
    *,
    labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    写入迁移期别名键（别名值 = 规范键当前值）。

    Args:
        final: 规范键 final 字典（会被拷贝后返回）。
        aliases: 别名 → 规范键；默认 DEFAULT_ALIASES。
        labels: 可选；同步复制 label。

    Returns:
        dict: 含别名的 final。
    """
    out = dict(final)
    mapping = dict(aliases or DEFAULT_ALIASES)
    for alias, canonical in mapping.items():
        if canonical in out:
            out[alias] = out[canonical]
    if labels is not None:
        for alias, canonical in mapping.items():
            if alias not in labels and canonical in labels:
                labels[alias] = labels[canonical]
    return out


def engine_unit_core_from_final(final: Mapping[str, Any]) -> dict[str, int]:
    """
    自走棋/开战单位核心面板：hp/speed/mp + atk←phys_atk。

    Args:
        final: CombatAttrBlock.final。

    Returns:
        dict[str, int]: 引擎可读核心字段。
    """
    phys = int(final.get("phys_atk", final.get("atk", 0)) or 0)
    return {
        "hp": max(1, int(final.get("hp", 1) or 1)),
        "atk": max(0, phys),
        "phys_atk": max(0, phys),
        "speed": max(1, int(final.get("speed", 1) or 1)),
        "mp": max(0, int(final.get("mp", 0) or 0)),
    }


def public_combat_final_summary(final: Mapping[str, Any]) -> dict[str, int]:
    """
    道友卡等对外摘要：只暴露 PUBLIC_COMBAT_SUMMARY_KEYS（schema 规范键）。

    Args:
        final: CombatAttrBlock.final。

    Returns:
        dict[str, int]: 物/法攻防 + hp + speed。
    """
    return {k: int(final.get(k, 0) or 0) for k in PUBLIC_COMBAT_SUMMARY_KEYS}


def filter_labels_by_categories(
    labels: Mapping[str, str],
    *,
    attr_categories: Mapping[str, str],
    allowed_categories: tuple[str, ...] | list[str],
) -> dict[str, str]:
    """
    按 entity_profile 的 use_categories 裁剪面板 labels。

    Args:
        labels: 全量 label。
        attr_categories: 属性键 → category。
        allowed_categories: 允许的 category；空则原样返回。

    Returns:
        dict[str, str]: 裁剪后 labels。
    """
    if not allowed_categories:
        return dict(labels)
    allowed = set(allowed_categories)
    return {
        k: v
        for k, v in labels.items()
        if attr_categories.get(k, "") in allowed or k in DEFAULT_ALIASES
    }


def _legacy_additive_sources(inp: CombatAttrAssembleInput) -> tuple[AdditiveSource, ...]:
    """把旧 technique_/constitution_ 字段与显式 additive_sources 合并。"""
    layers: list[AdditiveSource] = list(inp.additive_sources)
    if inp.technique_phys_atk or inp.technique_hp:
        layers.append(
            AdditiveSource(
                source_id="technique",
                label_zh="功法",
                amounts={
                    "phys_atk": float(inp.technique_phys_atk),
                    "hp": float(inp.technique_hp),
                },
            ),
        )
    if inp.constitution_phys_atk or inp.constitution_hp:
        layers.append(
            AdditiveSource(
                source_id="constitution",
                label_zh="体质",
                amounts={
                    "phys_atk": float(inp.constitution_phys_atk),
                    "hp": float(inp.constitution_hp),
                },
            ),
        )
    # 关闭的装备等通道：仅展示，不计入数值
    for ch_id, ch_body in inp.channels.items():
        enabled = bool(ch_body.get("enabled", False))
        amounts_raw = ch_body.get("amounts") or {}
        amounts = {
            str(k): float(v)
            for k, v in amounts_raw.items()
            if isinstance(v, (int, float))
        }
        layers.append(
            AdditiveSource(
                source_id=str(ch_id),
                label_zh=str(ch_body.get("label_zh") or ch_id),
                amounts=amounts,
                enabled=enabled,
                note_zh=None if enabled else str(ch_body.get("note_zh") or "通道未开启"),
            ),
        )
    return tuple(layers)


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

    # 步骤 3：品阶倍（speed 暂无独立 grade_mul，沿用轮回后值）
    graded: dict[str, float] = {
        "phys_atk": float(_floor_num(rein_atk * inp.grade_atk_mul)),
        "hp": float(_floor_num(rein_hp * inp.grade_hp_mul)),
        "speed": float(max(1, rein_speed)),
    }
    # 其余战斗键从 defaults 起底（抗性/法攻等）
    for key in COMBAT_FINAL_KEYS:
        if key not in graded:
            graded[key] = float(inp.defaults.get(key, 0))

    # 步骤 4：主键映射（泛化加算到任意战斗键）
    primary_deltas = map_primary_deltas(inp.primary, inp.primary_map)
    after_primary: dict[str, float] = dict(graded)
    for key, delta in primary_deltas.items():
        after_primary[key] = after_primary.get(key, 0.0) + float(delta)

    # 步骤 5～7：加算层（功法/体质/已开启通道）
    layers = _legacy_additive_sources(inp)
    additive_totals = sum_additive_amounts(layers)
    merged: dict[str, float] = dict(after_primary)
    for key, delta in additive_totals.items():
        merged[key] = merged.get(key, 0.0) + float(delta)

    # 步骤 8：clamp
    final_core: dict[str, Any] = {
        key: _clamp_key(key, merged.get(key, 0.0)) for key in COMBAT_FINAL_KEYS
    }
    labels = dict(inp.labels)
    final = apply_aliases(
        final_core,
        aliases=inp.aliases or DEFAULT_ALIASES,
        labels=labels,
    )
    if inp.allowed_categories:
        labels = filter_labels_by_categories(
            labels,
            attr_categories=inp.attr_categories,
            allowed_categories=inp.allowed_categories,
        )

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
    if any(abs(v) > 1e-9 for v in primary_deltas.values()):
        breakdown.append(
            {
                "source": "primary_map",
                "label_zh": "根基映射",
                **{k: _floor_num(v) for k, v in primary_deltas.items() if abs(v) > 1e-9},
            },
        )
    for src in layers:
        row: dict[str, Any] = {
            "source": src.source_id,
            "label_zh": src.label_zh,
            "enabled": src.enabled,
        }
        if src.note_zh:
            row["note_zh"] = src.note_zh
        if src.enabled:
            for k, v in src.amounts.items():
                if abs(float(v)) > 1e-9:
                    row[str(k)] = _floor_num(float(v))
        # 关闭通道也进 breakdown（显性 §0.7）；无数值时仍保留 enabled/note
        if src.enabled and not any(
            abs(float(v)) > 1e-9 for v in src.amounts.values()
        ):
            # 无贡献的开启层跳过（避免空功法行）
            if src.source_id in {"technique", "constitution"}:
                continue
        breakdown.append(row)

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
