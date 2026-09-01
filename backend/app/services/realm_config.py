"""
境界 / 挂机 / 突破 / 怪物 / M2 扩展配置加载（M1 + M2）。

启动时或首次访问时加载 ``app/config_data/*.yaml``；失败应 ERROR 并抛出。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from app.core.config import get_settings
from app.constants.avatar import (
    AVATAR_DEFAULT_LEAD_MAJORS,
    AVATAR_DEFAULT_MAX_MAJOR_REALM,
    AVATAR_FORBIDDEN_IDENTITY_REALMS,
)
from app.constants.inventory import (
    INSPECT_REALM_NONE_ZH,
    USE_EFFECT_KIND_LABEL_ZH,
    normalize_inspect_element,
)

if TYPE_CHECKING:
    from app.domain.formation_blueprint import (
        DeployConfig,
        ForceShiftRule,
        TerrainLayoutConfig,
    )

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config_data"

STAGE_LABEL_NAMES: dict[str, str] = {
    "layer_1": "一层",
    "layer_2": "二层",
    "layer_3": "三层",
    "layer_4": "四层",
    "layer_5": "五层",
    "layer_6": "六层",
    "layer_7": "七层",
    "layer_8": "八层",
    "layer_9": "九层",
    "perfection": "圆满",
    "early": "初期",
    "middle": "中期",
    "late": "后期",
}

IDLE_DIRECTION_NAMES: dict[str, str] = {
    "none": "空闲",
    "spirit": "修炼",
    "body": "淬体",
    "crafting": "制造业修炼",
    "sect_mining": "采矿",
}

STATUS_NAMES: dict[str, str] = {
    "normal": "正常",
    "epiphany": "顿悟",
    "weak": "虚弱",
    "poisoned": "中毒",
    "demonic": "入魔",
    "confused": "混乱",
    "fatigued": "疲劳",
    "breaking_through": "进阶中",
    "tribulation": "渡劫中",
    "awaiting_ferry": "待引渡",
    "reincarnating": "轮回中",
}


@dataclass(frozen=True)
class RealmStageConfig:
    """单一境界档位配置。"""

    stage: int
    label: str
    cultivation_required: int
    base_atk: int
    base_hp: int


@dataclass(frozen=True)
class MajorRealmConfig:
    """大境界配置。"""

    key: str
    name: str
    stage_mode: str
    next_major: str | None
    stages: tuple[RealmStageConfig, ...]

    def stage_by_number(self, stage: int) -> RealmStageConfig | None:
        """按 ``realm_stage`` 数字查找档位。"""
        for item in self.stages:
            if item.stage == stage:
                return item
        return None

    def max_stage(self) -> int:
        """当前大境界最大 stage 数字。"""
        return max(item.stage for item in self.stages)


@dataclass(frozen=True)
class BodyTemperLayerConfig:
    """炼体大境内单一层/期。"""

    stage: int
    label: str
    progress_required: int


@dataclass(frozen=True)
class BodyTemperMajorConfig:
    """炼体大境（炼皮/锻骨/…/道体）。"""

    key: str
    name: str
    stage_mode: str
    unlock_major: str
    next_major: str | None
    stages: tuple[BodyTemperLayerConfig, ...]

    def stage_by_number(self, stage: int) -> BodyTemperLayerConfig | None:
        """按层/期编号查找。"""
        for item in self.stages:
            if item.stage == stage:
                return item
        return None

    def max_stage(self) -> int:
        """本境最大层/期编号。"""
        return max(item.stage for item in self.stages)


@dataclass(frozen=True)
class BodyTemperQuenchRule:
    """淬体尝试规则（成功率 + 失败保留进度比）。"""

    success_rate: float
    fail_progress_keep_ratio: float


@dataclass(frozen=True)
class BodyTemperConfig:
    """炼体大境总表 + 淬体规则（可扩 next_major）。"""

    unlock_majors: tuple[str, ...]
    majors: dict[str, BodyTemperMajorConfig]
    default_major_id: str
    layer_advance: BodyTemperQuenchRule
    major_advance: BodyTemperQuenchRule
    success_rate_clamp: tuple[float, float]

    def get_major(self, key: str) -> BodyTemperMajorConfig | None:
        """按炼体大境 id 查询。"""
        return self.majors.get(key)


@dataclass(frozen=True)
class DirectionRates:
    """单一挂机方向的速率配置。"""

    enabled: bool
    gain_per_tick: int
    default_stones_per_tick: int | None


@dataclass(frozen=True)
class IdleBonusChannel:
    """挂机加成通道（内部/外部；无实例时用 default_mult）。"""

    channel_id: str
    enabled: bool
    default_mult: float


@dataclass(frozen=True)
class IdleConfig:
    """挂机全局配置（M2 三向 + 境界基础表 + 加成通道）。"""

    tick_seconds: int
    cost_by_realm: dict[str, int]
    spirit: DirectionRates
    body: DirectionRates
    crafting: DirectionRates
    # direction → major_realm → gain_per_tick（缺省回落 DirectionRates.gain_per_tick）
    gain_by_realm: dict[str, dict[str, int]]
    bonus_channels: dict[str, IdleBonusChannel]
    clamp_min: float
    clamp_max: float

    @property
    def body_enabled(self) -> bool:
        """炼体方向是否开放。"""
        return self.body.enabled

    @property
    def crafting_enabled(self) -> bool:
        """制造业方向是否开放。"""
        return self.crafting.enabled

    def direction_rates(self, direction: str) -> DirectionRates | None:
        """
        按方向取速率对象（未启用则 None）。

        Args:
            direction: spirit | body | crafting。

        Returns:
            DirectionRates | None: 方向配置。
        """
        if direction == "spirit":
            return self.spirit if self.spirit.enabled else None
        if direction == "body":
            return self.body if self.body.enabled else None
        if direction == "crafting":
            return self.crafting if self.crafting.enabled else None
        return None

    def gain_per_tick_for_major(self, direction: str, major_realm: str) -> int:
        """
        按大境界查表取基础速率；缺键回落 directions.*_per_tick。

        Args:
            direction: spirit | body | crafting。
            major_realm: 大境界 id（如 body_tempering）。

        Returns:
            int: 每 tick 基础产出（≥0）。
        """
        table = self.gain_by_realm.get(direction) or {}
        if major_realm in table:
            return max(0, int(table[major_realm]))
        rates = self.direction_rates(direction)
        if rates is None:
            # 方向关闭时仍可能查表展示：回落未启用方向的 raw gain
            fallback = {
                "spirit": self.spirit.gain_per_tick,
                "body": self.body.gain_per_tick,
                "crafting": self.crafting.gain_per_tick,
            }
            return max(0, int(fallback.get(direction, 0)))
        return max(0, int(rates.gain_per_tick))


@dataclass(frozen=True)
class BreakthroughRule:
    """层进阶或跨境突破规则。"""

    success_rate: float
    spirit_stone_cost: int
    fail_cultivation_keep_ratio: float
    fail_still_charge_stones: bool


@dataclass(frozen=True)
class AsyncChannelConfig:
    """异步真读条配置（M5-D05）。"""

    enabled: bool
    label_zh: str
    hint_zh: str
    duration_seconds: dict[str, int]
    client_poll_ms: int

    def duration_for(self, advance_type: str) -> int:
        """
        按进阶类型取权威读条秒数。

        Args:
            advance_type: ``layer`` / ``major``（内部键；配置用 layer_advance/major_advance）。

        Returns:
            int: 至少 1 秒。
        """
        key = "layer_advance" if advance_type == "layer" else "major_advance"
        raw = self.duration_seconds.get(key)
        if raw is None:
            # 兼容简写 layer / major
            raw = self.duration_seconds.get(advance_type, 8)
        return max(1, int(raw))


@dataclass(frozen=True)
class BreakthroughConfig:
    """突破配置聚合。"""

    layer_advance: BreakthroughRule
    major_advance: BreakthroughRule
    success_rate_clamp: dict[str, float] = field(default_factory=lambda: {"min": 0.05, "max": 0.95})
    # 筑基前突破免费；仅炼气→筑基跨境扣 major_advance 灵石
    pre_foundation_free: bool = True
    async_channel: AsyncChannelConfig = field(
        default_factory=lambda: AsyncChannelConfig(
            enabled=True,
            label_zh="闭关突破",
            hint_zh="突破需闭关片刻，期间无法开战或有效挂机。",
            duration_seconds={"layer_advance": 8, "major_advance": 15},
            client_poll_ms=500,
        ),
    )


@dataclass(frozen=True)
class MonsterRewards:
    """PVE 胜负奖励。"""

    cultivation_points: int
    spirit_stones: int


@dataclass(frozen=True)
class MonsterUnitConfig:
    """怪侧单个棋子配置（M3 棋盘化）。"""

    unit_uid: str
    name: str
    x: int
    y: int
    atk: int
    hp: int
    speed: int
    attack_range: int
    attack_kind: str
    can_fly: bool
    # M3-D06：嘲讽光环外键（taunt_auras.auras）；None=无光环
    taunt_aura_id: str | None = None


@dataclass(frozen=True)
class TauntAuraDef:
    """单条嘲讽光环定义（taunt_auras.yaml）。"""

    aura_id: str
    label_zh: str
    help_zh: str
    summary: str
    shape: str
    include_self_cell: bool
    duration_rounds: int | None
    radius: int | None = None
    cells: tuple[tuple[int, int], ...] = ()

    def to_engine_snapshot(self) -> dict[str, Any]:
        """
        压成引擎可吃的光环快照（开战 setup 写入单位；零 Bundle 依赖）。

        Returns:
            可 JSON 序列化的 dict（含 shape / radius / cells 等）。
        """
        return {
            "aura_id": self.aura_id,
            "label_zh": self.label_zh,
            "summary": self.summary,
            "shape": self.shape,
            "radius": self.radius if self.shape == "chebyshev" else None,
            "cells": [{"dx": dx, "dy": dy} for dx, dy in self.cells],
            "include_self_cell": self.include_self_cell,
            "duration_rounds": self.duration_rounds,
        }

    def to_public_summary(self) -> dict[str, str]:
        """
        玩家可见摘要（选怪 API / §0.7）。

        Returns:
            ``{aura_id, label_zh, summary}``。
        """
        return {
            "aura_id": self.aura_id,
            "label_zh": self.label_zh,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class TauntAurasConfig:
    """嘲讽光环注册表。"""

    schema_version: int
    auras: dict[str, TauntAuraDef]

    def resolve_snapshot(self, taunt_aura_id: str | None) -> dict[str, Any] | None:
        """
        按 id 解析引擎快照。

        Args:
            taunt_aura_id: 外键；空则无光环。

        Returns:
            快照 dict 或 None。

        Raises:
            ValueError: 引用了未知 id。
        """
        if not taunt_aura_id:
            return None
        aura = self.auras.get(taunt_aura_id)
        if aura is None:
            raise ValueError(f"unknown taunt_aura_id: {taunt_aura_id!r}")
        return aura.to_engine_snapshot()

    def public_summaries_for_units(
        self,
        units: tuple[MonsterUnitConfig, ...] | list[MonsterUnitConfig],
    ) -> list[dict[str, str]]:
        """
        从编成单位去重汇总嘲讽光环公开摘要（顺序=首次出现序）。

        Args:
            units: 怪物编成单位列表。

        Returns:
            ``to_public_summary`` 列表；未知 id 跳过（加载期应已 FK 校验）。
        """
        labels: list[dict[str, str]] = []
        seen: set[str] = set()
        for unit in units:
            aura_id = unit.taunt_aura_id
            if not aura_id or aura_id in seen:
                continue
            aura = self.auras.get(aura_id)
            if aura is None:
                continue
            seen.add(aura_id)
            labels.append(aura.to_public_summary())
        return labels


@dataclass(frozen=True)
class MonsterConfig:
    """PVE 怪物配置（M1 单体数值 + M3 可选棋盘编成）。"""

    monster_id: str
    name: str
    atk: int
    hp: int
    max_rounds: int
    rewards_on_win: MonsterRewards
    rewards_on_lose: MonsterRewards
    # M3：怪侧棋子编成；空元组表示旧式单体怪（回退落 (6,3)）
    units: tuple[MonsterUnitConfig, ...] = ()
    # M3：该怪的体力消耗；None 时取 stamina.yaml costs.battle_pve
    stamina_cost: int | None = None


@dataclass(frozen=True)
class OfflineConfig:
    """离线帽与 pending 阈值。"""

    free_cap_hours: float
    membership_caps: dict[str, float]
    preview_threshold_seconds: int
    discard_over_cap_wall_time: bool


@dataclass(frozen=True)
class TechniqueSkillConfig:
    """功法技能占位（展示用，引擎未接）。"""

    skill_id: str
    label_zh: str
    effect_zh: str


@dataclass(frozen=True)
class TechniqueConfig:
    """单本功法配置。"""

    technique_id: str
    name: str
    track: str
    max_level: int
    cost_per_level: tuple[int, ...]
    effects_placeholder: dict[str, float | int]
    # 参与时辰/天气 tag_modifiers 的标签（如 thunder_art）
    env_tags: tuple[str, ...] = ()
    # 按等级的骰子上下限修正；下标 0 = 1 级；元素为 {min_bonus,max_bonus}
    dice_mods: tuple[dict[str, int], ...] = ()
    # 功法特性（如 reincarnatable=可轮回带入）
    traits: tuple[str, ...] = ()
    elements: tuple[str, ...] = ()
    help_zh: str = ""
    learn_requires: dict[str, Any] = field(default_factory=dict)
    skills_main: tuple[TechniqueSkillConfig, ...] = ()
    skills_art: tuple[TechniqueSkillConfig, ...] = ()


@dataclass(frozen=True)
class TechniqueLoadoutConfig:
    """主功法 / 技法装备槽配置。"""

    main_slots: int
    default_art_slots: int
    help_zh: str
    art_slots_by_major: dict[str, int]


@dataclass(frozen=True)
class DivineAbilityConfig:
    """单条神通配置。"""

    ability_id: str
    name: str
    help_zh: str = ""
    effect_zh: str = ""
    elements: tuple[str, ...] = ()


@dataclass(frozen=True)
class DivineAbilityLoadoutConfig:
    """神通装备槽：修为基数 + 品阶加成。"""

    help_zh: str
    default_slots: int
    slots_by_major: dict[str, int]


@dataclass(frozen=True)
class DiceChannelConfig:
    """骰子修正通道开关。"""

    channel_id: str
    enabled: bool


@dataclass(frozen=True)
class CombatAttrDefConfig:
    """combat_attrs.yaml 单属性注册项。"""

    key: str
    label_zh: str
    help_zh: str
    category: str
    engine: bool = False
    panel: bool = True
    formula_enabled: bool = True
    default: float = 0.0


@dataclass(frozen=True)
class CombatAttrsConfig:
    """统一战斗/生活属性注册表（ATTR-D01）。"""

    schema_version: int
    defaults: dict[str, float]
    aliases: dict[str, str]
    primary_map: dict[str, dict[str, float]]
    attrs: dict[str, CombatAttrDefConfig]
    entity_profiles: dict[str, tuple[str, ...]]
    channels: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class DiceConfig:
    """修为骰子系统配置（dice.yaml）。"""

    # 缺键回落上下限
    fallback_min: int
    fallback_max: int
    # 怪物默认上下限
    monster_min: int
    monster_max: int
    # 全局钳制
    absolute_min: int
    absolute_max: int
    # 大境界 → stage → {min,max}
    realm_bounds: dict[str, dict[int, dict[str, int]]]
    # 体修道附加
    body_realm_bonus: dict[str, dict[int, dict[str, int]]]
    # 气运分档
    fate_luck_tiers: tuple[dict[str, int], ...]
    # 通道
    bonus_channels: dict[str, DiceChannelConfig]
    # 突破是否用 success_rate 映射阈值
    use_legacy_success_rate: bool
    # 战斗伤害是否用中点归一
    use_midpoint_normalizer: bool
    # 已声明用途
    purposes: tuple[str, ...]

    def channel_enabled(self, channel_id: str) -> bool:
        """通道是否启用。"""
        ch = self.bonus_channels.get(channel_id)
        return bool(ch and ch.enabled)


@dataclass(frozen=True)
class ConstitutionItemDef:
    """体质物品定义（配置样本）。"""

    def_id: str
    name: str
    quality: str
    kind: str
    grade: str
    base_attrs: dict[str, int]
    # 本源槽生效；含占位 idle_mult（float）等挂机钩子
    main_effects: dict[str, float]
    # 旁支槽生效
    sub_effects: dict[str, float]

    @property
    def effects(self) -> dict[str, float]:
        """兼容旧读取：默认视作本源效果。"""
        return self.main_effects

    def effects_for_slot(self, slot_type: str) -> dict[str, float]:
        """
        Effects that apply when this physique occupies ``slot_type``.

        Args:
            slot_type: ``main`` (本源) or ``sub`` (旁支).

        Returns:
            dict[str, float]: Active numeric effects.
        """
        if slot_type == "main":
            return self.main_effects
        if slot_type == "sub":
            return self.sub_effects
        return {}


@dataclass(frozen=True)
class ConstitutionConfig:
    """体质格位与样本物品。"""

    main_slots: int
    sub_slots: int
    soft_cap: int
    items: dict[str, ConstitutionItemDef]


@dataclass(frozen=True)
class GradeConfig:
    """跨境品阶定义。"""

    grade_id: str
    name: str
    weight: int
    atk_mul: float
    hp_mul: float
    divine_slots: int


@dataclass(frozen=True)
class GradesConfig:
    """品阶表与体质权重修正。"""

    grades: tuple[GradeConfig, ...]
    per_main_affix_bonus: float
    per_base_attr_point_bonus: float

    def grade_by_id(self, grade_id: str) -> GradeConfig | None:
        """按 id 查品阶。"""
        for item in self.grades:
            if item.grade_id == grade_id:
                return item
        return None


@dataclass(frozen=True)
class BoardZonesConfig:
    """棋盘三区划分（进攻方视角）。"""

    own_x: tuple[int, ...]
    neutral_x: tuple[int, ...]
    enemy_x: tuple[int, ...]


@dataclass(frozen=True)
class DeployRectConfig:
    """默认可部署矩形（进攻方视角；防守方镜像）。"""

    x_min: int
    x_max: int
    y_min: int
    y_max: int


@dataclass(frozen=True)
class UnitKindGate:
    """棋子种类闸门（未开放种类返回 40043）。"""

    unique: bool
    required: bool
    enabled: bool


@dataclass(frozen=True)
class UnitDefaultsConfig:
    """某类棋子的默认战斗面板值。"""

    speed: int
    can_fly: bool
    attack_range: int
    attack_kind: str
    atk_ratio: float
    hp_ratio: float


@dataclass(frozen=True)
class BoardConfig:
    """M3 棋盘全局配置（board.yaml）。"""

    size: int
    zones: BoardZonesConfig
    default_deploy: DeployRectConfig
    default_max_units: int
    default_anchor: tuple[int, int]
    max_rounds: int
    timeout_winner: str
    dice_sides: int
    ap_per_turn: int
    land_move_points: int
    fly_move_points: int
    hit_rates: dict[str, float]
    damage_floor: int
    damage_dice_normalizer: float
    max_units_by_major_realm: dict[str, int]
    unit_kinds: dict[str, UnitKindGate]
    unit_defaults: dict[str, UnitDefaultsConfig]


@dataclass(frozen=True)
class FormationLayerConfig:
    """阵法四象中的一层（环境 / 天气 / 效果通用结构）。"""

    layer_id: str
    force_apply: bool
    counter_group: str | None
    # 效果层可附带的面板乘区（环境/天气层通常为空）
    atk_mul: float
    hp_mul: float


@dataclass(frozen=True)
class FormationTerrainCell:
    """阵法地形格（进攻方视角坐标，己方半区）。"""

    x: int
    y: int
    terrain_type: str  # obstacle / ravine / seal
    subtype: str  # destructible / indestructible / flyable / no_fly / seal 子类


@dataclass(frozen=True)
class FormationDef:
    """
    单个阵法定义（四象 + 部署契约 + 可选强制移位）。

    ``deploy`` / ``terrain_layout`` / ``force_shifts`` 见
    ``阵法部署与自研设计.md``（M3-D08）。
    """

    formation_id: str
    name: str
    level: int
    unlocked_by_default: bool
    required_array_level: int
    terrain: tuple[FormationTerrainCell, ...]
    environment: FormationLayerConfig | None
    weather: FormationLayerConfig | None
    effect: FormationLayerConfig | None
    deploy: "DeployConfig"
    terrain_layout: "TerrainLayoutConfig"
    force_shifts: tuple["ForceShiftRule", ...] = ()


@dataclass(frozen=True)
class LayerCatalogEntry:
    """四象内容目录条目（环境 / 天气 / 效果共用壳）。"""

    content_id: str
    label_zh: str
    summary: str
    combat: dict[str, float]


@dataclass(frozen=True)
class FormationsConfig:
    """阵法总表 + 克制表 + 四象内容目录（M3-D07）。"""

    formations: dict[str, FormationDef]
    environment_counters: dict[str, dict[str, float]]
    weather_counters: dict[str, dict[str, float]]
    effect_counters: dict[str, dict[str, float]]
    environment_catalog: dict[str, LayerCatalogEntry]
    weather_catalog: dict[str, LayerCatalogEntry]
    effect_catalog: dict[str, LayerCatalogEntry]

    def catalogs_plain(self) -> dict[str, dict[str, Any]]:
        """引擎 setup 用的纯 dict 目录（含 label_zh / combat）。"""

        def _one(entries: dict[str, LayerCatalogEntry]) -> dict[str, Any]:
            return {
                cid: {
                    "label_zh": e.label_zh,
                    "summary": e.summary,
                    "combat": dict(e.combat),
                }
                for cid, e in entries.items()
            }

        return {
            "environment": _one(self.environment_catalog),
            "weather": _one(self.weather_catalog),
            "effect": _one(self.effect_catalog),
        }

    def to_engine_catalogs(self) -> dict[str, dict[str, Any]]:
        """
        引擎目录快照（对齐嘲讽 ``to_engine_snapshot`` 命名）。

        与 ``catalogs_plain`` 同义，供服务层显式表达「配置→引擎」边界。
        """
        return self.catalogs_plain()


@dataclass(frozen=True)
class SnapshotRewards:
    """PVP 攻打快照的占位奖励。"""

    cultivation_points: int
    spirit_stones: int


@dataclass(frozen=True)
class SnapshotsConfig:
    """防守快照配置（snapshots.yaml）。"""

    schema_version: int
    manual_cooldown_seconds: int
    daily_refresh_hours_utc: tuple[int, ...]
    attacker_win: SnapshotRewards
    attacker_lose: SnapshotRewards


@dataclass(frozen=True)
class StaminaConfig:
    """体力系统配置（stamina.yaml）。"""

    cap: int
    regen_per_minute: float
    costs: dict[str, int]
    item_overflow: bool


@dataclass(frozen=True)
class AvatarIdleRates:
    """化身单方向挂机速率。"""

    enabled: bool
    gain_per_tick: int


@dataclass(frozen=True)
class AvatarFeatureUnlockConfig:
    """化身单一功能解锁条目（avatar.yaml feature_unlocks）。"""

    feature_id: str
    min_major: str
    label_zh: str
    summary: str


@dataclass(frozen=True)
class AvatarTransferConfig:
    """化身互传折扣与白名单。"""

    allow: tuple[str, ...]
    deny: tuple[str, ...]
    retention_ratio: float
    retention_by_major: dict[str, float]
    min_amount: int
    summary: str


@dataclass(frozen=True)
class AvatarStaminaConfig:
    """化身体力与日行动（元婴起 stamina 功能解锁后生效）。"""

    base_cap: int
    cap_by_major: dict[str, int]
    daily_action_cap: int
    recovery_per_hour: float
    recovery_summary: str
    action_costs: dict[str, int]
    allow_stamina_transfer: bool


@dataclass(frozen=True)
class AvatarFriendAssistConfig:
    """道友化身助战（avatar.yaml friend_assist）。"""

    invite_expire_sec: int
    assist_dev_assume_online: bool
    stamina_base_cap: int
    stamina_cap_by_major: dict[str, int]
    stamina_recovery_per_hour: float
    battle_cost: int
    resume_ratio: float


@dataclass(frozen=True)
class AvatarConfig:
    """avatar.yaml 聚合。"""

    unlock_major_realm: str
    max_avatars: int
    max_major_realm: str
    avatar_lead_majors: int
    initial_stat_ratio: float
    material_mod_placeholder: float
    condense_spirit_stone_cost: int
    condense_cultivation_cost: int
    condense_technique_ids: tuple[str, ...]
    condense_medium_item_ids: tuple[str, ...]
    condense_medium_quantity: int
    spirit_rates: AvatarIdleRates
    body_rates: AvatarIdleRates
    crafting_rates: AvatarIdleRates
    spirit_stone_cost_per_tick_ratio: float
    transfer_allow: tuple[str, ...]
    transfer_deny: tuple[str, ...]
    feature_unlocks: dict[str, AvatarFeatureUnlockConfig]
    transfer: AvatarTransferConfig
    stamina: AvatarStaminaConfig
    friend_assist: AvatarFriendAssistConfig
    # 由 load_game_config 在 realms 就绪后注入；热路径走索引避免重复扫链
    capability: Any | None = None


@dataclass(frozen=True)
class DivineSenseOverloadBandConfig:
    """神识超载阶梯档（M4-D03）。"""

    max_load_ratio: float | None
    combat_stat_mult: float
    zone: str


@dataclass(frozen=True)
class DivineSenseBacklashConfig:
    """神识反噬表条目（M4-D03）。"""

    id: str
    when: str
    idle_mult: float
    set_flag: bool
    summary: str


@dataclass(frozen=True)
class DivineSenseConfig:
    """divine_sense.yaml 聚合。"""

    base_capacity: int
    per_realm_bonus: dict[str, int]
    cost_avatar: int
    cost_pet: int
    cost_puppet: int
    puppet_loadout_max: int
    soft_ratio: float
    hard_ratio: float
    overload_stat_mult: float
    backlash_idle_mult: float
    overload_bands: tuple[DivineSenseOverloadBandConfig, ...]
    backlash_table: tuple[DivineSenseBacklashConfig, ...]


@dataclass(frozen=True)
class CraftRecipeOutput:
    """单条配方产出。"""

    item_type: str | None
    item_id: str | None
    quantity: int
    grant_array_craft_level: int
    grant_craft_level: int


@dataclass(frozen=True)
class CraftMaterial:
    """配方材料需求。"""

    item_id: str
    quantity: int


@dataclass(frozen=True)
class CraftRecipe:
    """单条工坊配方。"""

    recipe_id: str
    branch: str
    name: str
    duration_seconds: int
    fail_chance: float
    spirit_stone_cost: int
    stamina_cost: int
    materials: tuple[CraftMaterial, ...]
    outputs: tuple[CraftRecipeOutput, ...]
    required_craft_level: int
    recipe_tier: int
    grant_craft_level: int


@dataclass(frozen=True)
class CraftRecipesConfig:
    """craft_recipes.yaml 聚合。"""

    main_crafting_bonus: float
    max_jobs_per_actor: int
    recipes: dict[str, CraftRecipe]
    quality_by_level_delta: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class PetRaceConfig:
    """灵宠种族定义（热插拔）。"""

    race_id: str
    name: str
    racial_talent_id: str
    base_capture_rate: float


@dataclass(frozen=True)
class PetGradeConfig:
    """个体品阶定义（槽位与基础乘区）。"""

    grade: int
    name: str
    affix_slots: int
    type_reroll_slots: int
    base_mult: float


@dataclass(frozen=True)
class PetSpeciesConfig:
    """灵宠物种定义。"""

    species_id: str
    name: str
    race: str
    rarity: str
    roles: tuple[str, ...]
    acquire_tags: tuple[str, ...]
    skill_pool_id: str
    base_atk: int
    base_hp: int
    base_speed: int
    growth: dict[str, float]
    upgrade_cost: dict[str, Any]
    divine_sense_cost: int | None = None
    evolve_to: str | None = None
    # PET-D03：独立被动池；空则捕获不 roll 独立被动
    passive_pool_id: str = ""


@dataclass(frozen=True)
class PetsConfig:
    """pets.yaml 聚合。"""

    hold_cap: int
    level_stat_bonus: float
    races: dict[str, PetRaceConfig]
    grades: dict[int, PetGradeConfig]
    species: dict[str, PetSpeciesConfig]
    capture_test_weights: dict[str, int]
    capture_test_grade_weights: dict[int, int]
    sect_reroll: dict[str, Any]
    # PET-D01：升阶费用（spirit_stones_base / grow / max_grade）
    grade_up: dict[str, Any]


@dataclass(frozen=True)
class PetAffixTierRange:
    """词条某品级的数值闭区间。"""

    min_value: float
    max_value: float


@dataclass(frozen=True)
class PetAffixTypeConfig:
    """
    灵宠词条类型（与体质词条分表）。

    Attributes:
        affix_type_id: 类型主键。
        name: 展示名。
        kind: flat_atk|flat_hp|flat_speed|pct_atk|pct_hp|pct_speed|passive_ref。
        tier_ranges: 品级 → 数值区间。
        passive_id: kind=passive_ref 时的被动引用（结算 → PET-D03）。
    """

    affix_type_id: str
    name: str
    kind: str
    tier_ranges: dict[str, PetAffixTierRange]
    passive_id: str | None = None


@dataclass(frozen=True)
class PetAffixesConfig:
    """pet_affixes.yaml 聚合（PET-D01）。"""

    types: dict[str, PetAffixTypeConfig]
    type_weights: dict[str, int]
    tier_weights: dict[str, int]
    value_reroll: dict[str, Any]


@dataclass(frozen=True)
class PetSkillConfig:
    """灵宠主动技能定义（PET-D02）。"""

    skill_id: str
    name: str
    power: int
    accuracy: int
    category: str
    priority: int
    pp: int
    mutex_tags: tuple[str, ...]


@dataclass(frozen=True)
class PetSkillPoolConfig:
    """物种技能池。"""

    pool_id: str
    name: str
    skill_ids: tuple[str, ...]
    default_learned: tuple[str, ...]
    default_equipped: tuple[str, ...]


@dataclass(frozen=True)
class PetSkillsConfig:
    """pet_skills.yaml 聚合。"""

    equip_slots: int
    skills: dict[str, PetSkillConfig]
    pools: dict[str, PetSkillPoolConfig]


@dataclass(frozen=True)
class PetSkillBookConfig:
    """技能书定义。"""

    book_id: str
    name: str
    skill_id: str
    scope: str
    race_id: str | None = None
    species_id: str | None = None


@dataclass(frozen=True)
class PetSkillBooksConfig:
    """pet_skill_books.yaml 聚合。"""

    books: dict[str, PetSkillBookConfig]


@dataclass(frozen=True)
class PetDuelNpcConfig:
    """NPC 对战模板。"""

    npc_id: str
    name: str
    species_id: str
    grade: int
    level: int
    skill_ids: tuple[str, ...]


@dataclass(frozen=True)
class PetDuelConfig:
    """pet_duel.yaml 聚合（PET-D05）。"""

    max_rounds: int
    damage_divisor: float
    damage_roll_min: float
    damage_roll_max: float
    accuracy_enabled: bool
    speed_tie_break: str
    default_struggle: dict[str, Any]
    npc_templates: dict[str, PetDuelNpcConfig]


@dataclass(frozen=True)
class PetPassiveConfig:
    """单一被动/种族天赋定义（PET-D03）。"""

    passive_id: str
    name: str
    kind: str
    effect_domain: str
    effects: dict[str, float]
    summary: str


@dataclass(frozen=True)
class PetPassivePoolConfig:
    """独立被动抽取池。"""

    pool_id: str
    empty_weight: int
    weights: dict[str, int]


@dataclass(frozen=True)
class PetPassivesConfig:
    """pet_passives.yaml 聚合。"""

    passives: dict[str, PetPassiveConfig]
    pools: dict[str, PetPassivePoolConfig]


@dataclass(frozen=True)
class PetFeedItemConfig:
    """单一兽丹定义（PET-D04）。"""

    item_id: str
    name: str
    per_item_cap: int
    effects: dict[str, float]
    summary: str


@dataclass(frozen=True)
class PetFeedConfig:
    """pet_feed.yaml 聚合。"""

    total_feed_cap: int
    total_feed_cap_by_grade: dict[int, int]
    total_feed_cap_by_species: dict[str, int]
    items: dict[str, PetFeedItemConfig]


@dataclass(frozen=True)
class PetEggConfig:
    """单一灵兽蛋定义（N5）。"""

    egg_id: str
    name: str
    species_id: str
    hatch_seconds: int
    spirit_stones: int
    grade_weights: dict[int, int]


@dataclass(frozen=True)
class PetEggsConfig:
    """pet_eggs.yaml 聚合。"""

    max_concurrent: int
    eggs: dict[str, PetEggConfig]


@dataclass(frozen=True)
class PetEncounterConfig:
    """pet_encounter.yaml 聚合（M4-D04c）。"""

    capturable_types: tuple[str, ...]
    skip_battle: bool
    tables: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class PetCaptureConfig:
    """pet_capture.yaml 聚合（M4-D04c）。"""

    lure_item_id: str
    bag_item_id: str
    require_bag: bool
    daily_attempt_cap: int
    special_affix_min_tier: str
    pen_affix: float
    pen_grade: dict[int, float]
    realm_diff_beast_stages_per_grade: int
    realm_diff_per_stage: float
    realm_diff_clamp_min: float
    realm_diff_clamp_max: float
    root_affinity: dict[str, dict[str, float]]
    taming_tech_bonus: dict[str, float]
    species_capture_override: dict[str, float]
    auto_capture_enabled: bool
    auto_capture_max_rolls: int
    estimate_special_affixes: bool


@dataclass(frozen=True)
class InventoryStackRules:
    """堆叠规则。"""

    default_max_stack: int
    by_item_type: dict[str, int]


@dataclass(frozen=True)
class ItemInspectDef:
    """工坊成品悬停：单一属性、功效、境界门槛、说明。"""

    realm_req_zh: str
    help_zh: str
    effects: tuple[str, ...]
    element: str | None = None


@dataclass(frozen=True)
class InventoryItemDef:
    """背包物品定义。"""

    item_id: str
    name: str
    item_type: str
    max_stack: int
    use_effect: dict[str, Any] | None = None
    # 可放入的袋：normal / reincarnation；缺省仅 normal
    bag_allowed: tuple[str, ...] = ("normal",)
    # M7 L2：可交易 / 绑定（绑定物禁上架）
    tradable: bool = True
    bound: bool = False
    # M7 机缘/交易：唯一物不可拆分发放
    unique: bool = False
    # S1-4：傀儡等可部署物指向战斗体模板 id；缺省等于 item_id
    actor_def_id: str | None = None
    # M8 R5：manual 细类 / 解锁配方（学习玩法后延，本字段仅管线）
    manual_kind: str | None = None
    unlock_recipe_id: str | None = None
    # 官方符箓成品挂效果白名单 id（工坊筛选 kind、领取写入 meta.effect_id）
    talisman_effect_id: str | None = None
    inspect: ItemInspectDef = field(
        default_factory=lambda: ItemInspectDef(
            realm_req_zh=INSPECT_REALM_NONE_ZH,
            help_zh="",
            effects=(),
            element=None,
        ),
    )


@dataclass(frozen=True)
class InventoryConfig:
    """inventory.yaml 聚合。"""

    stack_rules: InventoryStackRules
    item_types: tuple[str, ...]
    items: dict[str, InventoryItemDef]


@dataclass(frozen=True)
class EquipmentItemDef:
    """equipment.yaml 单条装备定义。"""

    item_id: str
    label_zh: str
    help_zh: str
    slot: str
    stats: dict[str, float]
    dice_mods: dict[str, int]
    idle_mods: dict[str, float]
    grants: tuple[str, ...]
    required_major_realm: str | None = None


@dataclass(frozen=True)
class EquipmentConfig:
    """equipment.yaml 聚合。"""

    items: dict[str, EquipmentItemDef]


@dataclass(frozen=True)
class ResearchAffixDef:
    """Single research affix (whitelist)."""

    affix_id: str
    label_zh: str
    help_zh: str
    stats: dict[str, float]


@dataclass(frozen=True)
class ResearchTechniqueConfig:
    """Technique research branch settings."""

    label_zh: str
    help_zh: str
    allowed_materials: tuple[str, ...]
    min_materials: int
    spend: dict[str, int]
    max_rerolls: int
    reroll_materials: tuple[dict[str, Any], ...]
    affix_slots: int
    extra_affix_roll: int
    session_ttl_seconds: int
    track: str
    max_level: int
    cost_per_level: tuple[int, ...]


@dataclass(frozen=True)
class ResearchFormationConfig:
    """research.yaml formation branch (M8 R3)."""

    label_zh: str
    help_zh: str
    allowed_materials: tuple[str, ...]
    min_materials: int
    spend: dict[str, int]
    required_array_level: int
    session_ttl_seconds: int
    default_deploy_mode: str
    terrain_layout: dict[str, Any]
    allowed_deploy_modes: tuple[str, ...]
    allowed_environment_ids: tuple[str, ...]
    allowed_weather_ids: tuple[str, ...]
    allowed_effect_ids: tuple[str, ...]
    max_force_shifts: int


@dataclass(frozen=True)
class ResearchTalismanConfig:
    """research.yaml talisman branch (M8 R4)."""

    label_zh: str
    help_zh: str
    allowed_materials: tuple[str, ...]
    min_materials: int
    spend: dict[str, int]
    session_ttl_seconds: int
    paper_item_id: str
    paper_per_copy: int
    max_batch: int
    preload_slots: int
    battle_enabled: bool


@dataclass(frozen=True)
class TalismanEffectDef:
    """talisman_effects.yaml whitelist entry."""

    effect_id: str
    label_zh: str
    help_zh: str
    trigger: str
    kind: str
    stack_group: str
    magnitude: float
    duration_kind: str
    duration: int
    attr: str
    use_chance: float
    hit_chance: float


@dataclass(frozen=True)
class TechniqueCraftRankConfig:
    """Per-major-realm rank caps for technique self-research."""

    affix_slots: int
    base_upgrade_cap: int
    upgrade_points_required: int


@dataclass(frozen=True)
class TechniqueCraftAffixRarityDef:
    """Rarity tier for technique-craft affixes (weights + stat/cost multipliers)."""

    rarity_id: str
    label_zh: str
    weight: float
    base_mult: float
    upgrade_mult: float
    cost_mult: float
    color: str


@dataclass(frozen=True)
class TechniqueCraftAffixDef:
    """Technique-craft affix filtered by efficacy."""

    affix_id: str
    label_zh: str
    rarity: str
    efficacy_allow: tuple[str, ...]
    role: str
    stats: dict[str, float]


@dataclass(frozen=True)
class TechniqueCraftConfig:
    """research.yaml technique_craft branch (功法卡片自研)."""

    help_zh: str
    blank_to_type_p_element: float
    efficacy_weights: dict[str, float]
    embed_fail_rate: float
    affix_upgrade_fail_rate: float
    breakthrough_fail_rate: float
    base_bonus_points: tuple[int, ...]
    affix_upgrade_points: tuple[int, ...]
    spirit_upgrade_cost: tuple[int, ...]
    body_upgrade_cost: tuple[int, ...]
    affix_upgrade_cost: tuple[int, ...]
    affix_reroll_cost: tuple[int, ...]
    breakthrough_cost_cultivation: int
    breakthrough_cost_body: int
    print_manual_cost_cultivation: int
    print_manual_cost_body: int
    affix_level_mult: float
    breakthrough_affix_bonus: float
    base_stat_per_click: float
    ranks: dict[str, TechniqueCraftRankConfig]
    weapon_bonus: dict[str, dict[str, float]]
    affix_rarities: dict[str, TechniqueCraftAffixRarityDef]
    affixes: dict[str, TechniqueCraftAffixDef]


@dataclass(frozen=True)
class ResearchConfig:
    """research.yaml aggregate."""

    schema_version: int
    reincarnation_carry: bool
    technique: ResearchTechniqueConfig
    formation: ResearchFormationConfig
    talisman: ResearchTalismanConfig
    affixes: dict[str, ResearchAffixDef]
    technique_craft: TechniqueCraftConfig


@dataclass(frozen=True)
class CalendarConfig:
    """六时历法配置（calendar.yaml）。"""

    slot_seconds: int
    epoch_utc: str
    shichen_order: tuple[str, ...]
    labels: dict[str, str]
    modifiers: dict[str, dict[str, float]]
    clamp_min: float
    clamp_max: float
    # 玩家可见说明：shichen_id → {summary, idle_note, ...}
    catalog: dict[str, dict[str, Any]]
    # 灵根/功法标签额外乘区：idle_cultivation.by_shichen.<id>.<tag>
    tag_modifiers: dict[str, Any]


@dataclass(frozen=True)
class WeatherRegionConfig:
    """单一区域天气池。"""

    region_id: str
    pool: dict[str, int]
    roll_interval_seconds: int


@dataclass(frozen=True)
class WeatherConfig:
    """天气池与修正配置（weather.yaml）。"""

    regions: dict[str, WeatherRegionConfig]
    labels: dict[str, str]
    modifiers: dict[str, Any]
    clamp_min: float
    clamp_max: float
    # 玩家可见说明：weather_id → {summary, idle_note, craft_notes, ...}
    catalog: dict[str, dict[str, Any]]
    # 灵根/功法标签额外乘区：idle_cultivation.by_weather.<id>.<tag>
    tag_modifiers: dict[str, Any]


@dataclass(frozen=True)
class TribulationPowerTier:
    """雷劫威力档。"""

    label: str
    base_weight: float
    cloud_radius: int


@dataclass(frozen=True)
class TribulationCountTier:
    """雷劫次数档。"""

    label: str
    strikes: int
    strikes_per_batch: int


@dataclass(frozen=True)
class TribulationConfig:
    """雷劫 / 渡劫配置（tribulation.yaml）。"""

    require_from_major: str
    require_from_stage: str
    always_after_first: bool
    power_tiers: dict[str, TribulationPowerTier]
    count_tiers: dict[str, TribulationCountTier]
    grade_to_tribulation: dict[str, dict[str, str]]
    layer_mapping: dict[str, dict[str, str]]
    prep_slots_default: int
    guardian_proc_chance: float
    guardian_hp_restore_ratio: float
    mercy_after_guardian_damage_mult: float
    in_existing_cloud_damage_mult: float
    cloud_radius_bonus_on_myriad: int
    artifact_base_shatter_chance: float
    artifact_durability_cost_per_strike: int
    reroll_grade_on_win: bool
    fate_luck_power_mult: dict[str, float]
    demonic_nature_power_mult: dict[str, float]
    veil: dict[str, Any]
    fall_on_hp_zero: bool
    realm_scale: dict[str, float]


@dataclass(frozen=True)
class ReincarnationConfig:
    """待引渡 / 轮回配置（reincarnation.yaml）。"""

    ferry_countdown_seconds: int
    self_rescue: dict[str, Any]
    carry: dict[str, Any]
    points: dict[str, Any]
    growth_attr_gain_placeholder: int
    altar: dict[str, Any]
    story: dict[str, Any]
    newborn: dict[str, Any]
    spirit_roots: dict[str, Any]
    legacy_catalog: dict[str, Any]
    shop: dict[str, Any]
    permanent_bonus_on_settle: dict[str, Any] = field(default_factory=dict)
    slots: dict[str, Any] = field(default_factory=dict)
    bags: dict[str, Any] = field(default_factory=dict)
    social_rescue: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SectsConfig:
    """宗门与设施开关（sects.yaml · M7 L1 + M7-V+ 深化）。"""

    facilities: dict[str, dict[str, Any]]
    sects: dict[str, dict[str, Any]]
    create_cost_spirit_stones: int
    idle_bonus_vs_wanderer: float
    contribution_zero_on_reincarnation: bool
    max_name_len: int
    max_motto_len: int
    max_announcement_len: int
    promotion_auto_approve_after_game_days: int
    facility_upgrade_cost_base: int
    facility_upgrade_cost_per_level: int
    grade_upgrade_spirit_stones_base: int
    features_by_founder_realm: dict[str, list[str]]
    npc_sects: dict[str, dict[str, Any]]
    sect_exchange: dict[str, Any]
    shop_items: dict[str, dict[str, Any]]
    quests: dict[str, dict[str, Any]]
    # M7-V+ 深化表
    sect_grades: dict[str, dict[str, Any]]
    disciple_ranks: dict[str, dict[str, Any]]
    specialties: dict[str, dict[str, Any]]
    facility_defs: dict[str, dict[str, Any]]
    sect_buffs: dict[str, dict[str, Any]]
    treasury: dict[str, Any]
    scripture: dict[str, Any]
    craftsmen: dict[str, dict[str, Any]]
    workshop_blueprints: dict[str, list[dict[str, Any]]]
    formations: dict[str, dict[str, Any]]
    formation_attr_keys: dict[str, dict[str, Any]]
    mine_yield: dict[str, Any]
    herb_garden: dict[str, Any]


@dataclass(frozen=True)
class FriendsConfig:
    """道友配置（friends.yaml · M7 L2）。"""

    max_friends: int
    max_companions: int
    max_vessels: int
    vessel_min_hours: int
    vessel_max_hours: int
    request_expire_sec: int
    keep_on_reincarnation: bool
    include_online_stub: bool
    include_online: bool
    dev_assume_online: bool
    # 可选覆盖 avatar.friend_assist.assist_dev_assume_online
    assist_dev_assume_online: bool | None


@dataclass(frozen=True)
class TradeConfig:
    """交易行/拍卖/面交/坊市（trade.yaml · M7 L2）。"""

    listing_fee_pct: float
    barter_fee_by_realm: dict[str, int]
    barter_fee_default: int
    auction_duration_sec: int
    auction_min_increment_pct: float
    auction_fee_pct: float
    auction_unsold_refund: str
    face_timeout_sec: int
    face_max_item_lines: int
    face_require_friend: bool
    face_require_online: bool
    face_dev_assume_online: bool
    recycle_label_zh: str
    # NPC 坊市：label / hint / 货架 mapping
    bazaar: dict[str, Any]


@dataclass(frozen=True)
class MailConfig:
    """邮件（mail.yaml · M7 L3 · 附物发信并入）。"""

    retain_days: int
    expire_unclaimed: str
    max_attachment_lines: int
    max_attachment_spirit_stones: int
    max_body_len: int
    list_limit: int
    # 掌门及以上 order（默认 9）
    sect_broadcast_min_rank_order: int
    broadcast_max_recipients: int
    gift: dict[str, Any]


@dataclass(frozen=True)
class ChatConfig:
    """聊天五频道（chat.yaml · M7 L4）。"""

    history_limit: int
    # 私聊每会话保留条数（持久；发送后惰性裁剪）
    dm_history_limit: int
    # 客户端会话级：非私聊不拉历史；退出/关浏览器清空本会话消息
    session_ephemeral: bool
    max_body_len: int
    rate_window_sec: int
    rate_max_messages: int
    sensitive_words: tuple[str, ...]
    sensitive_filter_enabled: bool
    world_line_id: str
    dm_require_friend: bool
    # 组队邀请须道友/同门/师徒（true 时校验社交关系）
    party_require_friend: bool
    # 组队邀请过期秒数（0=不过期）
    party_invite_expire_sec: int
    # 普通队伍人数上限
    party_max_members: int
    # 团队人数上限
    team_max_members: int
    # 仅 development：假定在线以便无 WS 时测邀请门闸
    party_dev_assume_online: bool
    labels_zh: dict[str, str]


@dataclass(frozen=True)
class ChatHeritageConfig:
    """聊天机缘红包（chat_heritage.yaml · M7 L5；玩家称「机缘」）。"""

    expire_sec: int
    min_shares: int
    max_shares: int
    max_spirit_stones: int
    max_item_lines: int
    claims_per_character: int
    daily_send_cap: int
    daily_spirit_cap: int
    fixed_remainder: str
    expire_refund: str
    claim_broadcast_hide_amount: bool
    active_list_limit: int
    # 已结束机缘是否惰性物理删除
    purge_closed_packets: bool
    # 客户端本会话保留已抢完条数
    session_finished_keep: int
    allowed_channel_types: tuple[str, ...]


@dataclass(frozen=True)
class MentorConfig:
    """师徒（mentor.yaml · M7 L6）。"""

    max_apprentices: int
    max_masters_per_apprentice: int
    min_realm_gap: int
    auto_graduate_max_gap: int
    request_expire_sec: int
    dissolve_cooldown_sec: int
    keep_on_reincarnation: bool
    history_after_dissolve: str
    pass_cultivation: dict[str, Any]
    daily_lesson: dict[str, Any]
    teach: dict[str, Any]
    study: dict[str, Any]
    direct_disciple: dict[str, Any]
    quests: dict[str, Any]
    graduate: dict[str, Any]


@dataclass(frozen=True)
class DualCultivationConfig:
    """双修（dual_cultivation.yaml · M7 L7）。"""

    invite_expire_sec: int
    undress_expire_sec: int
    max_rerolls: int
    spirit_stone_cost: int
    cultivation_gap_scale: int
    climax: dict[str, Any]
    stamina_costs: dict[str, Any]
    rank_min_scores: dict[str, Any]
    rank_labels: dict[str, str]
    dice_tiers: tuple[dict[str, Any], ...]
    techniques: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class CurrenciesConfig:
    """六币种目录（currencies.yaml · M7 L8）。"""

    currencies: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class CommerceConfig:
    """商业化（commerce.yaml · M7 L8）。"""

    keep_membership_on_reincarnation: bool
    membership_tiers: dict[str, dict[str, Any]]
    shop: dict[str, Any]
    sandbox: dict[str, Any]


@dataclass(frozen=True)
class MapConfig:
    """地图区域占位（map.yaml）。"""

    regions: dict[str, dict[str, Any]]
    factions: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class ActivityConfig:
    """活动开关占位（activity.yaml）。"""

    activities: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class DaoConfig:
    """大道目录与开道/运用规则（dao.yaml）。"""

    open: dict[str, Any]
    pool: dict[str, Any]
    resources: dict[str, Any]
    usage: dict[str, Any]
    restraint_enabled: bool
    categories: dict[str, str]
    rarities: dict[str, str]
    entries: dict[str, Any]
    labels: dict[str, str]


@dataclass(frozen=True)
class DaoRestraintConfig:
    """上位克制矩阵（dao_restraint.yaml）。"""

    edges: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class DaoLordContestConfig:
    """道主之争赛会日程（dao_lord.yaml contest）。"""

    tz: str
    registration_start: str
    registration_end: str
    fight_at: str
    live_round_kinds: tuple[str, ...]
    live_prep_seconds: int
    live_playback_seconds: int
    live_tick_base_ms: int
    live_dramatic_pause_ms: int
    log_retain_until_next_contest: bool
    both_offline_policy: str
    # DEV：无 WS 连接时仍视为在线，便于立刻开赛联调（生产应 false）
    dev_assume_online: bool
    # 擂台分阶段节奏
    staging_enabled: bool
    rsvp_seconds: int
    arena_first_round_countdown_seconds: int
    round_gap_seconds: int
    live_adjust_seconds: int
    leave_during_playback_forfeit: bool


@dataclass(frozen=True)
class DaoLordConfig:
    """道主门槛与时段（dao_lord.yaml）。"""

    claim_min_level: int
    challenge_min_level: int
    cooldown: dict[str, Any]
    reconnect_grace_seconds: int
    missing_snapshot_policy: str
    privileges_default: dict[str, Any]
    windows: tuple[dict[str, Any], ...]
    single_challenge_per_dao: bool
    contest: DaoLordContestConfig
    force_window_open: bool = False  # DEV/GM 运行时覆盖（非 YAML）


@dataclass(frozen=True)
class PresenceConfig:
    """角色在线状态（presence.yaml）。"""

    grace_sec: int
    # 仅 development：全局假定在线
    dev_assume_online: bool
    # 用途覆盖；空则回落业务 YAML 遗留键
    dev_assume_by_purpose: dict[str, bool]


@dataclass(frozen=True)
class WorldEventsConfig:
    """世界 Boss / 秘境骨架（world_events.yaml）。"""

    enabled: bool
    events: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class GameConfigBundle:
    """全部玩法配置的只读快照。"""

    realms: dict[str, MajorRealmConfig]
    body_temper: BodyTemperConfig
    idle: IdleConfig
    breakthrough: BreakthroughConfig
    monsters: dict[str, MonsterConfig]
    offline: OfflineConfig
    techniques: dict[str, TechniqueConfig]
    technique_loadout: TechniqueLoadoutConfig
    divine_abilities: dict[str, DivineAbilityConfig]
    divine_ability_loadout: DivineAbilityLoadoutConfig
    constitution: ConstitutionConfig
    grades: GradesConfig
    # M3 战斗成型
    board: BoardConfig
    formations: FormationsConfig
    snapshots: SnapshotsConfig
    stamina: StaminaConfig
    # M4 双线程成长
    avatar: AvatarConfig
    divine_sense: DivineSenseConfig
    craft_recipes: CraftRecipesConfig
    pets: PetsConfig
    pet_affixes: PetAffixesConfig
    pet_skills: PetSkillsConfig
    pet_skill_books: PetSkillBooksConfig
    pet_duel: PetDuelConfig
    pet_passives: PetPassivesConfig
    pet_feed: PetFeedConfig
    pet_eggs: PetEggsConfig
    pet_encounter: PetEncounterConfig
    pet_capture: PetCaptureConfig
    inventory: InventoryConfig
    equipment: EquipmentConfig
    research: ResearchConfig
    talisman_effects: dict[str, TalismanEffectDef]
    # M5 环境与轮回
    calendar: CalendarConfig
    weather: WeatherConfig
    tribulation: TribulationConfig
    reincarnation: ReincarnationConfig
    # 修为骰子
    dice: DiceConfig
    # ATTR 统一属性注册表
    combat_attrs: CombatAttrsConfig
    # ADM：宗门设施 / 地图 / 活动
    sects: SectsConfig
    friends: FriendsConfig
    trade: TradeConfig
    mail: MailConfig
    chat: ChatConfig
    chat_heritage: ChatHeritageConfig
    mentor: MentorConfig
    dual_cultivation: DualCultivationConfig
    currencies: CurrenciesConfig
    commerce: CommerceConfig
    map: MapConfig
    activity: ActivityConfig
    taunt_auras: TauntAurasConfig
    # M6 大道 / 道主 / 世界事件
    dao: DaoConfig
    dao_restraint: DaoRestraintConfig
    dao_lord: DaoLordConfig
    world_events: WorldEventsConfig
    presence: PresenceConfig


def _load_yaml(filename: str) -> dict[str, Any]:
    """
    经 ContentStore 读取玩法配置（受 ``CONTENT_STORE_MODE`` 控制）。

    - yaml_authority：仅 YAML
    - yaml_base_db_overlay：YAML ∪ DB 已发布 overlay（默认）
    - db_authority：优先已发布；无则 YAML 种子

    Args:
        filename: 文件名（如 ``pets.yaml``）。

    Returns:
        dict: 合并后的根对象（供各 ``_parse_*`` 消费）。
    """
    from app.game.content_store import ContentStore

    try:
        return ContentStore.load_filename(filename, copy=True)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"玩法配置缺失: {_CONFIG_DIR / filename}") from exc
    except ValueError as exc:
        raise ValueError(f"玩法配置根节点须为 mapping: {_CONFIG_DIR / filename}") from exc


def _parse_realms(raw: dict[str, Any]) -> dict[str, MajorRealmConfig]:
    """解析 realms.yaml 大境界表。"""
    majors_raw = raw.get("major_realms")
    if not isinstance(majors_raw, dict) or not majors_raw:
        raise ValueError("realms.yaml 缺少 major_realms")
    result: dict[str, MajorRealmConfig] = {}
    for key, body in majors_raw.items():
        stages_raw = body.get("stages") or []
        stages = tuple(
            RealmStageConfig(
                stage=int(item["stage"]),
                label=str(item["label"]),
                cultivation_required=int(item["cultivation_required"]),
                base_atk=int(item["base_atk"]),
                base_hp=int(item["base_hp"]),
            )
            for item in stages_raw
        )
        if not stages:
            raise ValueError(f"境界 {key} 无 stages")
        next_major = body.get("next_major")
        result[str(key)] = MajorRealmConfig(
            key=str(key),
            name=str(body["name"]),
            stage_mode=str(body.get("stage_mode", "layers")),
            next_major=str(next_major) if next_major else None,
            stages=stages,
        )
    return result


def _parse_body_temper(raw: dict[str, Any]) -> BodyTemperConfig:
    """
    解析 realms.yaml 炼体大境 + 淬体规则。

    兼容旧键 ``body_temper_major_order``（等同 unlock_majors）。

    Args:
        raw: realms.yaml 根对象。

    Returns:
        BodyTemperConfig: 炼体境快照。
    """
    order_raw = raw.get("body_temper_unlock_majors") or raw.get("body_temper_major_order")
    if not isinstance(order_raw, list) or not order_raw:
        raise ValueError("realms.yaml 缺少 body_temper_unlock_majors")
    unlock_majors = tuple(str(item) for item in order_raw)

    majors_raw = raw.get("body_temper_majors")
    if not isinstance(majors_raw, dict) or not majors_raw:
        raise ValueError("realms.yaml 缺少 body_temper_majors")

    majors: dict[str, BodyTemperMajorConfig] = {}
    for key, body in majors_raw.items():
        if not isinstance(body, dict):
            raise ValueError(f"body_temper_majors.{key} 须为对象")
        unlock = str(body.get("unlock_major") or "").strip()
        if unlock not in unlock_majors:
            raise ValueError(
                f"body_temper_majors.{key}.unlock_major={unlock!r} "
                f"不在 body_temper_unlock_majors",
            )
        stage_mode = str(body.get("stage_mode") or "layers").strip()
        if stage_mode not in {"layers", "phases"}:
            raise ValueError(f"body_temper_majors.{key}.stage_mode 仅 layers|phases")
        stages_raw = body.get("stages") or []
        stages = tuple(
            BodyTemperLayerConfig(
                stage=int(item["stage"]),
                label=str(item["label"]),
                progress_required=max(0, int(item["progress_required"])),
            )
            for item in stages_raw
        )
        if not stages:
            raise ValueError(f"body_temper_majors.{key} 无 stages")
        next_major = body.get("next_major")
        majors[str(key)] = BodyTemperMajorConfig(
            key=str(key),
            name=str(body["name"]),
            stage_mode=stage_mode,
            unlock_major=unlock,
            next_major=str(next_major) if next_major else None,
            stages=stages,
        )

    # next_major 外键（允许 null；指向的境须已声明——便于扩境时一次加齐）
    for major in majors.values():
        if major.next_major and major.next_major not in majors:
            raise ValueError(
                f"body_temper_majors.{major.key}.next_major={major.next_major!r} 未定义",
            )

    # 默认起点：无入边的境；否则取字典首项
    pointed = {m.next_major for m in majors.values() if m.next_major}
    roots = [k for k in majors if k not in pointed]
    default_major_id = roots[0] if roots else next(iter(majors))

    quench_raw = raw.get("body_temper_quench") or {}
    if not isinstance(quench_raw, dict):
        raise ValueError("body_temper_quench 须为对象")

    def _rule(section: str, default_rate: float, default_keep: float) -> BodyTemperQuenchRule:
        body = quench_raw.get(section) or {}
        if not isinstance(body, dict):
            body = {}
        return BodyTemperQuenchRule(
            success_rate=float(body.get("success_rate", default_rate)),
            fail_progress_keep_ratio=float(
                body.get("fail_progress_keep_ratio", default_keep),
            ),
        )

    clamp_raw = quench_raw.get("success_rate_clamp") or {}
    if not isinstance(clamp_raw, dict):
        clamp_raw = {}
    clamp_min = float(clamp_raw.get("min", 0.05))
    clamp_max = float(clamp_raw.get("max", 0.95))

    return BodyTemperConfig(
        unlock_majors=unlock_majors,
        majors=majors,
        default_major_id=default_major_id,
        layer_advance=_rule("layer_advance", 0.85, 0.7),
        major_advance=_rule("major_advance", 0.7, 0.5),
        success_rate_clamp=(clamp_min, clamp_max),
    )


def _parse_direction(
    raw: dict[str, Any],
    *,
    gain_key: str,
    default_stones: int | None,
) -> DirectionRates:
    """解析单一挂机方向。"""
    return DirectionRates(
        enabled=bool(raw.get("enabled", False)),
        gain_per_tick=int(raw.get(gain_key, 0)),
        default_stones_per_tick=(
            int(raw["spirit_stones_per_tick"]) if raw.get("spirit_stones_per_tick") else default_stones
        ),
    )


def _parse_gain_by_realm(raw: dict[str, Any] | None) -> dict[str, dict[str, int]]:
    """
    解析 gain_per_tick_by_realm 表。

    Args:
        raw: YAML 嵌套表 direction → major → int。

    Returns:
        dict[str, dict[str, int]]: 规范化后的境界基础速率表。
    """
    result: dict[str, dict[str, int]] = {}
    if not isinstance(raw, dict):
        return result
    for direction, body in raw.items():
        if not isinstance(body, dict):
            continue
        result[str(direction)] = {
            str(major): max(0, int(gain)) for major, gain in body.items()
        }
    return result


def _parse_bonus_channels(raw: dict[str, Any] | None) -> dict[str, IdleBonusChannel]:
    """
    解析 bonus_channels；缺键安全回落为空表。

    Args:
        raw: YAML 通道表。

    Returns:
        dict[str, IdleBonusChannel]: 通道 id → 配置。
    """
    result: dict[str, IdleBonusChannel] = {}
    if not isinstance(raw, dict):
        return result
    for channel_id, body in raw.items():
        if not isinstance(body, dict):
            continue
        result[str(channel_id)] = IdleBonusChannel(
            channel_id=str(channel_id),
            enabled=bool(body.get("enabled", False)),
            default_mult=float(body.get("default_mult", 1.0)),
        )
    return result


def _parse_idle(raw: dict[str, Any], tick_override: int | None) -> IdleConfig:
    """解析 idle.yaml（含境界基础表与加成通道）。"""
    directions = raw.get("directions") or {}
    spirit_raw = directions.get("spirit") or {}
    if not spirit_raw.get("enabled", False):
        raise ValueError("idle.yaml 须启用 spirit 方向")

    cost_by_realm_raw = raw.get("spirit_stone_cost_by_realm") or {}
    cost_by_realm = {str(k): int(v) for k, v in cost_by_realm_raw.items()}
    default_stone = cost_by_realm.get("body_tempering", 1)

    yaml_tick = int(raw.get("tick_seconds", 60))
    tick = int(tick_override) if tick_override and tick_override > 0 else yaml_tick

    clamp_min = float(raw.get("clamp_min", 0.5))
    clamp_max = float(raw.get("clamp_max", 2.0))
    if clamp_min > clamp_max:
        clamp_min, clamp_max = clamp_max, clamp_min

    return IdleConfig(
        tick_seconds=tick,
        cost_by_realm=cost_by_realm,
        spirit=_parse_direction(
            spirit_raw,
            gain_key="cultivation_per_tick",
            default_stones=default_stone,
        ),
        body=_parse_direction(
            directions.get("body") or {},
            gain_key="body_tempering_per_tick",
            default_stones=default_stone,
        ),
        crafting=_parse_direction(
            directions.get("crafting") or {},
            gain_key="crafting_exp_per_tick",
            default_stones=default_stone,
        ),
        gain_by_realm=_parse_gain_by_realm(raw.get("gain_per_tick_by_realm")),
        bonus_channels=_parse_bonus_channels(raw.get("bonus_channels")),
        clamp_min=clamp_min,
        clamp_max=clamp_max,
    )


def stones_per_tick_for(character: Any) -> int:
    """
    按角色大境界解析每 tick 灵石消耗。

    Args:
        character: 含 ``major_realm`` 的角色实体。

    Returns:
        int: 每 tick 灵石数；可为 0（筑基前免费挂机）。
    """
    idle = get_game_config().idle
    major = str(character.major_realm)
    # 缺键回落锻体档；允许配置 0（不强制至少 1）
    raw = idle.cost_by_realm.get(
        major,
        idle.cost_by_realm.get("body_tempering", 0),
    )
    return max(0, int(raw))


def gain_per_tick_for(character: Any, direction: str) -> int:
    """
    按角色大境界与方向取挂机基础速率（A 层）。

    Args:
        character: 含 ``major_realm`` 的角色实体。
        direction: spirit | body | crafting。

    Returns:
        int: 每 tick 基础产出。
    """
    idle = get_game_config().idle
    major = str(getattr(character, "major_realm", None) or "body_tempering")
    return idle.gain_per_tick_for_major(direction, major)


def clamp_idle_channel_mult(value: float) -> float:
    """
    将通道总乘区钳制到 idle.yaml clamp_min/max。

    Args:
        value: 原始通道乘积。

    Returns:
        float: 钳制后乘区。
    """
    idle = get_game_config().idle
    return max(float(idle.clamp_min), min(float(idle.clamp_max), float(value)))


def _parse_breakthrough_rule(raw: dict[str, Any]) -> BreakthroughRule:
    """解析一条突破规则。"""
    return BreakthroughRule(
        success_rate=float(raw["success_rate"]),
        spirit_stone_cost=int(raw["spirit_stone_cost"]),
        fail_cultivation_keep_ratio=float(raw["fail_cultivation_keep_ratio"]),
        fail_still_charge_stones=bool(raw.get("fail_still_charge_stones", True)),
    )


def _parse_async_channel(raw: dict[str, Any] | None) -> AsyncChannelConfig:
    """解析 breakthrough.async_channel；缺省时启用真读条。"""
    body = raw or {}
    duration_raw = body.get("duration_seconds") or {}
    return AsyncChannelConfig(
        enabled=bool(body.get("enabled", True)),
        label_zh=str(body.get("label_zh") or "闭关突破"),
        hint_zh=str(
            body.get("hint_zh")
            or "突破需闭关片刻，期间无法开战或有效挂机。",
        ),
        duration_seconds={
            "layer_advance": int(duration_raw.get("layer_advance", 8)),
            "major_advance": int(duration_raw.get("major_advance", 15)),
        },
        client_poll_ms=max(200, int(body.get("client_poll_ms", 500))),
    )


def _parse_breakthrough(raw: dict[str, Any]) -> BreakthroughConfig:
    """解析 breakthrough.yaml。"""
    clamp_raw = raw.get("success_rate_clamp") or {}
    return BreakthroughConfig(
        layer_advance=_parse_breakthrough_rule(raw["layer_advance"]),
        major_advance=_parse_breakthrough_rule(raw["major_advance"]),
        success_rate_clamp={
            "min": float(clamp_raw.get("min", 0.05)),
            "max": float(clamp_raw.get("max", 0.95)),
        },
        pre_foundation_free=bool(raw.get("pre_foundation_free", True)),
        async_channel=_parse_async_channel(raw.get("async_channel")),
    )


def _parse_monster_units(body: dict[str, Any]) -> tuple[MonsterUnitConfig, ...]:
    """解析怪物的 units 编成（M3 棋盘化，可缺省）。"""
    units_raw = body.get("units") or []
    units: list[MonsterUnitConfig] = []
    for item in units_raw:
        aura_raw = item.get("taunt_aura_id")
        units.append(
            MonsterUnitConfig(
                unit_uid=str(item["unit_uid"]),
                name=str(item.get("name", item["unit_uid"])),
                x=int(item["x"]),
                y=int(item["y"]),
                atk=int(item["atk"]),
                hp=int(item["hp"]),
                speed=int(item.get("speed", 5)),
                attack_range=int(item.get("attack_range", 1)),
                attack_kind=str(item.get("attack_kind", "melee_physical")),
                can_fly=bool(item.get("can_fly", False)),
                taunt_aura_id=str(aura_raw) if aura_raw else None,
            ),
        )
    return tuple(units)


def _parse_taunt_auras(raw: dict[str, Any]) -> TauntAurasConfig:
    """
    解析 taunt_auras.yaml。

    Args:
        raw: 合并后的根 mapping。

    Returns:
        TauntAurasConfig: 光环注册表。

    Raises:
        ValueError: shape / 必填字段非法。
    """
    from app.domain.taunt_aura import validate_aura_def

    schema_version = int(raw.get("schema_version", 1))
    auras_raw = raw.get("auras") or {}
    if not isinstance(auras_raw, dict):
        raise ValueError("taunt_auras.auras 须为 mapping")
    auras: dict[str, TauntAuraDef] = {}
    for aura_id, body in auras_raw.items():
        if not isinstance(body, dict):
            raise ValueError(f"taunt_auras.auras.{aura_id} 须为 mapping")
        aid = str(aura_id)
        validate_aura_def(aid, body)
        cells_raw = body.get("cells") or []
        cells: list[tuple[int, int]] = []
        if str(body.get("shape")) == "offsets":
            for item in cells_raw:
                cells.append((int(item["dx"]), int(item["dy"])))
        auras[aid] = TauntAuraDef(
            aura_id=aid,
            label_zh=str(body.get("label_zh", aid)),
            help_zh=str(body.get("help_zh", "")),
            summary=str(body.get("summary", "")),
            shape=str(body["shape"]),
            include_self_cell=bool(body.get("include_self_cell", False)),
            duration_rounds=(
                int(body["duration_rounds"])
                if body.get("duration_rounds") is not None
                else None
            ),
            radius=int(body["radius"]) if body.get("radius") is not None else None,
            cells=tuple(cells),
        )
    return TauntAurasConfig(schema_version=schema_version, auras=auras)


def resolve_unit_taunt_aura(
    taunt_aura_id: str | None,
    catalog: TauntAurasConfig,
) -> dict[str, Any] | None:
    """
    将单位上的光环 id 解析为引擎快照（薄封装 → ``TauntAurasConfig.resolve_snapshot``）。

    Args:
        taunt_aura_id: 外键；空则无光环。
        catalog: Bundle.taunt_auras。

    Returns:
        快照 dict 或 None。

    Raises:
        ValueError: 引用了未知 id。
    """
    return catalog.resolve_snapshot(taunt_aura_id)


def _parse_monsters(raw: dict[str, Any]) -> dict[str, MonsterConfig]:
    """解析 pve_monsters.yaml。"""
    monsters_raw = raw.get("monsters") or {}
    result: dict[str, MonsterConfig] = {}
    for monster_id, body in monsters_raw.items():
        win = body.get("rewards_on_win") or {}
        lose = body.get("rewards_on_lose") or {}
        stamina_cost_raw = body.get("stamina_cost")
        result[str(monster_id)] = MonsterConfig(
            monster_id=str(monster_id),
            name=str(body["name"]),
            atk=int(body["atk"]),
            hp=int(body["hp"]),
            max_rounds=int(body["max_rounds"]),
            rewards_on_win=MonsterRewards(
                cultivation_points=int(win.get("cultivation_points", 0)),
                spirit_stones=int(win.get("spirit_stones", 0)),
            ),
            rewards_on_lose=MonsterRewards(
                cultivation_points=int(lose.get("cultivation_points", 0)),
                spirit_stones=int(lose.get("spirit_stones", 0)),
            ),
            units=_parse_monster_units(body),
            stamina_cost=int(stamina_cost_raw) if stamina_cost_raw is not None else None,
        )
    if "tutorial_slime" not in result:
        raise ValueError("pve_monsters.yaml 须包含 tutorial_slime")
    return result


def _parse_offline(raw: dict[str, Any], settings: Any) -> OfflineConfig:
    """解析 offline.yaml；环境变量可覆盖关键默认值。"""
    membership_raw = raw.get("membership_caps") or {}
    membership_caps = {
        "free": float(settings.offline_cap_hours_free),
        "tier1": float(settings.offline_cap_hours_member_tier1),
        "tier2": float(settings.offline_cap_hours_member_tier2),
    }
    for tier, hours in membership_raw.items():
        if tier in membership_caps:
            membership_caps[str(tier)] = float(hours)

    return OfflineConfig(
        free_cap_hours=float(raw.get("free_cap_hours", settings.offline_cap_hours_free)),
        membership_caps=membership_caps,
        preview_threshold_seconds=int(
            raw.get("preview_threshold_seconds", settings.offline_preview_threshold_seconds),
        ),
        discard_over_cap_wall_time=bool(raw.get("discard_over_cap_wall_time", True)),
    )


def _parse_technique_skills(raw: Any) -> tuple[TechniqueSkillConfig, ...]:
    """Parse skill placeholder list from YAML."""
    if not isinstance(raw, list):
        return ()
    items: list[TechniqueSkillConfig] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        skill_id = str(row.get("id") or "").strip()
        if not skill_id:
            continue
        items.append(
            TechniqueSkillConfig(
                skill_id=skill_id,
                label_zh=str(row.get("label_zh") or skill_id),
                effect_zh=str(row.get("effect_zh") or ""),
            ),
        )
    return tuple(items)


def _parse_divine_ability_loadout(raw: dict[str, Any]) -> DivineAbilityLoadoutConfig:
    """Parse divine_abilities.yaml loadout block."""
    body = raw.get("loadout") or {}
    if not isinstance(body, dict):
        body = {}
    by_major_raw = body.get("slots_by_major") or {}
    by_major: dict[str, int] = {}
    if isinstance(by_major_raw, dict):
        for key, value in by_major_raw.items():
            by_major[str(key)] = max(0, int(value))
    return DivineAbilityLoadoutConfig(
        help_zh=str(body.get("help_zh") or ""),
        default_slots=max(0, int(body.get("default_slots") or 1)),
        slots_by_major=by_major,
    )


def _parse_divine_abilities(raw: dict[str, Any]) -> dict[str, DivineAbilityConfig]:
    """解析 divine_abilities.yaml。"""
    table = raw.get("divine_abilities") or {}
    result: dict[str, DivineAbilityConfig] = {}
    for ability_id, body in dict(table).items():
        if not isinstance(body, dict):
            continue
        elements_raw = body.get("elements") or []
        result[str(ability_id)] = DivineAbilityConfig(
            ability_id=str(ability_id),
            name=str(body.get("name") or ability_id),
            help_zh=str(body.get("help_zh") or ""),
            effect_zh=str(body.get("effect_zh") or ""),
            elements=tuple(str(x) for x in list(elements_raw) if str(x).strip()),
        )
    return result


def _parse_technique_loadout(raw: dict[str, Any]) -> TechniqueLoadoutConfig:
    """Parse techniques.yaml loadout block."""
    body = raw.get("loadout") or {}
    if not isinstance(body, dict):
        body = {}
    by_major_raw = body.get("art_slots_by_major") or {}
    by_major = {
        str(k): max(0, int(v))
        for k, v in dict(by_major_raw).items()
        if str(k).strip()
    }
    return TechniqueLoadoutConfig(
        main_slots=max(1, int(body.get("main_slots") or 1)),
        default_art_slots=max(0, int(body.get("default_art_slots") or 1)),
        help_zh=str(body.get("help_zh") or ""),
        art_slots_by_major=by_major,
    )


def _parse_techniques(raw: dict[str, Any]) -> dict[str, TechniqueConfig]:
    """解析 techniques.yaml。"""
    techniques_raw = raw.get("techniques") or {}
    result: dict[str, TechniqueConfig] = {}
    for tech_id, body in techniques_raw.items():
        env_tags_raw = body.get("env_tags") or []
        dice_mods_raw = body.get("dice_mods") or []
        dice_mods: list[dict[str, int]] = []
        for row in dice_mods_raw:
            if not isinstance(row, dict):
                continue
            dice_mods.append(
                {
                    "min_bonus": int(row.get("min_bonus", 0)),
                    "max_bonus": int(row.get("max_bonus", 0)),
                },
            )
        skills_raw = body.get("skills") or {}
        if not isinstance(skills_raw, dict):
            skills_raw = {}
        elements_raw = body.get("elements") or []
        learn_raw = body.get("learn_requires") or {}
        result[str(tech_id)] = TechniqueConfig(
            technique_id=str(tech_id),
            name=str(body["name"]),
            track=str(body["track"]),
            max_level=int(body["max_level"]),
            cost_per_level=tuple(int(x) for x in body["cost_per_level"]),
            effects_placeholder=dict(body.get("effects_placeholder") or {}),
            env_tags=tuple(str(t) for t in env_tags_raw),
            dice_mods=tuple(dice_mods),
            traits=tuple(str(t) for t in (body.get("traits") or [])),
            elements=tuple(str(e) for e in elements_raw if str(e).strip()),
            help_zh=str(body.get("help_zh") or ""),
            learn_requires=dict(learn_raw) if isinstance(learn_raw, dict) else {},
            skills_main=_parse_technique_skills(skills_raw.get("as_main")),
            skills_art=_parse_technique_skills(skills_raw.get("as_art")),
        )
    return result


def _parse_stage_bonus_table(
    raw: dict[str, Any] | None,
) -> dict[str, dict[int, dict[str, int]]]:
    """解析 major → stage → {min/max 或 min_bonus/max_bonus}。"""
    result: dict[str, dict[int, dict[str, int]]] = {}
    if not isinstance(raw, dict):
        return result
    for major, stages in raw.items():
        if not isinstance(stages, dict):
            continue
        stage_map: dict[int, dict[str, int]] = {}
        for stage_key, body in stages.items():
            if not isinstance(body, dict):
                continue
            stage_map[int(stage_key)] = {str(k): int(v) for k, v in body.items()}
        result[str(major)] = stage_map
    return result


def _parse_combat_attrs(raw: dict[str, Any]) -> CombatAttrsConfig:
    """解析 combat_attrs.yaml（ATTR 属性注册表）。"""
    defaults_raw = raw.get("defaults") or {}
    defaults = {str(k): float(v) for k, v in dict(defaults_raw).items()}
    aliases_raw = raw.get("aliases") or {}
    aliases = {str(k): str(v) for k, v in dict(aliases_raw).items()}
    primary_raw = raw.get("primary_map") or {}
    primary_map: dict[str, dict[str, float]] = {}
    for pk, body in dict(primary_raw).items():
        if not isinstance(body, dict):
            primary_map[str(pk)] = {}
            continue
        primary_map[str(pk)] = {str(ck): float(cv) for ck, cv in body.items()}
    attrs_raw = raw.get("attrs") or {}
    attrs: dict[str, CombatAttrDefConfig] = {}
    for key, body in dict(attrs_raw).items():
        if not isinstance(body, dict):
            continue
        attrs[str(key)] = CombatAttrDefConfig(
            key=str(key),
            label_zh=str(body.get("label_zh") or key),
            help_zh=str(body.get("help_zh") or ""),
            category=str(body.get("category") or "combat_core"),
            engine=bool(body.get("engine", False)),
            panel=bool(body.get("panel", True)),
            formula_enabled=bool(body.get("formula_enabled", True)),
            default=float(body.get("default", defaults.get(str(key), 0))),
        )
    profiles_raw = raw.get("entity_profiles") or {}
    entity_profiles: dict[str, tuple[str, ...]] = {}
    for ek, body in dict(profiles_raw).items():
        if isinstance(body, dict):
            cats = body.get("use_categories") or []
            entity_profiles[str(ek)] = tuple(str(c) for c in cats)
        elif isinstance(body, (list, tuple)):
            entity_profiles[str(ek)] = tuple(str(c) for c in body)
    channels_raw = raw.get("channels") or {}
    channels: dict[str, dict[str, Any]] = {}
    for cid, body in dict(channels_raw).items():
        if not isinstance(body, dict):
            continue
        channels[str(cid)] = {
            "enabled": bool(body.get("enabled", False)),
            "label_zh": str(body.get("label_zh") or cid),
        }
    return CombatAttrsConfig(
        schema_version=int(raw.get("schema_version", 2)),
        defaults=defaults,
        aliases=aliases,
        primary_map=primary_map,
        attrs=attrs,
        entity_profiles=entity_profiles,
        channels=channels,
    )


def _parse_dice(raw: dict[str, Any]) -> DiceConfig:
    """解析 dice.yaml。"""
    fallback = raw.get("fallback_bounds") or {}
    monster = raw.get("monster_default") or {}
    clamp_raw = raw.get("clamp") or {}
    channels_raw = raw.get("bonus_channels") or {}
    channels: dict[str, DiceChannelConfig] = {}
    for cid, body in channels_raw.items():
        if not isinstance(body, dict):
            continue
        channels[str(cid)] = DiceChannelConfig(
            channel_id=str(cid),
            enabled=bool(body.get("enabled", False)),
        )
    fate_tiers_raw = raw.get("fate_luck_tiers") or []
    fate_tiers: list[dict[str, int]] = []
    for tier in fate_tiers_raw:
        if not isinstance(tier, dict):
            continue
        fate_tiers.append({str(k): int(v) for k, v in tier.items()})
    breakthrough_raw = raw.get("breakthrough") or {}
    combat_raw = raw.get("combat") or {}
    purposes_raw = raw.get("purposes") or []
    return DiceConfig(
        fallback_min=int(fallback.get("min", 1)),
        fallback_max=int(fallback.get("max", 20)),
        monster_min=int(monster.get("min", 1)),
        monster_max=int(monster.get("max", 20)),
        absolute_min=int(clamp_raw.get("absolute_min", 1)),
        absolute_max=int(clamp_raw.get("absolute_max", 200)),
        realm_bounds=_parse_stage_bonus_table(raw.get("realm_bounds")),
        body_realm_bonus=_parse_stage_bonus_table(raw.get("body_realm_bonus")),
        fate_luck_tiers=tuple(fate_tiers),
        bonus_channels=channels,
        use_legacy_success_rate=bool(
            breakthrough_raw.get("use_legacy_success_rate", True),
        ),
        use_midpoint_normalizer=bool(combat_raw.get("use_midpoint_normalizer", True)),
        purposes=tuple(str(p) for p in purposes_raw),
    )

def _parse_constitution(raw: dict[str, Any]) -> ConstitutionConfig:
    """解析 constitution.yaml。"""
    from app.constants.constitution import CONSTITUTION_SOFT_CAP

    slot_defaults = raw.get("slot_defaults") or {}
    items_raw = raw.get("items") or {}
    items: dict[str, ConstitutionItemDef] = {}
    for def_id, body in items_raw.items():
        base_attrs = dict(body.get("base_attrs") or {})
        legacy_effects = {str(k): float(v) for k, v in dict(body.get("effects") or {}).items()}
        main_raw = dict(body.get("main_effects") or {})
        main_effects = (
            {str(k): float(v) for k, v in main_raw.items()} if main_raw else legacy_effects
        )
        sub_effects = {str(k): float(v) for k, v in dict(body.get("sub_effects") or {}).items()}
        items[str(def_id)] = ConstitutionItemDef(
            def_id=str(def_id),
            name=str(body["name"]),
            quality=str(body.get("quality", "mortal")),
            kind=str(body.get("kind", "physique")),
            grade=str(body.get("grade", body.get("quality", "mortal"))),
            base_attrs={str(k): int(v) for k, v in base_attrs.items()},
            main_effects=main_effects,
            sub_effects=sub_effects,
        )
    return ConstitutionConfig(
        main_slots=int(slot_defaults.get("main", 1)),
        sub_slots=int(slot_defaults.get("sub", 2)),
        soft_cap=int(slot_defaults.get("soft_cap", CONSTITUTION_SOFT_CAP)),
        items=items,
    )


def _parse_grades(raw: dict[str, Any]) -> GradesConfig:
    """解析 grades.yaml。"""
    grades_raw = raw.get("grades") or []
    grades = tuple(
        GradeConfig(
            grade_id=str(item["id"]),
            name=str(item["name"]),
            weight=int(item["weight"]),
            atk_mul=float(item["atk_mul"]),
            hp_mul=float(item["hp_mul"]),
            divine_slots=int(item["divine_slots"]),
        )
        for item in grades_raw
    )
    bonus_raw = raw.get("constitution_weight_bonus") or {}
    return GradesConfig(
        grades=grades,
        per_main_affix_bonus=float(bonus_raw.get("per_main_affix", 0)),
        per_base_attr_point_bonus=float(bonus_raw.get("per_base_attr_point", 0)),
    )


def _parse_board(raw: dict[str, Any], settings: Any) -> BoardConfig:
    """解析 board.yaml；BATTLE_MAX_ROUNDS 环境变量可覆盖回合上限。"""
    zones_raw = raw.get("zones") or {}
    deploy_raw = raw.get("default_deploy") or {}
    anchor_raw = raw.get("default_anchor_unit") or {}
    dnd_raw = raw.get("dnd") or {}
    ai_raw = raw.get("default_ai") or {}
    hit_raw = raw.get("hit_rates") or {}
    kinds_raw = raw.get("unit_kinds") or {}
    defaults_raw = raw.get("unit_defaults") or {}

    # 环境变量优先：便于联调时缩短/拉长战斗
    max_rounds_env = getattr(settings, "battle_max_rounds", None)
    max_rounds = int(max_rounds_env) if max_rounds_env else int(raw.get("max_rounds", 30))

    unit_kinds: dict[str, UnitKindGate] = {}
    for kind, body in kinds_raw.items():
        unit_kinds[str(kind)] = UnitKindGate(
            unique=bool(body.get("unique", False)),
            required=bool(body.get("required", False)),
            enabled=bool(body.get("enabled", False)),
        )
    if "main" not in unit_kinds:
        raise ValueError("board.yaml unit_kinds 须包含 main")

    unit_defaults: dict[str, UnitDefaultsConfig] = {}
    for kind, body in defaults_raw.items():
        unit_defaults[str(kind)] = UnitDefaultsConfig(
            speed=int(body.get("speed", 5)),
            can_fly=bool(body.get("can_fly", False)),
            attack_range=int(body.get("attack_range", 1)),
            attack_kind=str(body.get("attack_kind", "melee_physical")),
            atk_ratio=float(body.get("atk_ratio", 1.0)),
            hp_ratio=float(body.get("hp_ratio", 1.0)),
        )

    return BoardConfig(
        size=int(raw.get("size", 7)),
        zones=BoardZonesConfig(
            own_x=tuple(int(x) for x in zones_raw.get("own_x", [0, 1, 2])),
            neutral_x=tuple(int(x) for x in zones_raw.get("neutral_x", [3])),
            enemy_x=tuple(int(x) for x in zones_raw.get("enemy_x", [4, 5, 6])),
        ),
        default_deploy=DeployRectConfig(
            x_min=int(deploy_raw.get("x_min", 0)),
            x_max=int(deploy_raw.get("x_max", 1)),
            y_min=int(deploy_raw.get("y_min", 2)),
            y_max=int(deploy_raw.get("y_max", 4)),
        ),
        default_max_units=int(raw.get("default_max_units", 6)),
        default_anchor=(int(anchor_raw.get("x", 0)), int(anchor_raw.get("y", 3))),
        max_rounds=max_rounds,
        timeout_winner=str(raw.get("timeout_winner", "defender")),
        dice_sides=int(dnd_raw.get("dice_sides", 20)),
        ap_per_turn=int(ai_raw.get("ap_per_turn", 2)),
        land_move_points=int(ai_raw.get("land_move_points", 2)),
        fly_move_points=int(ai_raw.get("fly_move_points", 4)),
        hit_rates={str(k): float(v) for k, v in hit_raw.items()},
        damage_floor=int(raw.get("damage_floor", 0)),
        damage_dice_normalizer=float(raw.get("damage_dice_normalizer", 10.0)),
        max_units_by_major_realm={
            str(k): int(v) for k, v in (raw.get("max_units_by_major_realm") or {}).items()
        },
        unit_kinds=unit_kinds,
        unit_defaults=unit_defaults,
    )


def _parse_formation_layer(raw: dict[str, Any] | None) -> FormationLayerConfig | None:
    """解析阵法四象中的一层（环境 / 天气 / 效果）。"""
    if not raw:
        return None
    return FormationLayerConfig(
        layer_id=str(raw["id"]),
        force_apply=bool(raw.get("force_apply", False)),
        counter_group=(
            str(raw["counter_group"]) if raw.get("counter_group") else None
        ),
        atk_mul=float(raw.get("atk_mul", 1.0)),
        hp_mul=float(raw.get("hp_mul", 1.0)),
    )


def _parse_layer_catalog(raw: dict[str, Any] | None) -> dict[str, LayerCatalogEntry]:
    """
    解析 environment_catalog / weather_catalog / effect_catalog。

    每条必须有 label_zh（§0.0.2）；combat 可选。
    """
    out: dict[str, LayerCatalogEntry] = {}
    for content_id, body in (raw or {}).items():
        if not isinstance(body, dict):
            raise ValueError(f"catalog.{content_id} 须为 mapping")
        label = body.get("label_zh")
        if not label:
            raise ValueError(f"catalog.{content_id} 缺少 label_zh（中文名）")
        combat_raw = body.get("combat") or {}
        if combat_raw and not isinstance(combat_raw, dict):
            raise ValueError(f"catalog.{content_id}.combat 须为 mapping")
        combat = {str(k): float(v) for k, v in combat_raw.items()}
        out[str(content_id)] = LayerCatalogEntry(
            content_id=str(content_id),
            label_zh=str(label),
            summary=str(body.get("summary") or ""),
            combat=combat,
        )
    return out


def _parse_formations(raw: dict[str, Any]) -> FormationsConfig:
    """
    解析 formations.yaml（含 deploy / terrain_layout / force_shifts / catalog）。

    跨 board 的坐标硬校验在 ``load_game_config`` 加载 board 后执行。
    """
    from app.domain.formation_blueprint import (
        parse_deploy_config,
        parse_force_shifts,
        parse_terrain_layout,
    )
    from app.domain.terrain import SEAL_SUBTYPES, TERRAIN_SEAL

    formations_raw = raw.get("formations") or {}
    formations: dict[str, FormationDef] = {}
    for formation_id, body in formations_raw.items():
        terrain_cells = tuple(
            FormationTerrainCell(
                x=int(item["x"]),
                y=int(item["y"]),
                terrain_type=str(item["type"]),
                subtype=str(item.get("subtype", "")),
            )
            for item in (body.get("terrain") or [])
        )
        # 禁制子类枚举校验（M3-D07）
        for cell in terrain_cells:
            if cell.terrain_type == TERRAIN_SEAL:
                if cell.subtype not in SEAL_SUBTYPES:
                    raise ValueError(
                        f"formations.{formation_id} 禁制 subtype 非法："
                        f"{cell.subtype!r}（允许 {sorted(SEAL_SUBTYPES)}）",
                    )
        deploy = parse_deploy_config(body.get("deploy"))
        terrain_layout = parse_terrain_layout(
            body.get("terrain_layout"),
            has_terrain=bool(terrain_cells),
        )
        force_shifts = parse_force_shifts(body.get("force_shifts"))
        formations[str(formation_id)] = FormationDef(
            formation_id=str(formation_id),
            name=str(body["name"]),
            level=int(body.get("level", 0)),
            unlocked_by_default=bool(body.get("unlocked_by_default", False)),
            required_array_level=int(body.get("required_array_level", 0)),
            terrain=terrain_cells,
            environment=_parse_formation_layer(body.get("environment")),
            weather=_parse_formation_layer(body.get("weather")),
            effect=_parse_formation_layer(body.get("effect")),
            deploy=deploy,
            terrain_layout=terrain_layout,
            force_shifts=force_shifts,
        )
    if "none" not in formations:
        raise ValueError("formations.yaml 须包含 none 阵法")

    env_catalog = _parse_layer_catalog(raw.get("environment_catalog"))
    weather_catalog = _parse_layer_catalog(raw.get("weather_catalog"))
    effect_catalog = _parse_layer_catalog(raw.get("effect_catalog"))

    # 阵法引用的环境/天气 id 必须存在于 catalog（有声明才校验）
    for fid, fdef in formations.items():
        if fdef.environment is not None and fdef.environment.layer_id not in env_catalog:
            raise ValueError(
                f"formations.{fid}.environment.id={fdef.environment.layer_id!r} "
                f"不在 environment_catalog",
            )
        if fdef.weather is not None and fdef.weather.layer_id not in weather_catalog:
            raise ValueError(
                f"formations.{fid}.weather.id={fdef.weather.layer_id!r} "
                f"不在 weather_catalog",
            )
        if fdef.effect is not None and fdef.effect.layer_id not in effect_catalog:
            raise ValueError(
                f"formations.{fid}.effect.id={fdef.effect.layer_id!r} "
                f"不在 effect_catalog",
            )

    def _counters(key: str) -> dict[str, dict[str, float]]:
        """解析某层克制表：A → {B: 系数}。"""
        table_raw = raw.get(key) or {}
        return {
            str(a): {str(b): float(mul) for b, mul in (targets or {}).items()}
            for a, targets in table_raw.items()
        }

    return FormationsConfig(
        formations=formations,
        environment_counters=_counters("environment_counters"),
        weather_counters=_counters("weather_counters"),
        effect_counters=_counters("effect_counters"),
        environment_catalog=env_catalog,
        weather_catalog=weather_catalog,
        effect_catalog=effect_catalog,
    )


def _parse_snapshots(raw: dict[str, Any], settings: Any) -> SnapshotsConfig:
    """解析 snapshots.yaml；冷却可被环境变量覆盖。"""
    cooldown_env = getattr(settings, "snapshot_manual_cooldown_seconds", None)
    cooldown = (
        int(cooldown_env)
        if cooldown_env
        else int(raw.get("manual_cooldown_seconds", 3600))
    )
    rewards_raw = raw.get("pvp_rewards") or {}
    win_raw = rewards_raw.get("attacker_win") or {}
    lose_raw = rewards_raw.get("attacker_lose") or {}
    return SnapshotsConfig(
        schema_version=int(raw.get("schema_version", 1)),
        manual_cooldown_seconds=cooldown,
        daily_refresh_hours_utc=tuple(
            int(h) for h in raw.get("daily_refresh_hours_utc", [2, 10, 18])
        ),
        attacker_win=SnapshotRewards(
            cultivation_points=int(win_raw.get("cultivation_points", 0)),
            spirit_stones=int(win_raw.get("spirit_stones", 0)),
        ),
        attacker_lose=SnapshotRewards(
            cultivation_points=int(lose_raw.get("cultivation_points", 0)),
            spirit_stones=int(lose_raw.get("spirit_stones", 0)),
        ),
    )


def _parse_stamina(raw: dict[str, Any]) -> StaminaConfig:
    """解析 stamina.yaml。"""
    return StaminaConfig(
        cap=int(raw.get("cap", 120)),
        regen_per_minute=float(raw.get("regen_per_minute", 0.5)),
        costs={str(k): int(v) for k, v in (raw.get("costs") or {}).items()},
        item_overflow=bool(raw.get("item_overflow", False)),
    )


def _parse_avatar(raw: dict[str, Any]) -> AvatarConfig:
    """
    解析 avatar.yaml（含功能矩阵 / 互传折扣 / 体力）。

    Raises:
        ValueError: max_avatars≠1、retention 非法、feature min_major 缺失等。
    """
    idle = raw.get("idle") or {}
    spirit_raw = idle.get("spirit") or {}
    body_raw = idle.get("body") or {}
    crafting_raw = idle.get("crafting") or {}
    transfer_raw = raw.get("transfer") or {}
    stamina_raw = raw.get("stamina") or {}
    recovery_raw = stamina_raw.get("recovery") or {}

    max_avatars = int(raw.get("max_avatars", 1))
    # 单化身定案：配置层硬拒绝多化身
    if max_avatars != 1:
        raise ValueError("avatar.max_avatars 必须为 1（单化身定案，禁止多化身）")

    retention_ratio = float(transfer_raw.get("retention_ratio", 1.0))
    if not (0.0 < retention_ratio <= 1.0):
        raise ValueError("avatar.transfer.retention_ratio 须满足 (0, 1]")

    retention_by_major_raw = transfer_raw.get("retention_by_major") or {}
    retention_by_major: dict[str, float] = {}
    if isinstance(retention_by_major_raw, dict):
        for major_key, ratio_val in retention_by_major_raw.items():
            r = float(ratio_val)
            if not (0.0 < r <= 1.0):
                raise ValueError(
                    f"avatar.transfer.retention_by_major[{major_key}] 须满足 (0, 1]",
                )
            retention_by_major[str(major_key)] = r

    features_raw = raw.get("feature_unlocks") or {}
    feature_unlocks: dict[str, AvatarFeatureUnlockConfig] = {}
    if isinstance(features_raw, dict):
        for feature_id, body in features_raw.items():
            if not isinstance(body, dict):
                raise ValueError(f"avatar.feature_unlocks.{feature_id} 须为 object")
            min_major = str(body.get("min_major") or "").strip()
            if not min_major:
                raise ValueError(f"avatar.feature_unlocks.{feature_id}.min_major 必填")
            feature_unlocks[str(feature_id)] = AvatarFeatureUnlockConfig(
                feature_id=str(feature_id),
                min_major=min_major,
                label_zh=str(body.get("label_zh") or feature_id),
                summary=str(body.get("summary") or ""),
            )

    cap_by_major_raw = stamina_raw.get("cap_by_major") or {}
    cap_by_major = {
        str(k): int(v) for k, v in cap_by_major_raw.items()
    } if isinstance(cap_by_major_raw, dict) else {}
    action_costs_raw = stamina_raw.get("action_costs") or {}
    action_costs = {
        str(k): int(v) for k, v in action_costs_raw.items()
    } if isinstance(action_costs_raw, dict) else {}

    transfer_cfg = AvatarTransferConfig(
        allow=tuple(str(x) for x in (transfer_raw.get("allow") or ["cultivation_points"])),
        deny=tuple(
            str(x)
            for x in (transfer_raw.get("deny") or ["body_tempering_points", "crafting_exp"])
        ),
        retention_ratio=retention_ratio,
        retention_by_major=retention_by_major,
        min_amount=max(1, int(transfer_raw.get("min_amount", 1))),
        summary=str(transfer_raw.get("summary") or ""),
    )
    stamina_cfg = AvatarStaminaConfig(
        base_cap=int(stamina_raw.get("base_cap", 100)),
        cap_by_major=cap_by_major,
        daily_action_cap=int(stamina_raw.get("daily_action_cap", 10)),
        recovery_per_hour=float(recovery_raw.get("per_hour", 5)),
        recovery_summary=str(recovery_raw.get("summary") or ""),
        action_costs=action_costs,
        allow_stamina_transfer=bool(stamina_raw.get("allow_stamina_transfer", False)),
    )
    assist_raw = raw.get("friend_assist") or {}
    if not isinstance(assist_raw, dict):
        assist_raw = {}
    friend_assist_cfg = AvatarFriendAssistConfig(
        invite_expire_sec=max(0, int(assist_raw.get("invite_expire_sec", 86400))),
        assist_dev_assume_online=bool(assist_raw.get("assist_dev_assume_online", False)),
        stamina_base_cap=max(1, int(assist_raw.get("stamina_base_cap", 50))),
        stamina_cap_by_major={
            str(k): int(v)
            for k, v in (assist_raw.get("stamina_cap_by_major") or {}).items()
        },
        stamina_recovery_per_hour=float(
            assist_raw.get("stamina_recovery_per_hour", 3) or 3,
        ),
        battle_cost=max(1, int(assist_raw.get("battle_cost", 10))),
        resume_ratio=float(assist_raw.get("resume_ratio", 0.2) or 0.2),
    )

    return AvatarConfig(
        unlock_major_realm=str(raw.get("unlock_major_realm", "jindan")),
        max_avatars=max_avatars,
        max_major_realm=str(raw.get("max_major_realm") or AVATAR_DEFAULT_MAX_MAJOR_REALM).strip()
        or AVATAR_DEFAULT_MAX_MAJOR_REALM,
        avatar_lead_majors=max(0, int(raw.get("avatar_lead_majors", AVATAR_DEFAULT_LEAD_MAJORS) or 0)),
        initial_stat_ratio=float(raw.get("initial_stat_ratio", 0.5)),
        material_mod_placeholder=float(raw.get("material_mod_placeholder", 1.0)),
        condense_spirit_stone_cost=int(raw.get("condense_spirit_stone_cost", 1000)),
        condense_cultivation_cost=max(0, int(raw.get("condense_cultivation_cost", 0) or 0)),
        condense_technique_ids=tuple(
            str(x).strip()
            for x in (raw.get("condense_technique_ids") or [])
            if str(x).strip()
        ),
        condense_medium_item_ids=tuple(
            str(x).strip()
            for x in (raw.get("condense_medium_item_ids") or [])
            if str(x).strip()
        ),
        condense_medium_quantity=max(1, int(raw.get("condense_medium_quantity", 1) or 1)),
        spirit_rates=AvatarIdleRates(
            enabled=True,
            gain_per_tick=int(spirit_raw.get("cultivation_per_tick", 6)),
        ),
        body_rates=AvatarIdleRates(
            enabled=bool(body_raw.get("enabled", True)),
            gain_per_tick=int(body_raw.get("body_tempering_per_tick", 5)),
        ),
        crafting_rates=AvatarIdleRates(
            enabled=True,
            gain_per_tick=int(crafting_raw.get("crafting_exp_per_tick", 6)),
        ),
        spirit_stone_cost_per_tick_ratio=float(
            raw.get("spirit_stone_cost_per_tick_ratio", 0.8),
        ),
        transfer_allow=transfer_cfg.allow,
        transfer_deny=transfer_cfg.deny,
        feature_unlocks=feature_unlocks,
        transfer=transfer_cfg,
        stamina=stamina_cfg,
        friend_assist=friend_assist_cfg,
    )


def _parse_divine_sense(raw: dict[str, Any]) -> DivineSenseConfig:
    """解析 divine_sense.yaml（含 M4-D03 阶梯/反噬表）。"""
    costs = raw.get("costs") or {}
    bonus_raw = raw.get("per_realm_bonus") or {}
    bands_raw = raw.get("overload_bands") or []
    bands: list[DivineSenseOverloadBandConfig] = []
    if isinstance(bands_raw, list):
        for i, row in enumerate(bands_raw):
            if not isinstance(row, dict):
                raise ValueError(f"divine_sense.overload_bands[{i}] must be a mapping")
            max_r = row.get("max_load_ratio")
            bands.append(
                DivineSenseOverloadBandConfig(
                    max_load_ratio=None if max_r is None else float(max_r),
                    combat_stat_mult=float(row.get("combat_stat_mult", 0.7)),
                    zone=str(row.get("zone") or "overload"),
                ),
            )
    table_raw = raw.get("backlash_table") or []
    table: list[DivineSenseBacklashConfig] = []
    if isinstance(table_raw, list):
        for i, row in enumerate(table_raw):
            if not isinstance(row, dict):
                raise ValueError(f"divine_sense.backlash_table[{i}] must be a mapping")
            table.append(
                DivineSenseBacklashConfig(
                    id=str(row.get("id") or row.get("when") or f"tier_{i}"),
                    when=str(row.get("when") or "over_hard"),
                    idle_mult=float(row.get("idle_mult", 0.5)),
                    set_flag=bool(row.get("set_flag", True)),
                    summary=str(row.get("summary") or ""),
                ),
            )
    return DivineSenseConfig(
        base_capacity=int(raw.get("base_capacity", 10)),
        per_realm_bonus={str(k): int(v) for k, v in bonus_raw.items()},
        cost_avatar=int(costs.get("avatar", 5)),
        cost_pet=int(costs.get("pet", 3)),
        cost_puppet=int(costs.get("puppet", 2)),
        puppet_loadout_max=int(raw.get("puppet_loadout_max", 3)),
        soft_ratio=float(raw.get("soft_ratio", 1.0)),
        hard_ratio=float(raw.get("hard_ratio", 1.5)),
        overload_stat_mult=float(raw.get("overload_stat_mult", 0.7)),
        backlash_idle_mult=float(raw.get("backlash_idle_mult", 0.5)),
        overload_bands=tuple(bands),
        backlash_table=tuple(table),
    )


def _parse_craft_recipes(raw: dict[str, Any]) -> CraftRecipesConfig:
    """解析 craft_recipes.yaml。"""
    recipes_raw = raw.get("recipes") or {}
    recipes: dict[str, CraftRecipe] = {}
    for recipe_id, body in recipes_raw.items():
        mats = tuple(
            CraftMaterial(item_id=str(m["item_id"]), quantity=int(m["quantity"]))
            for m in (body.get("materials") or [])
        )
        outputs: list[CraftRecipeOutput] = []
        for out in body.get("outputs") or []:
            grant_lv = int(out.get("grant_craft_level") or 0)
            if out.get("grant_array_craft_level"):
                outputs.append(
                    CraftRecipeOutput(
                        item_type=None,
                        item_id=None,
                        quantity=0,
                        grant_array_craft_level=int(out["grant_array_craft_level"]),
                        grant_craft_level=grant_lv,
                    ),
                )
            else:
                outputs.append(
                    CraftRecipeOutput(
                        item_type=str(out.get("item_type", "material")),
                        item_id=str(out["item_id"]),
                        quantity=int(out.get("quantity", 1)),
                        grant_array_craft_level=0,
                        grant_craft_level=grant_lv,
                    ),
                )
        recipes[str(recipe_id)] = CraftRecipe(
            recipe_id=str(recipe_id),
            branch=str(body.get("branch", "alchemy")),
            name=str(body.get("name", recipe_id)),
            duration_seconds=int(body.get("duration_seconds", 60)),
            fail_chance=float(body.get("fail_chance", 0.0)),
            spirit_stone_cost=int(body.get("spirit_stone_cost", 0)),
            stamina_cost=int(body.get("stamina_cost", 0)),
            materials=mats,
            outputs=tuple(outputs),
            required_craft_level=int(body.get("required_craft_level") or 0),
            recipe_tier=int(body.get("recipe_tier") or 1),
            grant_craft_level=int(body.get("grant_craft_level") or 0),
        )
    quality_bands: list[dict[str, Any]] = []
    for band in raw.get("quality_by_level_delta") or []:
        weights = band.get("weights") or {}
        quality_bands.append(
            {
                "min_delta": int(band.get("min_delta") or 0),
                "weights": {str(k): int(v) for k, v in dict(weights).items()},
            },
        )
    quality_bands.sort(key=lambda row: int(row.get("min_delta") or 0))
    return CraftRecipesConfig(
        main_crafting_bonus=float(raw.get("main_crafting_bonus", 1.25)),
        max_jobs_per_actor=int(raw.get("max_jobs_per_actor", 1)),
        recipes=recipes,
        quality_by_level_delta=tuple(quality_bands),
    )


_ALLOWED_PET_RARITIES = frozenset({"common", "rare", "epic", "legendary"})
_ALLOWED_AFFIX_TIERS = frozenset({"common", "rare", "epic", "legendary"})
_ALLOWED_AFFIX_KINDS = frozenset(
    {
        "flat_atk",
        "flat_hp",
        "flat_speed",
        "pct_atk",
        "pct_hp",
        "pct_speed",
        "passive_ref",
    },
)


def _parse_pets(raw: dict[str, Any]) -> PetsConfig:
    """
    解析 pets.yaml（及可选 sect_reroll 合并字段）。

    Raises:
        ValueError: 种族外键非法、稀有度非法、空物种表等配置错误。
    """
    races_raw = raw.get("races") or {}
    races: dict[str, PetRaceConfig] = {}
    for race_id, body in races_raw.items():
        if not isinstance(body, dict):
            raise ValueError(f"pets.races.{race_id} must be a mapping")
        races[str(race_id)] = PetRaceConfig(
            race_id=str(race_id),
            name=str(body.get("name", race_id)),
            racial_talent_id=str(body.get("racial_talent_id", "")),
            base_capture_rate=float(body.get("base_capture_rate", 0.3)),
        )

    grades_raw = raw.get("grades") or {}
    grades: dict[int, PetGradeConfig] = {}
    for grade_key, body in grades_raw.items():
        if not isinstance(body, dict):
            raise ValueError(f"pets.grades.{grade_key} must be a mapping")
        grade_num = int(grade_key)
        grades[grade_num] = PetGradeConfig(
            grade=grade_num,
            name=str(body.get("name", f"grade_{grade_num}")),
            affix_slots=int(body.get("affix_slots", 3)),
            type_reroll_slots=int(body.get("type_reroll_slots", 1)),
            base_mult=float(body.get("base_mult", 1.0)),
        )

    species_raw = raw.get("species") or {}
    if not species_raw:
        raise ValueError("pets.species must not be empty")
    species: dict[str, PetSpeciesConfig] = {}
    for species_id, body in species_raw.items():
        if not isinstance(body, dict):
            raise ValueError(f"pets.species.{species_id} must be a mapping")
        race = str(body.get("race") or "").strip()
        if not race:
            if "beast" in races:
                race = "beast"
            elif races:
                race = next(iter(races))
            else:
                raise ValueError(f"pets.species.{species_id}: missing race and no races table")
        if races and race not in races:
            raise ValueError(f"pets.species.{species_id}: unknown race '{race}'")
        rarity = str(body.get("rarity") or "common").strip().lower()
        if rarity not in _ALLOWED_PET_RARITIES:
            raise ValueError(f"pets.species.{species_id}: illegal rarity '{rarity}'")
        roles_raw = body.get("roles") or []
        tags_raw = body.get("acquire_tags") or ["gm_grant"]
        growth_raw = body.get("growth") or {}
        growth = {
            "atk": float(growth_raw.get("atk", 1.0)),
            "hp": float(growth_raw.get("hp", 1.0)),
            "speed": float(growth_raw.get("speed", 1.0)),
        }
        ds_cost = body.get("divine_sense_cost")
        species[str(species_id)] = PetSpeciesConfig(
            species_id=str(species_id),
            name=str(body.get("name", species_id)),
            race=race,
            rarity=rarity,
            roles=tuple(str(x) for x in roles_raw),
            acquire_tags=tuple(str(x) for x in tags_raw),
            skill_pool_id=str(body.get("skill_pool_id") or ""),
            passive_pool_id=str(body.get("passive_pool_id") or ""),
            base_atk=int(body.get("base_atk", 5)),
            base_hp=int(body.get("base_hp", 20)),
            base_speed=int(body.get("base_speed", 10)),
            growth=growth,
            upgrade_cost=dict(body.get("upgrade_cost") or {}),
            divine_sense_cost=int(ds_cost) if ds_cost is not None else None,
            evolve_to=str(body["evolve_to"]) if body.get("evolve_to") else None,
        )

    weight_raw = raw.get("capture_test_weights") or {
        "common": 70,
        "rare": 25,
        "epic": 5,
        "legendary": 0,
    }
    capture_test_weights = {str(k): int(v) for k, v in weight_raw.items()}

    grade_w_raw = raw.get("capture_test_grade_weights") or {1: 100}
    capture_test_grade_weights = {int(k): int(v) for k, v in grade_w_raw.items()}
    if grades:
        for g in capture_test_grade_weights:
            if g not in grades:
                raise ValueError(f"capture_test_grade_weights unknown grade {g}")

    sect_reroll = dict(raw.get("sect_reroll") or {})
    grade_up = dict(raw.get("grade_up") or {})
    if grade_up:
        max_g = int(grade_up.get("max_grade", 7))
        if grades and max_g not in grades and max_g > max(grades.keys()):
            raise ValueError(f"pets.grade_up.max_grade {max_g} exceeds grades table")

    return PetsConfig(
        hold_cap=int(raw.get("hold_cap", 5)),
        level_stat_bonus=float(raw.get("level_stat_bonus", 0.05)),
        races=races,
        grades=grades,
        species=species,
        capture_test_weights=capture_test_weights,
        capture_test_grade_weights=capture_test_grade_weights,
        sect_reroll=sect_reroll,
        grade_up=grade_up,
    )


def _parse_pet_affixes(raw: dict[str, Any]) -> PetAffixesConfig:
    """
    解析 pet_affixes.yaml（PET-D01 词条热插拔库）。

    Raises:
        ValueError: 类型空表、非法 kind/tier、权重缺类型等。
    """
    types_raw = raw.get("types") or {}
    if not types_raw:
        raise ValueError("pet_affixes.types must not be empty")

    types: dict[str, PetAffixTypeConfig] = {}
    for type_id, body in types_raw.items():
        if not isinstance(body, dict):
            raise ValueError(f"pet_affixes.types.{type_id} must be a mapping")
        kind = str(body.get("kind") or "").strip()
        if kind not in _ALLOWED_AFFIX_KINDS:
            raise ValueError(f"pet_affixes.types.{type_id}: illegal kind '{kind}'")
        ranges_raw = body.get("tier_ranges") or {}
        if not isinstance(ranges_raw, dict) or not ranges_raw:
            raise ValueError(f"pet_affixes.types.{type_id}: tier_ranges required")
        tier_ranges: dict[str, PetAffixTierRange] = {}
        for tier, rng in ranges_raw.items():
            tier_key = str(tier).strip().lower()
            if tier_key not in _ALLOWED_AFFIX_TIERS:
                raise ValueError(f"pet_affixes.types.{type_id}: illegal tier '{tier}'")
            if not isinstance(rng, dict):
                raise ValueError(f"pet_affixes.types.{type_id}.tier_ranges.{tier} must be mapping")
            min_v = float(rng.get("min", 0))
            max_v = float(rng.get("max", min_v))
            if max_v < min_v:
                raise ValueError(
                    f"pet_affixes.types.{type_id}.tier_ranges.{tier}: max < min",
                )
            tier_ranges[tier_key] = PetAffixTierRange(min_value=min_v, max_value=max_v)
        passive_id = body.get("passive_id")
        if kind == "passive_ref" and not passive_id:
            raise ValueError(f"pet_affixes.types.{type_id}: passive_ref requires passive_id")
        types[str(type_id)] = PetAffixTypeConfig(
            affix_type_id=str(type_id),
            name=str(body.get("name", type_id)),
            kind=kind,
            tier_ranges=tier_ranges,
            passive_id=str(passive_id) if passive_id else None,
        )

    type_weights_raw = raw.get("type_weights") or {}
    type_weights = {str(k): int(v) for k, v in type_weights_raw.items()}
    for tid in type_weights:
        if tid not in types:
            raise ValueError(f"pet_affixes.type_weights unknown type '{tid}'")
    # 未写权重的类型默认 0（不进抽池）；至少一种权重 > 0
    if not any(w > 0 for w in type_weights.values()):
        # 缺省：每种类型权重 1
        type_weights = {tid: 1 for tid in types}

    tier_weights_raw = raw.get("tier_weights") or {
        "common": 55,
        "rare": 28,
        "epic": 14,
        "legendary": 3,
    }
    tier_weights = {str(k).lower(): int(v) for k, v in tier_weights_raw.items()}
    for tier in tier_weights:
        if tier not in _ALLOWED_AFFIX_TIERS:
            raise ValueError(f"pet_affixes.tier_weights illegal tier '{tier}'")

    value_reroll = dict(raw.get("value_reroll") or {})
    if "spirit_stones_base" not in value_reroll:
        value_reroll["spirit_stones_base"] = 50
    if "grow" not in value_reroll:
        value_reroll["grow"] = 0.1

    return PetAffixesConfig(
        types=types,
        type_weights=type_weights,
        tier_weights=tier_weights,
        value_reroll=value_reroll,
    )


_ALLOWED_SKILL_CATEGORIES = frozenset({"physical", "special", "status"})
_ALLOWED_BOOK_SCOPES = frozenset({"universal", "race", "species"})


def _parse_pet_skills(raw: dict[str, Any]) -> PetSkillsConfig:
    """
    解析 pet_skills.yaml（PET-D02）。

    Raises:
        ValueError: 技能/池空表、外键或 category 非法。
    """
    skills_raw = raw.get("skills") or {}
    if not skills_raw:
        raise ValueError("pet_skills.skills must not be empty")
    skills: dict[str, PetSkillConfig] = {}
    for skill_id, body in skills_raw.items():
        if not isinstance(body, dict):
            raise ValueError(f"pet_skills.skills.{skill_id} must be a mapping")
        category = str(body.get("category") or "physical").strip().lower()
        if category not in _ALLOWED_SKILL_CATEGORIES:
            raise ValueError(f"pet_skills.skills.{skill_id}: illegal category '{category}'")
        tags_raw = body.get("mutex_tags") or []
        skills[str(skill_id)] = PetSkillConfig(
            skill_id=str(skill_id),
            name=str(body.get("name", skill_id)),
            power=int(body.get("power", 0)),
            accuracy=int(body.get("accuracy", 100)),
            category=category,
            priority=int(body.get("priority", 0)),
            pp=int(body.get("pp", 20)),
            mutex_tags=tuple(str(x) for x in tags_raw),
        )

    pools_raw = raw.get("pools") or {}
    if not pools_raw:
        raise ValueError("pet_skills.pools must not be empty")
    pools: dict[str, PetSkillPoolConfig] = {}
    for pool_id, body in pools_raw.items():
        if not isinstance(body, dict):
            raise ValueError(f"pet_skills.pools.{pool_id} must be a mapping")
        skill_ids = tuple(str(x) for x in (body.get("skill_ids") or []))
        for sid in skill_ids:
            if sid not in skills:
                raise ValueError(f"pet_skills.pools.{pool_id}: unknown skill '{sid}'")
        default_learned = tuple(str(x) for x in (body.get("default_learned") or []))
        default_equipped = tuple(str(x) for x in (body.get("default_equipped") or []))
        for sid in default_learned + default_equipped:
            if sid and sid not in skill_ids:
                raise ValueError(
                    f"pet_skills.pools.{pool_id}: default skill '{sid}' not in skill_ids",
                )
        pools[str(pool_id)] = PetSkillPoolConfig(
            pool_id=str(pool_id),
            name=str(body.get("name", pool_id)),
            skill_ids=skill_ids,
            default_learned=default_learned,
            default_equipped=default_equipped,
        )

    equip_slots = int(raw.get("equip_slots", 4))
    if equip_slots < 1 or equip_slots > 4:
        raise ValueError("pet_skills.equip_slots must be 1..4")

    return PetSkillsConfig(equip_slots=equip_slots, skills=skills, pools=pools)


def _parse_pet_skill_books(
    raw: dict[str, Any],
    *,
    skills: dict[str, PetSkillConfig],
    races: dict[str, Any],
) -> PetSkillBooksConfig:
    """
    解析 pet_skill_books.yaml；校验 skill_id / race 外键。

    Raises:
        ValueError: scope 非法或外键缺失。
    """
    books_raw = raw.get("books") or {}
    books: dict[str, PetSkillBookConfig] = {}
    for book_id, body in books_raw.items():
        if not isinstance(body, dict):
            raise ValueError(f"pet_skill_books.books.{book_id} must be a mapping")
        skill_id = str(body.get("skill_id") or "").strip()
        if not skill_id or skill_id not in skills:
            raise ValueError(f"pet_skill_books.books.{book_id}: unknown skill_id '{skill_id}'")
        scope = str(body.get("scope") or "universal").strip().lower()
        if scope not in _ALLOWED_BOOK_SCOPES:
            raise ValueError(f"pet_skill_books.books.{book_id}: illegal scope '{scope}'")
        race_id = str(body["race_id"]).strip() if body.get("race_id") else None
        species_id = str(body["species_id"]).strip() if body.get("species_id") else None
        if scope == "race":
            if not race_id:
                raise ValueError(f"pet_skill_books.books.{book_id}: race scope requires race_id")
            if races and race_id not in races:
                raise ValueError(f"pet_skill_books.books.{book_id}: unknown race '{race_id}'")
        if scope == "species" and not species_id:
            raise ValueError(f"pet_skill_books.books.{book_id}: species scope requires species_id")
        books[str(book_id)] = PetSkillBookConfig(
            book_id=str(book_id),
            name=str(body.get("name", book_id)),
            skill_id=skill_id,
            scope=scope,
            race_id=race_id,
            species_id=species_id,
        )
    return PetSkillBooksConfig(books=books)


def _parse_pet_duel(raw: dict[str, Any]) -> PetDuelConfig:
    """
    解析 pet_duel.yaml（PET-D05）。

    Raises:
        ValueError: 缺 struggle / NPC 非法。
    """
    struggle = dict(raw.get("default_struggle") or {})
    if not struggle.get("skill_id"):
        raise ValueError("pet_duel.default_struggle.skill_id required")
    npcs_raw = raw.get("npc_templates") or {}
    npcs: dict[str, PetDuelNpcConfig] = {}
    for npc_id, body in npcs_raw.items():
        if not isinstance(body, dict):
            raise ValueError(f"pet_duel.npc_templates.{npc_id} must be a mapping")
        skills = tuple(str(x) for x in (body.get("skill_ids") or []))
        npcs[str(npc_id)] = PetDuelNpcConfig(
            npc_id=str(npc_id),
            name=str(body.get("name", npc_id)),
            species_id=str(body.get("species_id") or ""),
            grade=int(body.get("grade", 1)),
            level=int(body.get("level", 1)),
            skill_ids=skills,
        )
        if not npcs[str(npc_id)].species_id:
            raise ValueError(f"pet_duel.npc_templates.{npc_id}: species_id required")
    return PetDuelConfig(
        max_rounds=int(raw.get("max_rounds", 40)),
        damage_divisor=float(raw.get("damage_divisor", 50)),
        damage_roll_min=float(raw.get("damage_roll_min", 0.85)),
        damage_roll_max=float(raw.get("damage_roll_max", 1.0)),
        accuracy_enabled=bool(raw.get("accuracy_enabled", True)),
        speed_tie_break=str(raw.get("speed_tie_break", "seed_parity")),
        default_struggle=struggle,
        npc_templates=npcs,
    )


def _parse_pet_passives(raw: dict[str, Any]) -> PetPassivesConfig:
    """
    解析 pet_passives.yaml（PET-D03）。

    Raises:
        ValueError: 被动缺名 / 池引用未知被动 / domain 非法。
    """
    allowed_domains = {"combat", "life", "cultivation"}
    passives_raw = raw.get("passives") or {}
    passives: dict[str, PetPassiveConfig] = {}
    for pid, body in passives_raw.items():
        if not isinstance(body, dict):
            raise ValueError(f"pet_passives.passives.{pid} must be a mapping")
        domain = str(body.get("effect_domain", "combat"))
        if domain not in allowed_domains:
            raise ValueError(f"pet_passives.passives.{pid}: bad effect_domain '{domain}'")
        effects_raw = body.get("effects") or {}
        effects = {str(k): float(v) for k, v in effects_raw.items()} if isinstance(effects_raw, dict) else {}
        passives[str(pid)] = PetPassiveConfig(
            passive_id=str(pid),
            name=str(body.get("name", pid)),
            kind=str(body.get("kind", "independent")),
            effect_domain=domain,
            effects=effects,
            summary=str(body.get("summary", "")),
        )

    pools_raw = raw.get("pools") or {}
    pools: dict[str, PetPassivePoolConfig] = {}
    for pool_id, body in pools_raw.items():
        if not isinstance(body, dict):
            raise ValueError(f"pet_passives.pools.{pool_id} must be a mapping")
        weights = {str(k): int(v) for k, v in (body.get("weights") or {}).items()}
        for pid in weights:
            if pid not in passives:
                raise ValueError(f"pet_passives.pools.{pool_id}: unknown passive '{pid}'")
        pools[str(pool_id)] = PetPassivePoolConfig(
            pool_id=str(pool_id),
            empty_weight=max(0, int(body.get("empty_weight", 0))),
            weights=weights,
        )
    return PetPassivesConfig(passives=passives, pools=pools)


def _parse_pet_feed(raw: dict[str, Any]) -> PetFeedConfig:
    """
    解析 pet_feed.yaml（PET-D04）。

    Raises:
        ValueError: 兽丹缺 effects / per_item_cap 非法。
    """
    items_raw = raw.get("items") or {}
    items: dict[str, PetFeedItemConfig] = {}
    for item_id, body in items_raw.items():
        if not isinstance(body, dict):
            raise ValueError(f"pet_feed.items.{item_id} must be a mapping")
        effects_raw = body.get("effects") or {}
        if not isinstance(effects_raw, dict) or not effects_raw:
            raise ValueError(f"pet_feed.items.{item_id}: effects required")
        effects = {str(k): float(v) for k, v in effects_raw.items()}
        items[str(item_id)] = PetFeedItemConfig(
            item_id=str(item_id),
            name=str(body.get("name", item_id)),
            per_item_cap=max(0, int(body.get("per_item_cap", 0))),
            effects=effects,
            summary=str(body.get("summary", "")),
        )
    by_grade = {int(k): int(v) for k, v in (raw.get("total_feed_cap_by_grade") or {}).items()}
    by_species = {str(k): int(v) for k, v in (raw.get("total_feed_cap_by_species") or {}).items()}
    return PetFeedConfig(
        total_feed_cap=max(0, int(raw.get("total_feed_cap", 0))),
        total_feed_cap_by_grade=by_grade,
        total_feed_cap_by_species=by_species,
        items=items,
    )


def _parse_pet_eggs(raw: dict[str, Any]) -> PetEggsConfig:
    """
    解析 pet_eggs.yaml（N5）。

    Raises:
        ValueError: 蛋缺 species_id 或 hatch_seconds 非法。
    """
    eggs_raw = raw.get("eggs") or {}
    eggs: dict[str, PetEggConfig] = {}
    for egg_id, body in eggs_raw.items():
        if not isinstance(body, dict):
            raise ValueError(f"pet_eggs.eggs.{egg_id} must be a mapping")
        species_id = str(body.get("species_id") or "").strip()
        if not species_id:
            raise ValueError(f"pet_eggs.eggs.{egg_id}: species_id required")
        gw_raw = body.get("grade_weights") or {}
        grade_weights = {int(k): int(v) for k, v in gw_raw.items()} if gw_raw else {}
        eggs[str(egg_id)] = PetEggConfig(
            egg_id=str(egg_id),
            name=str(body.get("name", egg_id)),
            species_id=species_id,
            hatch_seconds=max(0, int(body.get("hatch_seconds", 0))),
            spirit_stones=max(0, int(body.get("spirit_stones", 0))),
            grade_weights=grade_weights,
        )
    return PetEggsConfig(
        max_concurrent=max(0, int(raw.get("max_concurrent", 0))),
        eggs=eggs,
    )


def _parse_pet_encounter(raw: dict[str, Any]) -> PetEncounterConfig:
    """
    解析 pet_encounter.yaml（M4-D04c）。

    Args:
        raw: YAML 根对象。

    Returns:
        PetEncounterConfig。
    """
    types = tuple(str(x) for x in (raw.get("capturable_types") or ["spirit_beast"]))
    tables_raw = raw.get("tables") or []
    if not isinstance(tables_raw, list):
        raise ValueError("pet_encounter.tables must be a list")
    tables: list[dict[str, Any]] = []
    for i, row in enumerate(tables_raw):
        if not isinstance(row, dict):
            raise ValueError(f"pet_encounter.tables[{i}] must be a mapping")
        entries = row.get("entries") or []
        if not isinstance(entries, list):
            raise ValueError(f"pet_encounter.tables[{i}].entries must be a list")
        normalized_entries: list[dict[str, Any]] = []
        for j, ent in enumerate(entries):
            if not isinstance(ent, dict):
                raise ValueError(f"pet_encounter.tables[{i}].entries[{j}] must be a mapping")
            gw = {int(k): int(v) for k, v in (ent.get("grade_weights") or {}).items()}
            normalized_entries.append(
                {
                    "type": str(ent.get("type") or "monster"),
                    "species_id": str(ent.get("species_id") or "").strip(),
                    "weight": int(ent.get("weight") or 0),
                    "label": str(ent.get("label") or ""),
                    "grade_weights": gw,
                },
            )
        tables.append(
            {
                "region_id": str(row.get("region_id") or "*"),
                "shichen": str(row.get("shichen") or "*"),
                "weather": str(row.get("weather") or "*"),
                "entries": normalized_entries,
            },
        )
    return PetEncounterConfig(
        capturable_types=types,
        skip_battle=bool(raw.get("skip_battle", True)),
        tables=tuple(tables),
    )


def _parse_pet_capture(raw: dict[str, Any]) -> PetCaptureConfig:
    """
    解析 pet_capture.yaml（M4-D04c）。

    Args:
        raw: YAML 根对象。

    Returns:
        PetCaptureConfig。
    """
    lure = str(raw.get("lure_item_id") or "pet_lure_grass").strip()
    bag = str(raw.get("bag_item_id") or "pet_spirit_bag").strip()
    if not lure or not bag:
        raise ValueError("pet_capture.lure_item_id / bag_item_id required")
    rd = raw.get("realm_diff") or {}
    auto = raw.get("auto_capture") or {}
    root_raw = raw.get("root_affinity") or {}
    root: dict[str, dict[str, float]] = {}
    for tag, races in root_raw.items():
        if isinstance(races, dict):
            root[str(tag)] = {str(rk): float(rv) for rk, rv in races.items()}
    return PetCaptureConfig(
        lure_item_id=lure,
        bag_item_id=bag,
        require_bag=bool(raw.get("require_bag", True)),
        daily_attempt_cap=int(raw.get("daily_attempt_cap") or 0),
        special_affix_min_tier=str(raw.get("special_affix_min_tier") or "rare"),
        pen_affix=float(raw.get("pen_affix") or 0.05),
        pen_grade={int(k): float(v) for k, v in (raw.get("pen_grade") or {}).items()},
        realm_diff_beast_stages_per_grade=int(rd.get("beast_stages_per_grade") or 8),
        realm_diff_per_stage=float(rd.get("per_stage") or 0.015),
        realm_diff_clamp_min=float(rd.get("clamp_min") or -0.25),
        realm_diff_clamp_max=float(rd.get("clamp_max") or 0.25),
        root_affinity=root,
        taming_tech_bonus={
            str(k): float(v) for k, v in (raw.get("taming_tech_bonus") or {}).items()
        },
        species_capture_override={
            str(k): float(v) for k, v in (raw.get("species_capture_override") or {}).items()
        },
        auto_capture_enabled=bool(auto.get("enabled", False)),
        auto_capture_max_rolls=int(auto.get("max_rolls") or 5),
        estimate_special_affixes=bool(raw.get("estimate_special_affixes", True)),
    )


def _parse_item_inspect(body: dict[str, Any]) -> ItemInspectDef:
    """Parse optional inspect block; missing keys stay 0 / 无 so hover layout is stable."""
    raw = body.get("inspect")
    inspect_raw = raw if isinstance(raw, dict) else {}
    use_eff = body.get("use_effect")
    effects_raw = inspect_raw.get("effects")
    effects: tuple[str, ...] = ()
    if isinstance(effects_raw, list):
        effects = tuple(str(x).strip() for x in effects_raw if str(x).strip())
    if not effects and isinstance(use_eff, dict):
        kind_zh = USE_EFFECT_KIND_LABEL_ZH.get(str(use_eff.get("kind") or ""), "")
        if kind_zh:
            effects = (kind_zh,)
    help_zh = str(inspect_raw.get("help_zh") or body.get("description") or "").strip()
    realm_req = str(inspect_raw.get("realm_req_zh") or INSPECT_REALM_NONE_ZH).strip()
    return ItemInspectDef(
        realm_req_zh=realm_req or INSPECT_REALM_NONE_ZH,
        help_zh=help_zh,
        effects=effects,
        element=normalize_inspect_element(inspect_raw.get("element")),
    )


def _parse_inventory(raw: dict[str, Any]) -> InventoryConfig:
    """解析 inventory.yaml。"""
    stack_raw = raw.get("stack_rules") or {}
    items_raw = raw.get("items") or {}
    items: dict[str, InventoryItemDef] = {}
    for item_id, body in items_raw.items():
        use_eff = body.get("use_effect")
        bag_raw = body.get("bag_allowed")
        if bag_raw is None:
            bag_allowed: tuple[str, ...] = ("normal",)
        else:
            bag_allowed = tuple(str(x) for x in bag_raw)
        items[str(item_id)] = InventoryItemDef(
            item_id=str(item_id),
            name=str(body.get("name", item_id)),
            item_type=str(body.get("item_type", "material")),
            max_stack=int(body.get("max_stack", stack_raw.get("default_max_stack", 99))),
            use_effect=dict(use_eff) if use_eff else None,
            bag_allowed=bag_allowed,
            tradable=bool(body.get("tradable", True)),
            bound=bool(body.get("bound", False)),
            unique=bool(body.get("unique", False)),
            actor_def_id=(
                str(body["actor_def_id"]) if body.get("actor_def_id") else None
            ),
            manual_kind=(str(body["manual_kind"]) if body.get("manual_kind") else None),
            unlock_recipe_id=(
                str(body["unlock_recipe_id"]) if body.get("unlock_recipe_id") else None
            ),
            talisman_effect_id=(
                str(body["talisman_effect_id"]).strip()
                if body.get("talisman_effect_id")
                else None
            ),
            inspect=_parse_item_inspect(body if isinstance(body, dict) else {}),
        )
    by_type = {
        str(k): int(v) for k, v in (stack_raw.get("by_item_type") or {}).items()
    }
    return InventoryConfig(
        stack_rules=InventoryStackRules(
            default_max_stack=int(stack_raw.get("default_max_stack", 99)),
            by_item_type=by_type,
        ),
        item_types=tuple(str(x) for x in (raw.get("item_types") or [])),
        items=items,
    )


def _parse_equipment(raw: dict[str, Any], *, combat_attrs: CombatAttrsConfig) -> EquipmentConfig:
    """解析 equipment.yaml；stats 键须 ∈ combat_attrs.attrs。"""
    items_raw = raw.get("items") or {}
    items: dict[str, EquipmentItemDef] = {}
    allowed_keys = set(combat_attrs.attrs.keys())
    for item_id, body in items_raw.items():
        stats_raw = body.get("stats") or {}
        stats: dict[str, float] = {}
        for key, val in stats_raw.items():
            sk = str(key)
            if sk not in allowed_keys:
                raise ValueError(f"equipment.{item_id}.stats.{sk}: unknown combat attr key")
            stats[sk] = float(val)
        dice_raw = body.get("dice_mods") or {}
        dice_mods = {
            "min_bonus": int(dice_raw.get("min_bonus", 0) or 0),
            "max_bonus": int(dice_raw.get("max_bonus", 0) or 0),
        }
        idle_raw = body.get("idle_mods") or {}
        idle_mods = {
            "idle_mult": float(idle_raw.get("idle_mult", 1.0) or 1.0),
        }
        grants = tuple(str(x) for x in (body.get("grants") or []))
        req = body.get("required_major_realm")
        # equip_kind falls back when slot omitted (道具专文 §5)
        slot_raw = body.get("equip_kind") or body.get("slot") or ""
        items[str(item_id)] = EquipmentItemDef(
            item_id=str(item_id),
            label_zh=str(body.get("label_zh", item_id)),
            help_zh=str(body.get("help_zh", "")),
            slot=str(slot_raw),
            stats=stats,
            dice_mods=dice_mods,
            idle_mods=idle_mods,
            grants=grants,
            required_major_realm=str(req) if req else None,
        )
    return EquipmentConfig(items=items)


def _parse_talisman_effects(raw: dict[str, Any]) -> dict[str, TalismanEffectDef]:
    """Parse talisman_effects.yaml whitelist; require label_zh and known trigger."""
    from app.config_source.validate_content import validate_talisman_effects_raw

    validate_talisman_effects_raw(raw)
    effects: dict[str, TalismanEffectDef] = {}
    for effect_id, body in (raw or {}).items():
        effects[str(effect_id)] = TalismanEffectDef(
            effect_id=str(effect_id),
            label_zh=str(body["label_zh"]).strip(),
            help_zh=str(body.get("help_zh") or ""),
            trigger=str(body.get("trigger") or "").strip(),
            kind=str(body.get("kind") or "buff"),
            stack_group=str(body.get("stack_group") or effect_id),
            magnitude=float(body.get("magnitude") or 0.0),
            duration_kind=str(body.get("duration_kind") or "global"),
            duration=int(body.get("duration") or 0),
            attr=str(body.get("attr") or "phys_atk"),
            use_chance=float(body.get("use_chance") or 0.0),
            hit_chance=float(body.get("hit_chance") or 1.0),
        )
    return effects


def _parse_int_tuple(raw: Any, default: tuple[int, ...]) -> tuple[int, ...]:
    """Coerce a YAML list of ints; empty/missing uses ``default``."""
    if raw is None:
        return default
    return tuple(int(x) for x in raw)


def _parse_technique_craft(
    raw: dict[str, Any] | None,
    *,
    combat_attrs: CombatAttrsConfig,
) -> TechniqueCraftConfig:
    """Parse technique_craft; missing block uses YAML-matching placeholders."""
    from app.config_source.validate_content import assert_attr_stats, registered_attr_keys

    body = raw if isinstance(raw, dict) else {}
    weights_src = body.get("efficacy_weights") or {
        "spell_attack": 1,
        "spell_buff": 1,
        "martial_attack": 1,
        "martial_buff": 1,
        "idle_spirit": 1,
        "idle_body": 1,
    }
    efficacy_weights = {str(k): float(v) for k, v in weights_src.items()}
    ranks_src = body.get("ranks") or {
        "body_tempering": {
            "affix_slots": 1,
            "base_upgrade_cap": 3,
            "upgrade_points_required": 10,
        },
        "qi_refining": {
            "affix_slots": 2,
            "base_upgrade_cap": 6,
            "upgrade_points_required": 100,
        },
    }
    ranks: dict[str, TechniqueCraftRankConfig] = {}
    for rank_id, rank_body in ranks_src.items():
        rb = rank_body or {}
        ranks[str(rank_id)] = TechniqueCraftRankConfig(
            affix_slots=int(rb.get("affix_slots") or 1),
            base_upgrade_cap=int(rb.get("base_upgrade_cap") or 0),
            upgrade_points_required=int(rb.get("upgrade_points_required") or 0),
        )
    weapon_src = body.get("weapon_bonus") or {
        "sword": {"phys_atk": 2},
        "saber": {"phys_atk": 2},
        "spear": {"phys_atk": 2},
        "gauntlet": {"phys_atk": 2},
        "bow": {"phys_atk": 2},
        "puppet": {"phys_atk": 2},
        "avatar": {"magic_atk": 2},
    }
    weapon_bonus: dict[str, dict[str, float]] = {}
    for weapon_id, bonus in weapon_src.items():
        weapon_bonus[str(weapon_id)] = {str(k): float(v) for k, v in (bonus or {}).items()}

    from app.constants.technique_craft import AFFIX_RARITY_DEFAULT, AFFIX_RARITY_IDS

    rarities_src = body.get("affix_rarities") or {
        "gray": {
            "label_zh": "灰",
            "weight": 10,
            "base_mult": 0.7,
            "upgrade_mult": 0.7,
            "cost_mult": 0.75,
            "color": "#9e9e9e",
        },
        "white": {
            "label_zh": "白",
            "weight": 28,
            "base_mult": 1.0,
            "upgrade_mult": 1.0,
            "cost_mult": 1.0,
            "color": "#eceff1",
        },
        "green": {
            "label_zh": "绿",
            "weight": 26,
            "base_mult": 1.2,
            "upgrade_mult": 1.2,
            "cost_mult": 1.25,
            "color": "#67c23a",
        },
        "blue": {
            "label_zh": "蓝",
            "weight": 24,
            "base_mult": 1.4,
            "upgrade_mult": 1.4,
            "cost_mult": 1.5,
            "color": "#409eff",
        },
        "purple": {
            "label_zh": "紫",
            "weight": 8,
            "base_mult": 1.7,
            "upgrade_mult": 1.7,
            "cost_mult": 1.9,
            "color": "#a855f7",
        },
        "orange": {
            "label_zh": "橙",
            "weight": 3,
            "base_mult": 2.1,
            "upgrade_mult": 2.1,
            "cost_mult": 2.5,
            "color": "#e6a23c",
        },
        "red": {
            "label_zh": "红",
            "weight": 1,
            "base_mult": 2.8,
            "upgrade_mult": 2.8,
            "cost_mult": 3.4,
            "color": "#f56c6c",
        },
    }
    affix_rarities: dict[str, TechniqueCraftAffixRarityDef] = {}
    for rid, rbody in rarities_src.items():
        key = str(rid)
        rb = rbody or {}
        affix_rarities[key] = TechniqueCraftAffixRarityDef(
            rarity_id=key,
            label_zh=str(rb.get("label_zh") or key),
            weight=float(rb.get("weight") or 0),
            base_mult=float(rb.get("base_mult") or 1.0),
            upgrade_mult=float(rb.get("upgrade_mult") or 1.0),
            cost_mult=float(rb.get("cost_mult") or 1.0),
            color=str(rb.get("color") or "#ffffff"),
        )
    for required in AFFIX_RARITY_IDS:
        if required not in affix_rarities:
            affix_rarities[required] = TechniqueCraftAffixRarityDef(
                rarity_id=required,
                label_zh=required,
                weight=1.0 if required == AFFIX_RARITY_DEFAULT else 0.0,
                base_mult=1.0,
                upgrade_mult=1.0,
                cost_mult=1.0,
                color="#ffffff",
            )

    affixes_src = body.get("affixes") or {
        "sa_edge": {
            "label_zh": "法锋",
            "rarity": "white",
            "efficacy_allow": ["spell_attack"],
            "role": "attack",
            "stats": {"magic_atk": 3},
        },
        "sb_ward": {
            "label_zh": "法盾",
            "rarity": "white",
            "efficacy_allow": ["spell_buff"],
            "role": "buff",
            "stats": {"magic_def": 3},
        },
        "ma_edge": {
            "label_zh": "武锋",
            "rarity": "white",
            "efficacy_allow": ["martial_attack"],
            "role": "attack",
            "stats": {"phys_atk": 3},
        },
        "mb_ward": {
            "label_zh": "武御",
            "rarity": "white",
            "efficacy_allow": ["martial_buff"],
            "role": "buff",
            "stats": {"phys_def": 3},
        },
        "is_flow": {
            "label_zh": "周天",
            "rarity": "white",
            "efficacy_allow": ["idle_spirit"],
            "role": "idle",
            "stats": {"magic_atk": 1},
        },
        "ib_bone": {
            "label_zh": "锻骨",
            "rarity": "white",
            "efficacy_allow": ["idle_body"],
            "role": "idle",
            "stats": {"phys_atk": 1},
        },
    }
    attr_keys = registered_attr_keys(combat_attrs)
    affixes: dict[str, TechniqueCraftAffixDef] = {}
    for affix_id, affix_body in affixes_src.items():
        ab = affix_body or {}
        stats = {str(k): float(v) for k, v in (ab.get("stats") or {}).items()}
        assert_attr_stats(
            f"research.technique_craft.affixes.{affix_id}.stats",
            stats,
            attr_keys,
        )
        rarity = str(ab.get("rarity") or AFFIX_RARITY_DEFAULT).strip() or AFFIX_RARITY_DEFAULT
        if rarity not in affix_rarities:
            rarity = AFFIX_RARITY_DEFAULT
        affixes[str(affix_id)] = TechniqueCraftAffixDef(
            affix_id=str(affix_id),
            label_zh=str(ab.get("label_zh") or affix_id),
            rarity=rarity,
            efficacy_allow=tuple(str(x) for x in (ab.get("efficacy_allow") or [])),
            role=str(ab.get("role") or ""),
            stats=stats,
        )
    p_el = body.get("blank_to_type_p_element")
    embed = body.get("embed_fail_rate")
    affix_fail = body.get("affix_upgrade_fail_rate")
    bt_fail = body.get("breakthrough_fail_rate")
    return TechniqueCraftConfig(
        help_zh=str(
            body.get("help_zh")
            or "用空白卡生成属性/效能正式卡，镶入草稿后选发动条件与词条，定稿后可培养。",
        ),
        blank_to_type_p_element=0.5 if p_el is None else float(p_el),
        efficacy_weights=efficacy_weights,
        embed_fail_rate=0.2 if embed is None else float(embed),
        affix_upgrade_fail_rate=0.2 if affix_fail is None else float(affix_fail),
        breakthrough_fail_rate=0.3 if bt_fail is None else float(bt_fail),
        base_bonus_points=_parse_int_tuple(body.get("base_bonus_points"), (5, 10, 20)),
        affix_upgrade_points=_parse_int_tuple(body.get("affix_upgrade_points"), (5, 10, 20)),
        spirit_upgrade_cost=_parse_int_tuple(body.get("spirit_upgrade_cost"), (20, 40, 80, 160)),
        body_upgrade_cost=_parse_int_tuple(body.get("body_upgrade_cost"), (20, 40, 80, 160)),
        affix_upgrade_cost=_parse_int_tuple(body.get("affix_upgrade_cost"), (15, 30, 60, 120)),
        affix_reroll_cost=_parse_int_tuple(body.get("affix_reroll_cost"), (10, 20, 40, 80)),
        breakthrough_cost_cultivation=int(
            50 if body.get("breakthrough_cost_cultivation") is None
            else body.get("breakthrough_cost_cultivation")
        ),
        breakthrough_cost_body=int(
            50 if body.get("breakthrough_cost_body") is None
            else body.get("breakthrough_cost_body")
        ),
        print_manual_cost_cultivation=int(
            500 if body.get("print_manual_cost_cultivation") is None
            else body.get("print_manual_cost_cultivation")
        ),
        print_manual_cost_body=int(
            500 if body.get("print_manual_cost_body") is None
            else body.get("print_manual_cost_body")
        ),
        affix_level_mult=0.2 if body.get("affix_level_mult") is None else float(body.get("affix_level_mult")),
        breakthrough_affix_bonus=(
            0.15
            if body.get("breakthrough_affix_bonus") is None
            else float(body.get("breakthrough_affix_bonus"))
        ),
        base_stat_per_click=(
            1.0 if body.get("base_stat_per_click") is None else float(body.get("base_stat_per_click"))
        ),
        ranks=ranks,
        weapon_bonus=weapon_bonus,
        affix_rarities=affix_rarities,
        affixes=affixes,
    )




def _parse_research(raw: dict[str, Any], *, combat_attrs: CombatAttrsConfig) -> ResearchConfig:
    """Parse research.yaml; affix stats must be registered ATTR keys."""
    tech_raw = raw.get("technique") or {}
    reroll_raw = tech_raw.get("reroll") or {}
    extra_mats = []
    for mat in reroll_raw.get("extra_materials") or []:
        extra_mats.append(
            {
                "item_id": str(mat.get("item_id") or ""),
                "quantity": int(mat.get("quantity") or 0),
            },
        )
    spend_raw = tech_raw.get("spend") or {}
    technique = ResearchTechniqueConfig(
        label_zh=str(tech_raw.get("label_zh") or "自研功法"),
        help_zh=str(tech_raw.get("help_zh") or ""),
        allowed_materials=tuple(str(x) for x in (tech_raw.get("allowed_materials") or [])),
        min_materials=int(tech_raw.get("min_materials") or 1),
        spend={
            "cultivation_points": int(spend_raw.get("cultivation_points") or 0),
            "body_tempering_points": int(spend_raw.get("body_tempering_points") or 0),
        },
        max_rerolls=int(reroll_raw.get("max_rerolls") or 0),
        reroll_materials=tuple(extra_mats),
        affix_slots=int(tech_raw.get("affix_slots") or 1),
        extra_affix_roll=int(tech_raw.get("extra_affix_roll") or 12),
        session_ttl_seconds=int(tech_raw.get("session_ttl_seconds") or 86400),
        track=str(tech_raw.get("track") or "spirit"),
        max_level=int(tech_raw.get("max_level") or 5),
        cost_per_level=tuple(int(x) for x in (tech_raw.get("cost_per_level") or [])),
    )
    allowed_keys = set(combat_attrs.attrs.keys())
    affixes: dict[str, ResearchAffixDef] = {}
    for affix_id, body in (raw.get("affixes") or {}).items():
        stats_raw = body.get("stats") or {}
        stats: dict[str, float] = {}
        for key, val in stats_raw.items():
            sk = str(key)
            if sk not in allowed_keys:
                raise ValueError(f"research.affixes.{affix_id}.stats.{sk}: unknown combat attr key")
            stats[sk] = float(val)
        affixes[str(affix_id)] = ResearchAffixDef(
            affix_id=str(affix_id),
            label_zh=str(body.get("label_zh", affix_id)),
            help_zh=str(body.get("help_zh", "")),
            stats=stats,
        )
    form_raw = raw.get("formation") or {}
    form_spend = form_raw.get("spend") or {}
    formation = ResearchFormationConfig(
        label_zh=str(form_raw.get("label_zh") or "自研阵法"),
        help_zh=str(form_raw.get("help_zh") or ""),
        allowed_materials=tuple(str(x) for x in (form_raw.get("allowed_materials") or [])),
        min_materials=int(form_raw.get("min_materials") or 1),
        spend={
            "cultivation_points": int(form_spend.get("cultivation_points") or 0),
            "body_tempering_points": int(form_spend.get("body_tempering_points") or 0),
        },
        required_array_level=int(form_raw.get("required_array_level") or 0),
        session_ttl_seconds=int(form_raw.get("session_ttl_seconds") or 86400),
        default_deploy_mode=str(form_raw.get("default_deploy_mode") or "free_own"),
        terrain_layout=dict(form_raw.get("terrain_layout") or {}),
        allowed_deploy_modes=tuple(
            str(x) for x in (form_raw.get("allowed_deploy_modes") or ("free_own",))
        ),
        allowed_environment_ids=tuple(
            str(x) for x in (form_raw.get("allowed_environment_ids") or [])
        ),
        allowed_weather_ids=tuple(str(x) for x in (form_raw.get("allowed_weather_ids") or [])),
        allowed_effect_ids=tuple(str(x) for x in (form_raw.get("allowed_effect_ids") or [])),
        max_force_shifts=int(form_raw.get("max_force_shifts") or 0),
    )
    tal_raw = raw.get("talisman") or {}
    tal_spend = tal_raw.get("spend") or {}
    scribe_raw = tal_raw.get("scribe") or {}
    battle_raw = tal_raw.get("battle") or {}
    talisman = ResearchTalismanConfig(
        label_zh=str(tal_raw.get("label_zh") or "自研符箓"),
        help_zh=str(tal_raw.get("help_zh") or ""),
        allowed_materials=tuple(str(x) for x in (tal_raw.get("allowed_materials") or [])),
        min_materials=int(tal_raw.get("min_materials") or 1),
        spend={
            "cultivation_points": int(tal_spend.get("cultivation_points") or 0),
            "body_tempering_points": int(tal_spend.get("body_tempering_points") or 0),
        },
        session_ttl_seconds=int(tal_raw.get("session_ttl_seconds") or 86400),
        paper_item_id=str(scribe_raw.get("paper_item_id") or "talisman_paper"),
        paper_per_copy=int(scribe_raw.get("paper_per_copy") or 1),
        max_batch=int(scribe_raw.get("max_batch") or 20),
        preload_slots=int(tal_raw.get("preload_slots") or 1),
        battle_enabled=bool((battle_raw.get("enabled", True))),
    )
    technique_craft = _parse_technique_craft(
        raw.get("technique_craft") or {},
        combat_attrs=combat_attrs,
    )
    return ResearchConfig(
        schema_version=int(raw.get("schema_version") or 1),
        reincarnation_carry=bool(raw.get("reincarnation_carry", False)),
        technique=technique,
        formation=formation,
        talisman=talisman,
        affixes=affixes,
        technique_craft=technique_craft,
    )


def _parse_calendar(raw: dict[str, Any], settings: Any) -> CalendarConfig:
    """解析 calendar.yaml；环境变量可覆盖 slot_seconds / epoch。"""
    slot = int(raw.get("slot_seconds", 60))
    if getattr(settings, "calendar_slot_seconds", 0) and settings.calendar_slot_seconds > 0:
        slot = int(settings.calendar_slot_seconds)
    epoch = str(raw.get("epoch_utc", "2026-01-01T00:00:00Z"))
    if getattr(settings, "calendar_epoch_utc", "") and str(settings.calendar_epoch_utc).strip():
        epoch = str(settings.calendar_epoch_utc).strip()
    order = tuple(str(x) for x in (raw.get("shichen_order") or []))
    labels = {str(k): str(v) for k, v in (raw.get("labels") or {}).items()}
    modifiers_raw = raw.get("modifiers") or {}
    modifiers: dict[str, dict[str, float]] = {}
    for key, table in modifiers_raw.items():
        if isinstance(table, dict):
            modifiers[str(key)] = {str(k): float(v) for k, v in table.items()}
    clamp = raw.get("clamp") or {}
    catalog_raw = raw.get("catalog") or {}
    catalog: dict[str, dict[str, Any]] = {}
    for key, entry in catalog_raw.items():
        if isinstance(entry, dict):
            catalog[str(key)] = dict(entry)
    tag_modifiers = dict(raw.get("tag_modifiers") or {})
    return CalendarConfig(
        slot_seconds=slot,
        epoch_utc=epoch,
        shichen_order=order,
        labels=labels,
        modifiers=modifiers,
        clamp_min=float(clamp.get("min", 0.5)),
        clamp_max=float(clamp.get("max", 1.5)),
        catalog=catalog,
        tag_modifiers=tag_modifiers,
    )


def _parse_weather(raw: dict[str, Any]) -> WeatherConfig:
    """解析 weather.yaml。"""
    regions_raw = raw.get("regions") or {}
    regions: dict[str, WeatherRegionConfig] = {}
    for region_id, body in regions_raw.items():
        pool_raw = body.get("pool") or {}
        regions[str(region_id)] = WeatherRegionConfig(
            region_id=str(region_id),
            pool={str(k): int(v) for k, v in pool_raw.items()},
            roll_interval_seconds=int(body.get("roll_interval_seconds", 180)),
        )
    clamp = raw.get("clamp") or {}
    catalog_raw = raw.get("catalog") or {}
    catalog: dict[str, dict[str, Any]] = {}
    for key, entry in catalog_raw.items():
        if isinstance(entry, dict):
            catalog[str(key)] = dict(entry)
    return WeatherConfig(
        regions=regions,
        labels={str(k): str(v) for k, v in (raw.get("labels") or {}).items()},
        modifiers=dict(raw.get("modifiers") or {}),
        clamp_min=float(clamp.get("min", 0.5)),
        clamp_max=float(clamp.get("max", 1.5)),
        catalog=catalog,
        tag_modifiers=dict(raw.get("tag_modifiers") or {}),
    )


def _parse_tribulation(raw: dict[str, Any]) -> TribulationConfig:
    """解析 tribulation.yaml。"""
    require = raw.get("require_from") or {}
    power_raw = raw.get("power_tiers") or {}
    power_tiers = {
        str(k): TribulationPowerTier(
            label=str(v.get("label", k)),
            base_weight=float(v.get("base_weight", 1.0)),
            cloud_radius=int(v.get("cloud_radius", 0)),
        )
        for k, v in power_raw.items()
    }
    count_raw = raw.get("count_tiers") or {}
    count_tiers = {
        str(k): TribulationCountTier(
            label=str(v.get("label", k)),
            # 必须 ≥1：小数经 int() 会变成 0，导致每批结算 0 道雷 → 自动结算空转
            strikes=max(1, int(v.get("strikes", 9))),
            strikes_per_batch=max(1, int(v.get("strikes_per_batch", 3))),
        )
        for k, v in count_raw.items()
    }
    grade_map = {
        str(k): {str(ik): str(iv) for ik, iv in v.items()}
        for k, v in (raw.get("grade_to_tribulation") or {}).items()
    }
    layer_map = {
        str(k): {str(ik): str(iv) for ik, iv in v.items()}
        for k, v in (raw.get("layer_mapping") or {}).items()
    }
    return TribulationConfig(
        require_from_major=str(require.get("major", "yuanying")),
        require_from_stage=str(require.get("stage", "peak")),
        always_after_first=bool(raw.get("always_after_first", True)),
        power_tiers=power_tiers,
        count_tiers=count_tiers,
        grade_to_tribulation=grade_map,
        layer_mapping=layer_map,
        prep_slots_default=int(raw.get("prep_slots_default", 6)),
        guardian_proc_chance=float(raw.get("guardian_proc_chance", 0.35)),
        guardian_hp_restore_ratio=float(raw.get("guardian_hp_restore_ratio", 0.2)),
        mercy_after_guardian_damage_mult=float(
            raw.get("mercy_after_guardian_damage_mult", 0.01),
        ),
        in_existing_cloud_damage_mult=float(raw.get("in_existing_cloud_damage_mult", 2.0)),
        cloud_radius_bonus_on_myriad=int(raw.get("cloud_radius_bonus_on_myriad", 1)),
        artifact_base_shatter_chance=float(raw.get("artifact_base_shatter_chance", 0.03)),
        artifact_durability_cost_per_strike=int(
            raw.get("artifact_durability_cost_per_strike", 1),
        ),
        reroll_grade_on_win=bool(raw.get("reroll_grade_on_win", False)),
        fate_luck_power_mult={
            str(k): float(v) for k, v in (raw.get("fate_luck_power_mult") or {}).items()
        },
        demonic_nature_power_mult={
            str(k): float(v)
            for k, v in (raw.get("demonic_nature_power_mult") or {}).items()
        },
        veil=dict(raw.get("veil") or {}),
        fall_on_hp_zero=bool(raw.get("fall_on_hp_zero", True)),
        realm_scale={str(k): float(v) for k, v in (raw.get("realm_scale") or {}).items()},
    )


def _parse_reincarnation(raw: dict[str, Any], settings: Any) -> ReincarnationConfig:
    """解析 reincarnation.yaml；环境变量可覆盖倒计时与带宠闸。"""
    ferry = int(raw.get("ferry_countdown_seconds", 3600))
    if getattr(settings, "ferry_countdown_seconds", 0) and settings.ferry_countdown_seconds > 0:
        ferry = int(settings.ferry_countdown_seconds)
    carry = dict(raw.get("carry") or {})
    pet_carry = dict(carry.get("pet_carry") or {})
    # REINCARNATION_PET_CARRY 总闸覆盖 YAML
    if hasattr(settings, "reincarnation_pet_carry"):
        pet_carry["enabled"] = bool(settings.reincarnation_pet_carry)
    carry["pet_carry"] = pet_carry
    return ReincarnationConfig(
        ferry_countdown_seconds=ferry,
        self_rescue=dict(raw.get("self_rescue") or {}),
        social_rescue=dict(raw.get("social_rescue") or {}),
        carry=carry,
        points=dict(raw.get("points") or {}),
        growth_attr_gain_placeholder=int(raw.get("growth_attr_gain_placeholder", 1)),
        altar=dict(raw.get("altar") or {}),
        story=dict(raw.get("story") or {}),
        newborn=dict(raw.get("newborn") or {}),
        spirit_roots=dict(raw.get("spirit_roots") or {}),
        legacy_catalog=dict(raw.get("legacy_catalog") or {}),
        shop=dict(raw.get("shop") or {}),
        permanent_bonus_on_settle=dict(raw.get("permanent_bonus_on_settle") or {}),
        slots=dict(raw.get("slots") or {}),
        bags=dict(raw.get("bags") or {}),
    )


def _parse_mapping_of_dicts(raw: Any, *, path: str) -> dict[str, dict[str, Any]]:
    """将 YAML mapping 解析为 dict[str, dict]。"""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"sects.yaml {path} 须为 mapping")
    out: dict[str, dict[str, Any]] = {}
    for key, body in raw.items():
        if not isinstance(body, dict):
            raise ValueError(f"sects.yaml {path}.{key} 须为 mapping")
        out[str(key)] = dict(body)
    return out


def _parse_sects(raw: dict[str, Any]) -> SectsConfig:
    """解析 sects.yaml：设施开关 + M7 L1 / M7-V+ 宗门玩法表。"""
    facilities_raw = raw.get("facilities") or {}
    if not isinstance(facilities_raw, dict):
        raise ValueError("sects.yaml facilities 须为 mapping")
    facilities: dict[str, dict[str, Any]] = {}
    for facility_id, body in facilities_raw.items():
        if not isinstance(body, dict):
            raise ValueError(f"facility {facility_id} 须为 mapping")
        facilities[str(facility_id)] = {
            "enabled": bool(body.get("enabled", False)),
            "note": str(body.get("note", "")),
            **{k: v for k, v in body.items() if k not in {"enabled", "note"}},
        }
    sects_raw = raw.get("sects") or {}
    if not isinstance(sects_raw, dict):
        raise ValueError("sects.yaml sects 须为 mapping")
    sects = {
        str(k): dict(v) if isinstance(v, dict) else {"value": v}
        for k, v in sects_raw.items()
    }
    # NPC 宗门：禁止空表导致玩法不可测
    npc_raw = raw.get("npc_sects") or {}
    if not isinstance(npc_raw, dict):
        raise ValueError("sects.yaml npc_sects 须为 mapping")
    npc_sects: dict[str, dict[str, Any]] = {}
    for tid, body in npc_raw.items():
        if not isinstance(body, dict):
            raise ValueError(f"npc_sect {tid} 须为 mapping")
        if not body.get("label_zh"):
            raise ValueError(f"npc_sect {tid} 须含 label_zh")
        npc_sects[str(tid)] = dict(body)
    features_raw = raw.get("features_by_founder_realm") or {}
    if not isinstance(features_raw, dict):
        raise ValueError("sects.yaml features_by_founder_realm 须为 mapping")
    features_by_founder_realm: dict[str, list[str]] = {}
    for major, feats in features_raw.items():
        if not isinstance(feats, list):
            raise ValueError(f"features_by_founder_realm.{major} 须为 list")
        features_by_founder_realm[str(major)] = [str(x) for x in feats]
    exchange_raw = raw.get("sect_exchange") or {}
    if not isinstance(exchange_raw, dict):
        raise ValueError("sects.yaml sect_exchange 须为 mapping")
    shop_raw = raw.get("shop_items") or {}
    if not isinstance(shop_raw, dict):
        raise ValueError("sects.yaml shop_items 须为 mapping")
    shop_items = {
        str(k): dict(v) if isinstance(v, dict) else {"value": v}
        for k, v in shop_raw.items()
    }
    quests_raw = raw.get("quests") or {}
    if not isinstance(quests_raw, dict):
        raise ValueError("sects.yaml quests 须为 mapping")
    quests = {
        str(k): dict(v) if isinstance(v, dict) else {"value": v}
        for k, v in quests_raw.items()
    }
    sect_grades = _parse_mapping_of_dicts(raw.get("sect_grades"), path="sect_grades")
    for gid, gbody in sect_grades.items():
        if not gbody.get("label_zh"):
            raise ValueError(f"sect_grades.{gid} 须含 label_zh")
    disciple_ranks = _parse_mapping_of_dicts(
        raw.get("disciple_ranks"),
        path="disciple_ranks",
    )
    for rid, rbody in disciple_ranks.items():
        if not rbody.get("label_zh"):
            raise ValueError(f"disciple_ranks.{rid} 须含 label_zh")
    specialties = _parse_mapping_of_dicts(raw.get("specialties"), path="specialties")
    facility_defs = _parse_mapping_of_dicts(
        raw.get("facility_defs"),
        path="facility_defs",
    )
    sect_buffs = _parse_mapping_of_dicts(raw.get("sect_buffs"), path="sect_buffs")
    treasury_raw = raw.get("treasury") or {}
    if not isinstance(treasury_raw, dict):
        raise ValueError("sects.yaml treasury 须为 mapping")
    scripture_raw = raw.get("scripture") or {}
    if not isinstance(scripture_raw, dict):
        raise ValueError("sects.yaml scripture 须为 mapping")
    craftsmen = _parse_mapping_of_dicts(raw.get("craftsmen"), path="craftsmen")
    bp_raw = raw.get("workshop_blueprints") or {}
    if not isinstance(bp_raw, dict):
        raise ValueError("sects.yaml workshop_blueprints 须为 mapping")
    workshop_blueprints: dict[str, list[dict[str, Any]]] = {}
    for branch, rows in bp_raw.items():
        if not isinstance(rows, list):
            raise ValueError(f"workshop_blueprints.{branch} 须为 list")
        workshop_blueprints[str(branch)] = [
            dict(x) if isinstance(x, dict) else {"value": x} for x in rows
        ]
    formations = _parse_mapping_of_dicts(raw.get("formations"), path="formations")
    formation_attr_keys = _parse_mapping_of_dicts(
        raw.get("formation_attr_keys") or {},
        path="formation_attr_keys",
    )
    mine_yield = dict(raw.get("mine_yield") or {}) if isinstance(
        raw.get("mine_yield") or {},
        dict,
    ) else {}
    herb_garden = dict(raw.get("herb_garden") or {}) if isinstance(
        raw.get("herb_garden") or {},
        dict,
    ) else {}
    return SectsConfig(
        facilities=facilities,
        sects=sects,
        create_cost_spirit_stones=int(raw.get("create_cost_spirit_stones") or 100000),
        idle_bonus_vs_wanderer=float(raw.get("idle_bonus_vs_wanderer") or 1.05),
        contribution_zero_on_reincarnation=bool(
            raw.get("contribution_zero_on_reincarnation", True),
        ),
        max_name_len=int(raw.get("max_name_len") or 12),
        max_motto_len=int(raw.get("max_motto_len") or 48),
        max_announcement_len=int(raw.get("max_announcement_len") or 200),
        promotion_auto_approve_after_game_days=int(
            raw.get("promotion_auto_approve_after_game_days") or 1,
        ),
        facility_upgrade_cost_base=int(raw.get("facility_upgrade_cost_base") or 80),
        facility_upgrade_cost_per_level=int(
            raw.get("facility_upgrade_cost_per_level") or 40,
        ),
        grade_upgrade_spirit_stones_base=int(
            raw.get("grade_upgrade_spirit_stones_base") or 5000,
        ),
        features_by_founder_realm=features_by_founder_realm,
        npc_sects=npc_sects,
        sect_exchange=dict(exchange_raw),
        shop_items=shop_items,
        quests=quests,
        sect_grades=sect_grades,
        disciple_ranks=disciple_ranks,
        specialties=specialties,
        facility_defs=facility_defs,
        sect_buffs=sect_buffs,
        treasury=dict(treasury_raw),
        scripture=dict(scripture_raw),
        craftsmen=craftsmen,
        workshop_blueprints=workshop_blueprints,
        formations=formations,
        formation_attr_keys=formation_attr_keys,
        mine_yield=mine_yield,
        herb_garden=herb_garden,
    )


def _parse_friends(raw: dict[str, Any]) -> FriendsConfig:
    """解析 friends.yaml。"""
    stub = bool(raw.get("include_online_stub", False))
    include_online = bool(raw.get("include_online", stub))
    assist_dev: bool | None = None
    if "assist_dev_assume_online" in raw:
        assist_dev = bool(raw.get("assist_dev_assume_online"))
    return FriendsConfig(
        max_friends=int(raw.get("max_friends") or 50),
        max_companions=int(raw.get("max_companions") or 20),
        max_vessels=int(raw.get("max_vessels") or 10),
        vessel_min_hours=max(1, int(raw.get("vessel_min_hours") or 1)),
        vessel_max_hours=max(1, int(raw.get("vessel_max_hours") or 720)),
        request_expire_sec=int(raw.get("request_expire_sec") or 0),
        keep_on_reincarnation=bool(raw.get("keep_on_reincarnation", True)),
        include_online_stub=stub,
        include_online=include_online,
        dev_assume_online=bool(raw.get("dev_assume_online", False)),
        assist_dev_assume_online=assist_dev,
    )


def _parse_trade(raw: dict[str, Any]) -> TradeConfig:
    """解析 trade.yaml。"""
    fee_raw = raw.get("barter_fee_by_realm") or {}
    if not isinstance(fee_raw, dict):
        raise ValueError("trade.yaml barter_fee_by_realm 须为 mapping")
    refund = str(raw.get("auction_unsold_refund") or "mail").strip().lower()
    if refund not in {"inventory", "mail"}:
        raise ValueError("trade.yaml auction_unsold_refund 须为 inventory|mail")
    bazaar_raw = raw.get("bazaar") or {}
    if bazaar_raw is None:
        bazaar_raw = {}
    if not isinstance(bazaar_raw, dict):
        raise ValueError("trade.yaml bazaar 须为 mapping")
    return TradeConfig(
        listing_fee_pct=float(raw.get("listing_fee_pct") or 0.05),
        barter_fee_by_realm={str(k): int(v) for k, v in fee_raw.items()},
        barter_fee_default=int(raw.get("barter_fee_default") or 100),
        auction_duration_sec=int(raw.get("auction_duration_sec") or 3600),
        auction_min_increment_pct=float(raw.get("auction_min_increment_pct") or 0.05),
        auction_fee_pct=float(raw.get("auction_fee_pct") or 0.05),
        auction_unsold_refund=refund,
        face_timeout_sec=int(raw.get("face_timeout_sec") or 120),
        face_max_item_lines=int(raw.get("face_max_item_lines") or 8),
        face_require_friend=bool(raw.get("face_require_friend", True)),
        face_require_online=bool(raw.get("face_require_online", True)),
        face_dev_assume_online=bool(raw.get("face_dev_assume_online", False)),
        recycle_label_zh=str(raw.get("recycle_label_zh") or "天道回收池"),
        bazaar=dict(bazaar_raw),
    )


def _parse_mail(raw: dict[str, Any]) -> MailConfig:
    """解析 mail.yaml。"""
    expire = str(raw.get("expire_unclaimed") or "return_sender").strip().lower()
    if expire not in {"return_sender", "destroy"}:
        raise ValueError("mail.yaml expire_unclaimed 须为 return_sender|destroy")
    gift_raw = raw.get("gift") or {}
    if not isinstance(gift_raw, dict):
        raise ValueError("mail.yaml gift 须为 mapping")
    return MailConfig(
        retain_days=int(raw.get("retain_days") or 30),
        expire_unclaimed=expire,
        max_attachment_lines=int(raw.get("max_attachment_lines") or 6),
        max_attachment_spirit_stones=int(raw.get("max_attachment_spirit_stones") or 0),
        max_body_len=int(raw.get("max_body_len") or 500),
        list_limit=int(raw.get("list_limit") or 50),
        sect_broadcast_min_rank_order=int(raw.get("sect_broadcast_min_rank_order") or 9),
        broadcast_max_recipients=int(raw.get("broadcast_max_recipients") or 100),
        gift=dict(gift_raw),
    )


def _parse_chat(raw: dict[str, Any]) -> ChatConfig:
    """解析 chat.yaml。"""
    words_raw = raw.get("sensitive_words") or []
    if not isinstance(words_raw, list):
        raise ValueError("chat.yaml sensitive_words 须为 list")
    labels_raw = raw.get("labels_zh") or {}
    if not isinstance(labels_raw, dict):
        raise ValueError("chat.yaml labels_zh 须为 mapping")
    return ChatConfig(
        history_limit=int(raw.get("history_limit") or 100),
        dm_history_limit=max(1, int(raw.get("dm_history_limit") or 100)),
        session_ephemeral=bool(raw.get("session_ephemeral", True)),
        max_body_len=int(raw.get("max_body_len") or 200),
        rate_window_sec=int(raw.get("rate_window_sec") or 10),
        rate_max_messages=int(raw.get("rate_max_messages") or 5),
        sensitive_words=tuple(str(w) for w in words_raw if str(w).strip()),
        sensitive_filter_enabled=bool(raw.get("sensitive_filter_enabled", True)),
        world_line_id=str(raw.get("world_line_id") or "default"),
        dm_require_friend=bool(raw.get("dm_require_friend", False)),
        party_require_friend=bool(raw.get("party_require_friend", True)),
        party_invite_expire_sec=int(raw.get("party_invite_expire_sec") or 60),
        party_max_members=int(raw.get("party_max_members") or 5),
        team_max_members=int(raw.get("team_max_members") or 40),
        party_dev_assume_online=bool(raw.get("party_dev_assume_online", False)),
        labels_zh={str(k): str(v) for k, v in labels_raw.items()},
    )


def _parse_chat_heritage(raw: dict[str, Any]) -> ChatHeritageConfig:
    """解析 chat_heritage.yaml。"""
    allowed = raw.get("allowed_channel_types") or ["world", "sect", "dm", "party"]
    if not isinstance(allowed, list) or not allowed:
        raise ValueError("chat_heritage.yaml allowed_channel_types 须为非空 list")
    rem = str(raw.get("fixed_remainder") or "last_share").strip().lower()
    if rem not in {"last_share", "recycle"}:
        raise ValueError("chat_heritage.yaml fixed_remainder 须为 last_share|recycle")
    refund = str(raw.get("expire_refund") or "mail").strip().lower()
    if refund not in {"mail", "inventory"}:
        raise ValueError("chat_heritage.yaml expire_refund 须为 mail|inventory")
    return ChatHeritageConfig(
        expire_sec=int(raw.get("expire_sec") or 86400),
        min_shares=int(raw.get("min_shares") or 1),
        max_shares=int(raw.get("max_shares") or 50),
        max_spirit_stones=int(raw.get("max_spirit_stones") or 0),
        max_item_lines=int(raw.get("max_item_lines") or 8),
        claims_per_character=int(raw.get("claims_per_character") or 1),
        daily_send_cap=int(raw.get("daily_send_cap") or 20),
        daily_spirit_cap=int(raw.get("daily_spirit_cap") or 200000),
        fixed_remainder=rem,
        expire_refund=refund,
        claim_broadcast_hide_amount=bool(raw.get("claim_broadcast_hide_amount", False)),
        active_list_limit=int(raw.get("active_list_limit") or 30),
        purge_closed_packets=bool(raw.get("purge_closed_packets", True)),
        session_finished_keep=int(raw.get("session_finished_keep") or 20),
        allowed_channel_types=tuple(str(x) for x in allowed),
    )


def _parse_mentor(raw: dict[str, Any]) -> MentorConfig:
    """解析 mentor.yaml。"""
    quests = raw.get("quests") or {}
    if not isinstance(quests, dict):
        raise ValueError("mentor.yaml quests 须为 mapping")
    return MentorConfig(
        max_apprentices=int(raw.get("max_apprentices") or 3),
        max_masters_per_apprentice=int(raw.get("max_masters_per_apprentice") or 1),
        min_realm_gap=int(raw.get("min_realm_gap") or 0),
        auto_graduate_max_gap=int(raw.get("auto_graduate_max_gap") or 0),
        request_expire_sec=int(raw.get("request_expire_sec") or 0),
        dissolve_cooldown_sec=int(raw.get("dissolve_cooldown_sec") or 0),
        keep_on_reincarnation=bool(raw.get("keep_on_reincarnation", True)),
        history_after_dissolve=str(raw.get("history_after_dissolve") or "readonly"),
        pass_cultivation=dict(raw.get("pass_cultivation") or {}),
        daily_lesson=dict(raw.get("daily_lesson") or {}),
        teach=dict(raw.get("teach") or {}),
        study=dict(raw.get("study") or {}),
        direct_disciple=dict(raw.get("direct_disciple") or {}),
        quests=dict(quests),
        graduate=dict(raw.get("graduate") or {}),
    )


def _parse_dual_cultivation(raw: dict[str, Any]) -> DualCultivationConfig:
    """解析 dual_cultivation.yaml。"""
    techniques_raw = raw.get("techniques") or {}
    if not isinstance(techniques_raw, dict) or not techniques_raw:
        raise ValueError("dual_cultivation.yaml 须含非空 techniques")
    techniques: dict[str, dict[str, Any]] = {}
    for tid, body in techniques_raw.items():
        if not isinstance(body, dict):
            raise ValueError(f"technique {tid} 须为 mapping")
        mode = str(body.get("mode") or "")
        if mode not in ("mutual_gain", "transfer", "extract"):
            raise ValueError(f"technique {tid} mode 非法: {mode}")
        techniques[str(tid)] = dict(body)
    tiers_raw = raw.get("dice_tiers") or []
    if not isinstance(tiers_raw, list) or not tiers_raw:
        raise ValueError("dual_cultivation.yaml 须含 dice_tiers 列表")
    tiers = [dict(t) for t in tiers_raw if isinstance(t, dict)]
    labels_raw = raw.get("rank_labels") or {}
    labels = {str(k): str(v) for k, v in dict(labels_raw).items()}
    stamina_costs_raw = raw.get("stamina_costs") or {}
    if not isinstance(stamina_costs_raw, dict):
        raise ValueError("dual_cultivation.stamina_costs 须为 mapping")
    return DualCultivationConfig(
        invite_expire_sec=int(raw.get("invite_expire_sec") or 60),
        undress_expire_sec=int(raw.get("undress_expire_sec") or 60),
        max_rerolls=int(raw.get("max_rerolls") or 0),
        spirit_stone_cost=int(raw.get("spirit_stone_cost") or 0),
        cultivation_gap_scale=int(raw.get("cultivation_gap_scale") or 500),
        climax=dict(raw.get("climax") or {}),
        stamina_costs=dict(stamina_costs_raw),
        rank_min_scores=dict(raw.get("rank_min_scores") or {}),
        rank_labels=labels,
        dice_tiers=tuple(tiers),
        techniques=techniques,
    )


def _parse_currencies(raw: dict[str, Any]) -> CurrenciesConfig:
    """解析 currencies.yaml。"""
    body = raw.get("currencies") or {}
    if not isinstance(body, dict) or not body:
        raise ValueError("currencies.yaml 须含非空 currencies")
    currencies = {
        str(k): dict(v) if isinstance(v, dict) else {"label_zh": str(v)}
        for k, v in body.items()
    }
    return CurrenciesConfig(currencies=currencies)


def _parse_commerce(raw: dict[str, Any]) -> CommerceConfig:
    """解析 commerce.yaml。"""
    tiers = raw.get("membership_tiers") or {}
    if not isinstance(tiers, dict) or "free" not in tiers:
        raise ValueError("commerce.yaml 须含 membership_tiers.free")
    shop = raw.get("shop") or {}
    if not isinstance(shop, dict):
        raise ValueError("commerce.yaml shop 须为 mapping")
    return CommerceConfig(
        keep_membership_on_reincarnation=bool(
            raw.get("keep_membership_on_reincarnation", False),
        ),
        membership_tiers={str(k): dict(v) for k, v in tiers.items() if isinstance(v, dict)},
        shop=dict(shop),
        sandbox=dict(raw.get("sandbox") or {}),
    )


def _parse_map(raw: dict[str, Any]) -> MapConfig:
    """解析 map.yaml：区域与势力占位。"""
    regions_raw = raw.get("regions") or {}
    if not isinstance(regions_raw, dict) or not regions_raw:
        raise ValueError("map.yaml 须含非空 regions")
    regions: dict[str, dict[str, Any]] = {}
    for region_id, body in regions_raw.items():
        if not isinstance(body, dict):
            raise ValueError(f"region {region_id} 须为 mapping")
        regions[str(region_id)] = dict(body)
    factions_raw = raw.get("factions") or {}
    if not isinstance(factions_raw, dict):
        raise ValueError("map.yaml factions 须为 mapping")
    factions = {
        str(k): dict(v) if isinstance(v, dict) else {"value": v}
        for k, v in factions_raw.items()
    }
    return MapConfig(regions=regions, factions=factions)


def _parse_activity(raw: dict[str, Any]) -> ActivityConfig:
    """解析 activity.yaml。"""
    activities_raw = raw.get("activities") or {}
    if not isinstance(activities_raw, dict):
        raise ValueError("activity.yaml activities 须为 mapping")
    activities: dict[str, dict[str, Any]] = {}
    for activity_id, body in activities_raw.items():
        if not isinstance(body, dict):
            raise ValueError(f"activity {activity_id} 须为 mapping")
        activities[str(activity_id)] = {
            "enabled": bool(body.get("enabled", False)),
            "title": str(body.get("title", activity_id)),
            "note": str(body.get("note", "")),
            "overrides": dict(body.get("overrides") or {}),
        }
    return ActivityConfig(activities=activities)


def _parse_dao(raw: dict[str, Any]) -> DaoConfig:
    """解析 dao.yaml。"""
    entries_raw = dict(raw.get("entries") or {})
    categories = {str(k): str(v) for k, v in dict(raw.get("categories") or {}).items()}
    rarities = {str(k): str(v) for k, v in dict(raw.get("rarities") or {}).items()}
    labels = {str(k): str(v) for k, v in dict(raw.get("labels") or {}).items()}
    entries: dict[str, Any] = {}
    for dao_id, body in entries_raw.items():
        if not isinstance(body, dict):
            continue
        cat = str(body.get("category") or "elemental")
        rar = str(body.get("rarity") or "common")
        label = str(body.get("label_zh") or labels.get(dao_id) or dao_id)
        entries[str(dao_id)] = {
            "dao_id": str(dao_id),
            "label_zh": label,
            "category": cat,
            "category_label": categories.get(cat, cat),
            "rarity": rar,
            "rarity_label": rarities.get(rar, rar),
            "weight": float(body.get("weight") or 0),
            "description": str(body.get("description") or ""),
        }
        labels.setdefault(str(dao_id), label)
    return DaoConfig(
        open=dict(raw.get("open") or {}),
        pool=dict(raw.get("pool") or {}),
        resources=dict(raw.get("resources") or {}),
        usage=dict(raw.get("usage") or {}),
        restraint_enabled=bool(raw.get("restraint_enabled", True)),
        categories=categories,
        rarities=rarities,
        entries=entries,
        labels=labels,
    )


def _parse_dao_restraint(raw: dict[str, Any]) -> DaoRestraintConfig:
    """解析 dao_restraint.yaml。"""
    edges: list[dict[str, Any]] = []
    for item in list(raw.get("edges") or []):
        if not isinstance(item, dict):
            continue
        edges.append(
            {
                "attacker": str(item.get("attacker") or ""),
                "defender": str(item.get("defender") or ""),
                "damage_mul": float(item.get("damage_mul") or 1.0),
                "label_zh": str(item.get("label_zh") or item.get("label") or "上位克制"),
            },
        )
    return DaoRestraintConfig(edges=tuple(edges))


def _parse_dao_lord(raw: dict[str, Any]) -> DaoLordConfig:
    """解析 dao_lord.yaml。"""
    windows: list[dict[str, Any]] = []
    for item in list(raw.get("windows") or []):
        if not isinstance(item, dict):
            continue
        windows.append(
            {
                "start_hour": int(item.get("start_hour") or 0),
                "end_hour": int(item.get("end_hour") or 24),
                "tz": str(item.get("tz") or "UTC"),
                "label_zh": str(item.get("label_zh") or "挑战时段"),
                "weekday": item.get("weekday"),
            },
        )
    contest_raw = dict(raw.get("contest") or {})
    kinds = contest_raw.get("live_round_kinds") or ["semi", "final", "lord"]
    if not isinstance(kinds, list):
        kinds = ["semi", "final", "lord"]
    contest = DaoLordContestConfig(
        tz=str(contest_raw.get("tz") or "Asia/Shanghai"),
        registration_start=str(contest_raw.get("registration_start") or "18:00"),
        registration_end=str(contest_raw.get("registration_end") or "19:55"),
        fight_at=str(contest_raw.get("fight_at") or "20:00"),
        live_round_kinds=tuple(str(k) for k in kinds),
        live_prep_seconds=int(contest_raw.get("live_prep_seconds") or 15),
        live_playback_seconds=int(contest_raw.get("live_playback_seconds") or 90),
        live_tick_base_ms=int(contest_raw.get("live_tick_base_ms") or 400),
        live_dramatic_pause_ms=int(contest_raw.get("live_dramatic_pause_ms") or 900),
        log_retain_until_next_contest=bool(
            contest_raw.get("log_retain_until_next_contest", True),
        ),
        both_offline_policy=str(
            contest_raw.get("both_offline_policy") or "earlier_entrant_advances",
        ),
        dev_assume_online=bool(contest_raw.get("dev_assume_online", False)),
        staging_enabled=bool(contest_raw.get("staging_enabled", True)),
        rsvp_seconds=max(0, int(contest_raw.get("rsvp_seconds") or 60)),
        arena_first_round_countdown_seconds=max(
            0,
            int(contest_raw.get("arena_first_round_countdown_seconds") or 30),
        ),
        round_gap_seconds=max(0, int(contest_raw.get("round_gap_seconds") or 30)),
        live_adjust_seconds=max(0, int(contest_raw.get("live_adjust_seconds") or 60)),
        leave_during_playback_forfeit=bool(
            contest_raw.get("leave_during_playback_forfeit", True),
        ),
    )
    return DaoLordConfig(
        claim_min_level=int(raw.get("claim_min_level") or 2),
        challenge_min_level=int(raw.get("challenge_min_level") or 1),
        cooldown=dict(raw.get("cooldown") or {}),
        reconnect_grace_seconds=int(raw.get("reconnect_grace_seconds") or 45),
        missing_snapshot_policy=str(raw.get("missing_snapshot_policy") or "reject"),
        privileges_default=dict(raw.get("privileges_default") or {}),
        windows=tuple(windows),
        single_challenge_per_dao=bool(raw.get("single_challenge_per_dao", True)),
        contest=contest,
    )


def _parse_presence(raw: dict[str, Any]) -> PresenceConfig:
    """解析 presence.yaml。"""
    purpose_raw = raw.get("dev_assume_by_purpose") or {}
    if not isinstance(purpose_raw, dict):
        raise ValueError("presence.yaml dev_assume_by_purpose 须为 mapping")
    purpose: dict[str, bool] = {
        str(k): bool(v) for k, v in purpose_raw.items() if str(k).strip()
    }
    return PresenceConfig(
        grace_sec=max(0, int(raw.get("grace_sec") or 0)),
        dev_assume_online=bool(raw.get("dev_assume_online", False)),
        dev_assume_by_purpose=purpose,
    )


def _parse_world_events(raw: dict[str, Any]) -> WorldEventsConfig:
    """解析 world_events.yaml。"""
    events: dict[str, dict[str, Any]] = {}
    for event_id, body in dict(raw.get("events") or {}).items():
        if not isinstance(body, dict):
            continue
        events[str(event_id)] = dict(body)
    return WorldEventsConfig(
        enabled=bool(raw.get("enabled", False)),
        events=events,
    )


def load_game_config() -> GameConfigBundle:
    """
    从磁盘加载全部玩法配置。

    Returns:
        GameConfigBundle: 只读配置快照。
    """
    settings = get_settings()
    realms_raw = _load_yaml("realms.yaml")
    realms = _parse_realms(realms_raw)
    body_temper = _parse_body_temper(realms_raw)
    idle = _parse_idle(_load_yaml("idle.yaml"), settings.idle_tick_seconds)
    breakthrough = _parse_breakthrough(_load_yaml("breakthrough.yaml"))
    monsters = _parse_monsters(_load_yaml("pve_monsters.yaml"))
    taunt_auras = _parse_taunt_auras(_load_yaml("taunt_auras.yaml"))
    # 怪物单位嘲讽光环外键校验
    for mon in monsters.values():
        for u in mon.units:
            if u.taunt_aura_id and u.taunt_aura_id not in taunt_auras.auras:
                raise ValueError(
                    f"monsters.{mon.monster_id}.units.{u.unit_uid}: "
                    f"unknown taunt_aura_id '{u.taunt_aura_id}'",
                )
    offline = _parse_offline(_load_yaml("offline.yaml"), settings)
    tech_raw = _load_yaml("techniques.yaml")
    techniques = _parse_techniques(tech_raw)
    technique_loadout = _parse_technique_loadout(tech_raw)
    divine_raw = _load_yaml("divine_abilities.yaml")
    divine_abilities = _parse_divine_abilities(divine_raw)
    divine_ability_loadout = _parse_divine_ability_loadout(divine_raw)
    constitution = _parse_constitution(_load_yaml("constitution.yaml"))
    grades = _parse_grades(_load_yaml("grades.yaml"))
    board = _parse_board(_load_yaml("board.yaml"), settings)
    formations = _parse_formations(_load_yaml("formations.yaml"))
    # 阵法蓝图相对棋盘的硬校验（部署格 / 地形 / 移位）
    from app.domain.formation_blueprint import validate_formation_def

    for _fdef in formations.formations.values():
        validate_formation_def(board, _fdef)
    snapshots = _parse_snapshots(_load_yaml("snapshots.yaml"), settings)
    stamina = _parse_stamina(_load_yaml("stamina.yaml"))
    avatar = _parse_avatar(_load_yaml("avatar.yaml"))
    # feature_unlocks.min_major 必须落在境界链内；并预计算能力索引（热路径复用）
    from app.domain.avatar_capability import AvatarCapabilityIndex
    from dataclasses import replace as dc_replace

    for fid, funlock in avatar.feature_unlocks.items():
        if funlock.min_major not in realms:
            raise ValueError(
                f"avatar.feature_unlocks.{fid}.min_major={funlock.min_major!r} 不在 realms",
            )
    if avatar.max_major_realm in AVATAR_FORBIDDEN_IDENTITY_REALMS:
        raise ValueError("avatar.max_major_realm 不可配置为道主境/轮回境")
    if avatar.max_major_realm not in realms:
        raise ValueError(
            f"avatar.max_major_realm={avatar.max_major_realm!r} 不在 realms",
        )
    avatar = dc_replace(
        avatar,
        capability=AvatarCapabilityIndex.from_config(avatar, realms),
    )
    divine_sense = _parse_divine_sense(_load_yaml("divine_sense.yaml"))
    craft_recipes = _parse_craft_recipes(_load_yaml("craft_recipes.yaml"))
    pets_raw = dict(_load_yaml("pets.yaml"))
    try:
        sect_reroll_file = _load_yaml("pet_sect_reroll.yaml")
        if isinstance(sect_reroll_file, dict) and "sect_reroll" not in pets_raw:
            pets_raw["sect_reroll"] = dict(sect_reroll_file)
    except FileNotFoundError:
        pass
    pets = _parse_pets(pets_raw)
    pet_affixes = _parse_pet_affixes(_load_yaml("pet_affixes.yaml"))
    pet_skills = _parse_pet_skills(_load_yaml("pet_skills.yaml"))
    # 物种 skill_pool_id 外键校验（热插拔）
    for sp in pets.species.values():
        if sp.skill_pool_id and sp.skill_pool_id not in pet_skills.pools:
            raise ValueError(
                f"pets.species.{sp.species_id}: unknown skill_pool_id '{sp.skill_pool_id}'",
            )
    pet_skill_books = _parse_pet_skill_books(
        _load_yaml("pet_skill_books.yaml"),
        skills=pet_skills.skills,
        races=pets.races,
    )
    pet_duel = _parse_pet_duel(_load_yaml("pet_duel.yaml"))
    # NPC 物种外键
    for npc in pet_duel.npc_templates.values():
        if npc.species_id not in pets.species:
            raise ValueError(f"pet_duel.npc {npc.npc_id}: unknown species '{npc.species_id}'")
        for sid in npc.skill_ids:
            if sid not in pet_skills.skills:
                raise ValueError(f"pet_duel.npc {npc.npc_id}: unknown skill '{sid}'")
    pet_passives = _parse_pet_passives(_load_yaml("pet_passives.yaml"))
    # 种族天赋 / 物种被动池 / 词条 passive_ref 外键
    for race in pets.races.values():
        tid = race.racial_talent_id
        if tid and tid not in pet_passives.passives:
            raise ValueError(f"pets.races.{race.race_id}: unknown racial_talent_id '{tid}'")
    for sp in pets.species.values():
        if sp.passive_pool_id and sp.passive_pool_id not in pet_passives.pools:
            raise ValueError(
                f"pets.species.{sp.species_id}: unknown passive_pool_id '{sp.passive_pool_id}'",
            )
    for type_id, tcfg in pet_affixes.types.items():
        if tcfg.kind == "passive_ref" and tcfg.passive_id:
            if tcfg.passive_id not in pet_passives.passives:
                raise ValueError(
                    f"pet_affixes.types.{type_id}: unknown passive_id '{tcfg.passive_id}'",
                )
    pet_feed = _parse_pet_feed(_load_yaml("pet_feed.yaml"))
    inventory = _parse_inventory(_load_yaml("inventory.yaml"))
    combat_attrs = _parse_combat_attrs(_load_yaml("combat_attrs.yaml"))
    equipment = _parse_equipment(_load_yaml("equipment.yaml"), combat_attrs=combat_attrs)
    for eq_id, eq_def in equipment.items.items():
        if eq_id not in inventory.items:
            raise ValueError(f"equipment.{eq_id}: missing inventory item")
        if inventory.items[eq_id].item_type != "equipment":
            raise ValueError(f"inventory.{eq_id}: item_type must be equipment")
    research = _parse_research(_load_yaml("research.yaml"), combat_attrs=combat_attrs)
    for mat_id in research.technique.allowed_materials:
        if mat_id not in inventory.items:
            raise ValueError(f"research.technique.allowed_materials missing inventory: {mat_id}")
    for mat_id in research.formation.allowed_materials:
        if mat_id not in inventory.items:
            raise ValueError(f"research.formation.allowed_materials missing inventory: {mat_id}")
    for mat_id in research.talisman.allowed_materials:
        if mat_id not in inventory.items:
            raise ValueError(f"research.talisman.allowed_materials missing inventory: {mat_id}")
    if research.talisman.paper_item_id not in inventory.items:
        raise ValueError("research.talisman.scribe.paper_item_id missing inventory")
    talisman_effects = _parse_talisman_effects(_load_yaml("talisman_effects.yaml"))
    for feed_id in pet_feed.items:
        if feed_id not in inventory.items:
            raise ValueError(f"pet_feed.items.{feed_id}: missing inventory item")
    pet_eggs = _parse_pet_eggs(_load_yaml("pet_eggs.yaml"))
    for egg in pet_eggs.eggs.values():
        if egg.species_id not in pets.species:
            raise ValueError(f"pet_eggs.{egg.egg_id}: unknown species '{egg.species_id}'")
    # 蛋道具须存在于背包目录
    for egg_id in pet_eggs.eggs:
        if egg_id not in inventory.items:
            raise ValueError(f"pet_eggs.{egg_id}: missing inventory item")
        if inventory.items[egg_id].item_type != "pet_egg":
            raise ValueError(f"inventory.{egg_id}: item_type must be pet_egg")
    pet_encounter = _parse_pet_encounter(_load_yaml("pet_encounter.yaml"))
    for table in pet_encounter.tables:
        for ent in table.get("entries") or []:
            sid = str(ent.get("species_id") or "").strip()
            if sid and sid not in pets.species:
                raise ValueError(f"pet_encounter: unknown species '{sid}'")
            if sid and str(ent.get("type")) in pet_encounter.capturable_types:
                if "wild_capture" not in pets.species[sid].acquire_tags:
                    raise ValueError(
                        f"pet_encounter species '{sid}' missing acquire_tag wild_capture",
                    )
    pet_capture = _parse_pet_capture(_load_yaml("pet_capture.yaml"))
    if pet_capture.lure_item_id not in inventory.items:
        raise ValueError(f"pet_capture.lure_item_id missing inventory: {pet_capture.lure_item_id}")
    if pet_capture.bag_item_id not in inventory.items:
        raise ValueError(f"pet_capture.bag_item_id missing inventory: {pet_capture.bag_item_id}")
    for sid in pet_capture.species_capture_override:
        if sid not in pets.species:
            raise ValueError(f"pet_capture.species_capture_override unknown species '{sid}'")
    calendar = _parse_calendar(_load_yaml("calendar.yaml"), settings)
    weather = _parse_weather(_load_yaml("weather.yaml"))
    tribulation = _parse_tribulation(_load_yaml("tribulation.yaml"))
    reincarnation = _parse_reincarnation(_load_yaml("reincarnation.yaml"), settings)
    dice = _parse_dice(_load_yaml("dice.yaml"))
    sects = _parse_sects(_load_yaml("sects.yaml"))
    friends = _parse_friends(_load_yaml("friends.yaml"))
    trade = _parse_trade(_load_yaml("trade.yaml"))
    mail = _parse_mail(_load_yaml("mail.yaml"))
    chat = _parse_chat(_load_yaml("chat.yaml"))
    chat_heritage = _parse_chat_heritage(_load_yaml("chat_heritage.yaml"))
    mentor = _parse_mentor(_load_yaml("mentor.yaml"))
    dual_cultivation = _parse_dual_cultivation(_load_yaml("dual_cultivation.yaml"))
    currencies = _parse_currencies(_load_yaml("currencies.yaml"))
    commerce = _parse_commerce(_load_yaml("commerce.yaml"))
    map_cfg = _parse_map(_load_yaml("map.yaml"))
    activity = _parse_activity(_load_yaml("activity.yaml"))
    dao = _parse_dao(_load_yaml("dao.yaml"))
    dao_restraint = _parse_dao_restraint(_load_yaml("dao_restraint.yaml"))
    dao_lord = _parse_dao_lord(_load_yaml("dao_lord.yaml"))
    world_events = _parse_world_events(_load_yaml("world_events.yaml"))
    presence = _parse_presence(_load_yaml("presence.yaml"))
    # 开道门槛须落在境界链
    min_open = str(dao.open.get("min_major_realm") or "true_immortal")
    if min_open not in realms:
        raise ValueError(f"dao.open.min_major_realm={min_open!r} 不在 realms")
    for edge in dao_restraint.edges:
        if edge["attacker"] and edge["attacker"] not in dao.entries:
            raise ValueError(f"dao_restraint attacker unknown: {edge['attacker']}")
        if edge["defender"] and edge["defender"] not in dao.entries:
            raise ValueError(f"dao_restraint defender unknown: {edge['defender']}")
    logger.info(
        "game config loaded realms=%s tick=%ss techniques=%s formations=%s craft=%s "
        "calendar_slot=%ss weather_regions=%s dice_majors=%s facilities=%s map_regions=%s "
        "dao_entries=%s",
        list(realms.keys()),
        idle.tick_seconds,
        list(techniques.keys()),
        list(formations.formations.keys()),
        list(craft_recipes.recipes.keys()),
        calendar.slot_seconds,
        list(weather.regions.keys()),
        list(dice.realm_bounds.keys()),
        list(sects.facilities.keys()),
        list(map_cfg.regions.keys()),
        list(dao.entries.keys()),
    )
    bundle = GameConfigBundle(
        realms=realms,
        body_temper=body_temper,
        idle=idle,
        breakthrough=breakthrough,
        monsters=monsters,
        offline=offline,
        techniques=techniques,
        technique_loadout=technique_loadout,
        divine_abilities=divine_abilities,
        divine_ability_loadout=divine_ability_loadout,
        constitution=constitution,
        grades=grades,
        board=board,
        formations=formations,
        snapshots=snapshots,
        stamina=stamina,
        avatar=avatar,
        divine_sense=divine_sense,
        craft_recipes=craft_recipes,
        pets=pets,
        pet_affixes=pet_affixes,
        pet_skills=pet_skills,
        pet_skill_books=pet_skill_books,
        pet_duel=pet_duel,
        pet_passives=pet_passives,
        pet_feed=pet_feed,
        pet_eggs=pet_eggs,
        pet_encounter=pet_encounter,
        pet_capture=pet_capture,
        inventory=inventory,
        equipment=equipment,
        research=research,
        talisman_effects=talisman_effects,
        calendar=calendar,
        weather=weather,
        tribulation=tribulation,
        reincarnation=reincarnation,
        dice=dice,
        combat_attrs=combat_attrs,
        sects=sects,
        friends=friends,
        trade=trade,
        mail=mail,
        chat=chat,
        chat_heritage=chat_heritage,
        mentor=mentor,
        dual_cultivation=dual_cultivation,
        currencies=currencies,
        commerce=commerce,
        map=map_cfg,
        activity=activity,
        taunt_auras=taunt_auras,
        dao=dao,
        dao_restraint=dao_restraint,
        dao_lord=dao_lord,
        world_events=world_events,
        presence=presence,
    )
    from app.config_source.validate_content import validate_loaded_bundle

    validate_loaded_bundle(bundle)
    return bundle


@lru_cache
def get_game_config() -> GameConfigBundle:
    """返回缓存的玩法配置单例。"""
    return load_game_config()


def clear_game_config_cache() -> None:
    """清空配置缓存（测试或热更后调用）。"""
    get_game_config.cache_clear()


def get_major_realm(major_key: str) -> MajorRealmConfig | None:
    """按大境界键查询配置。"""
    return get_game_config().realms.get(major_key)


def get_current_stage(
    major_realm: str,
    realm_stage: int,
) -> RealmStageConfig | None:
    """查询角色当前档位配置。"""
    major = get_major_realm(major_realm)
    if major is None:
        return None
    return major.stage_by_number(realm_stage)


def build_realm_display(major_realm: str, realm_stage_label: str) -> str:
    """拼接境界展示串。"""
    major = get_major_realm(major_realm)
    major_name = major.name if major else major_realm
    stage_name = STAGE_LABEL_NAMES.get(realm_stage_label, realm_stage_label)
    return f"{major_name}{stage_name}"


def is_perfection_stage(major_realm: str, realm_stage: int) -> bool:
    """当前是否处于该大境界圆满档。"""
    major = get_major_realm(major_realm)
    if major is None:
        return False
    return realm_stage >= major.max_stage()


def offline_cap_hours_for_tier(membership_tier: str) -> float:
    """
    按会员档位返回离线有效小时帽。

    Args:
        membership_tier: free / tier1 / tier2。

    Returns:
        float: 有效小时数。
    """
    offline = get_game_config().offline
    return offline.membership_caps.get(membership_tier, offline.free_cap_hours)
