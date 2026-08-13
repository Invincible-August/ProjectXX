"""
角色请求 / 响应 Schema（M0 §5.6–§5.8；M1/M2 衍生字段）。
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

_CHARACTER_NAME_PATTERN = re.compile(r"^[\u4e00-\u9fa5a-zA-Z0-9]+$")


class CreateCharacterRequest(BaseModel):
    """``POST /characters`` 请求体。"""

    name: str = Field(..., min_length=2, max_length=16, description="道号")
    # M7 L7：创角推荐必选；存量/旧测可省略，进双修前补选
    gender: str | None = Field(
        default=None,
        description="道途阴阳 male|female；建议创角时必选",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """去除首尾空白并校验字符集。"""
        trimmed = value.strip()
        if len(trimmed) < 2 or len(trimmed) > 16:
            raise ValueError("角色名长度须为 2～16 个字符")
        if not _CHARACTER_NAME_PATTERN.fullmatch(trimmed):
            raise ValueError("角色名仅允许中文、字母与数字")
        return trimmed

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, value: str | None) -> str | None:
        """校验性别键。"""
        if value is None or value == "":
            return None
        normalized = str(value).strip().lower()
        if normalized not in ("male", "female"):
            raise ValueError("性别须为 male 或 female")
        return normalized


class CharacterPublic(BaseModel):
    """对外角色面板结构（含 M2 池/进度/品阶/离线字段）。"""

    id: int = Field(description="角色主键")
    name: str = Field(description="道号（全服唯一）")
    gender: str | None = Field(
        default=None,
        description="道途阴阳 male|female；未补选为 null",
    )
    gender_label_zh: str | None = Field(
        default=None,
        description="性别中文展示",
    )
    major_realm: str = Field(description="大境界键，如 body_tempering / qi_refining")
    major_realm_name: str = Field(description="大境界中文名")
    realm_stage: int = Field(description="境界层/期序号（锻体炼气为层，其余为期）")
    realm_stage_label: str = Field(description="层/期标签键，如 layer_1 / early")
    realm_display: str = Field(description="境界展示文案（大境界+层/期）")
    # 成长三池：挂机只涨池；突破门槛读 realm_progress（M2）
    cultivation_points: int = Field(description="修灵池（修为点数，未投入境界进度）")
    body_tempering_points: int = Field(description="淬体度池（挂机炼体产出；可投入淬体进度或炼体功法）")
    # 炼体大境（炼皮→道体，层/期对齐主修）
    body_temper_stage: str = Field(default="refine_skin", description="炼体大境 id")
    body_temper_stage_name: str = Field(default="炼皮", description="炼体大境中文名")
    body_temper_layer: int = Field(default=1, description="炼体层/期序号")
    body_temper_layer_label: str = Field(
        default="layer_1",
        description="炼体层/期标签 layer_N / early / …",
    )
    body_temper_progress: int = Field(default=0, description="当前档淬体进度")
    body_temper_to_next: int | None = Field(
        default=None,
        description="距本档圆满尚需进度；可淬体时为 0",
    )
    body_temper_progress_ratio: float = Field(
        default=0.0,
        description="当前档淬体进度比例 0～1",
    )
    body_temper_display: str = Field(
        default="炼皮一层",
        description="炼体程度展示（含可淬体/卡主修提示）",
    )
    body_temper_capped: bool = Field(
        default=False,
        description="进度已满但主修未达对照境，暂不可淬体",
    )
    body_temper_ready_to_quench: bool = Field(
        default=False,
        description="进度满且条件达标，可发起淬体",
    )
    body_temper_next_stage_name: str | None = Field(
        default=None,
        description="淬体目标展示名",
    )
    crafting_exp: int = Field(description="制造业经验池")
    spirit_stones: int = Field(description="灵石（挂机消耗与交易货币）")
    idle_direction: str = Field(description="本体挂机方向：none/spirit/body/crafting")
    idle_direction_name: str = Field(description="挂机方向中文名")
    status: str = Field(
        description="状态机：normal/breaking_through/tribulation/awaiting_ferry/reincarnating",
    )
    status_name: str = Field(description="状态中文名")
    last_settled_at: str = Field(description="上次挂机 settle 锚点（UTC ISO）")
    created_at: str = Field(description="创角时间 UTC ISO")
    updated_at: str = Field(description="最近更新时间 UTC ISO")
    cultivation_to_next: int | None = Field(
        default=None,
        description="距下一档突破尚需投入的境界进度（可读提示）",
    )
    cultivation_progress_ratio: float = Field(
        default=0.0,
        description="当前档境界进度比例 0～1",
    )
    is_stalled: bool = Field(default=False, description="灵石不足导致挂机停滞")
    idle_cultivation_per_tick: int = Field(default=0, description="修灵方向每 tick 基础产出")
    idle_body_per_tick: int = Field(default=0, description="炼体方向每 tick 基础产出")
    idle_crafting_per_tick: int = Field(default=0, description="制造业方向每 tick 基础产出")
    idle_stones_per_tick: int = Field(default=0, description="每 tick 灵石消耗")
    idle_tick_seconds: int = Field(default=60, description="一片挂机时长（秒）")
    base_atk: int = Field(default=0, description="衍生基础攻击（= combat.final.phys_atk 别名）")
    base_hp: int = Field(default=0, description="衍生基础生命（= combat.final.hp 别名）")
    combat: dict | None = Field(
        default=None,
        description="ATTR CombatAttrBlock：final/primary/labels/breakdown/growth",
    )
    life: dict | None = Field(
        default=None,
        description="ATTR LifeAttrBlock：战斗体力/悟性/吐纳/工坊向等",
    )
    battle_stamina: dict | None = Field(
        default=None,
        description="战斗体力读数：left/cap/regen_per_minute/next_point_in_seconds",
    )
    # --- M2 ---
    realm_progress: int = Field(default=0, description="已投入当前档的境界进度（突破门槛）")
    breakthrough_grade: str = Field(default="none", description="最近跨境品阶键；无跨境为 none")
    breakthrough_grade_name: str = Field(default="无", description="品阶中文名")
    divine_ability_slots: int = Field(default=0, description="由品阶推导的神通槽位数")
    membership_tier: str = Field(default="free", description="会员档：free/tier1/tier2")
    membership_expires_at: str | None = Field(
        default=None,
        description="付费会员过期 UTC ISO；free 为 null",
    )
    offline_cap_hours: float = Field(default=12.0, description="离线收益上限小时数")
    tiandao_points: int = Field(default=0, description="天道点（不可玩家直转）")
    membership: dict | None = Field(
        default=None,
        description="会员摘要：tier/label/expires/idle_cap_hours",
    )
    offline_pending: dict | None = Field(default=None, description="待领取离线明细；无则 null")
    pending_event_logs: list[dict] = Field(
        default_factory=list,
        description="待领取事件日志（如师傅传授）；领取离线收益或 ack 后清空",
    )
    technique_summary: list[dict] = Field(default_factory=list, description="功法摘要列表")
    constitution_summary: dict = Field(
        default_factory=lambda: {"equipped": []},
        description="体质装备摘要",
    )
    # --- M4 双线程成长 ---
    has_avatar: bool = Field(default=False, description="是否已凝练化身")
    avatar_summary: dict | None = Field(default=None, description="化身摘要（方向/三池等）")
    divine_sense: dict | None = Field(default=None, description="神识容量与占用摘要")
    array_craft_level: int = Field(default=0, description="阵法制造等级")
    craft_jobs_summary: dict = Field(
        default_factory=lambda: {"running": 0, "ready": 0},
        description="工坊队列 running/ready 计数",
    )
    inventory_count: int = Field(default=0, description="背包物品种数")
    pets_count: int = Field(default=0, description="持有灵宠数")
    dual_idle_preview: dict | None = Field(default=None, description="本体+化身双线程挂机预览")
    # --- M5 环境与轮回 ---
    reincarnation_points: int = Field(default=0, description="轮回点（跨世货币）")
    reincarnation_count: int = Field(default=0, description="已完成轮回次数")
    peak_major_realm: str = Field(
        default="body_tempering",
        description="历史最高大境界（发点/商店条件）",
    )
    growth_attrs: dict = Field(default_factory=dict, description="剧情/兼容占位成长 JSON")
    permanent_bonus: dict = Field(
        default_factory=dict,
        description="跨世永久加成（独立表：初始/小大突破成长/突破率等）",
    )
    story_flags: dict = Field(
        default_factory=lambda: {"experienced_nodes": []},
        description="剧情已历节点等 flag（无正文）",
    )
    ferry: dict | None = Field(default=None, description="待引渡摘要（截止时刻/剩余秒等）")
    tribulation: dict | None = Field(default=None, description="进行中渡劫会话摘要")
    world_env: dict | None = Field(default=None, description="当前世界时辰+天气摘要")
    fate_luck: int = Field(default=0, description="气运占位（渡劫轴 A：高则降威力乘区）")
    demonic_nature: int = Field(default=0, description="魔性占位（渡劫轴 A：高则抬威力乘区）")
    idle_env: dict | None = Field(
        default=None,
        description="当前环境挂机有效速率预览（时辰×天气×标签 + catalog）",
    )
    spirit_root_tags: list[str] = Field(
        default_factory=list,
        description="灵根环境标签（如 thunder_root），参与挂机乘区",
    )
    activity: dict | None = Field(
        default=None,
        description="活动互斥快照（当前占用 + 各操作可否）",
    )
    dao: dict | None = Field(
        default=None,
        description="大道摘要：本命道/道值/等级/可开道",
    )
    dao_lord: dict | None = Field(
        default=None,
        description="道主身份摘要（仅自己是道主时）",
    )
    sect: dict | None = Field(
        default=None,
        description="宗门摘要：散修占位或入宗贡献/职位/相对散修乘区说明",
    )
    friend_count: int = Field(default=0, description="活跃道友数（M7 L2）")
    social_badges: dict | None = Field(
        default=None,
        description="社交角标占位：mail_unread/chat_unread/dual_invite",
    )
