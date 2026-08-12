"""GM API Schema（M1 + M2 development）。"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class GmSetCharacterRequest(BaseModel):
    """``POST /gm/character/set``：字段皆可选，至少一项。"""

    major_realm: str | None = None
    realm_stage: int | None = Field(default=None, ge=1)
    cultivation_points: int | None = Field(default=None, ge=0)
    realm_progress: int | None = Field(default=None, ge=0)
    body_tempering_points: int | None = Field(default=None, ge=0)
    crafting_exp: int | None = Field(default=None, ge=0)
    breakthrough_grade: str | None = None
    membership_tier: str | None = None
    spirit_stones: int | None = Field(default=None, ge=0)
    idle_direction: str | None = None
    status: str | None = None
    clear_offline_pending: bool | None = None
    # --- M3 战斗成型调试字段 ---
    set_stamina: int | None = Field(default=None, ge=0, description="直接设置体力值")
    trial_puppet_count: int | None = Field(
        default=None,
        ge=0,
        description="设置试炼木傀持有数",
    )
    reset_snapshot_cooldown: bool | None = Field(
        default=None,
        description="清除快照手动更新冷却",
    )
    force_refresh_snapshot: bool | None = Field(
        default=None,
        description="立即用当前防守预设重建快照",
    )
    # --- M4 双线程成长调试 ---
    divine_sense_capacity_bonus: int | None = Field(default=None, ge=0)
    array_craft_level: int | None = Field(default=None, ge=0)
    force_jindan: bool | None = Field(default=None, description="一键设为金丹初期")
    grant_craft_materials: bool | None = Field(default=None, description="发放配方测试材料")
    grant_test_pet: bool | None = Field(default=None, description="发放测试灵宠")
    clear_craft_jobs: bool | None = Field(default=None, description="清空工坊队列")
    clear_divine_sense_backlash: bool | None = Field(default=None)
    # --- M5 环境与轮回 ---
    force_shichen: str | None = Field(default=None, description="强制当前时辰 id")
    force_weather: str | None = Field(default=None, description="强制天气 id")
    start_tribulation: bool | None = Field(default=None, description="强制进入渡劫准备")
    set_awaiting_ferry: bool | None = Field(default=None, description="直接置待引渡")
    force_ferry_timeout: bool | None = Field(default=None, description="立即超时强制轮回")
    mark_story_node: str | None = Field(default=None, description="标记已历剧情节点")
    fate_luck: int | None = Field(default=None, description="设置气运")
    demonic_nature: int | None = Field(default=None, description="设置魔性")
    force_yuanying_peak: bool | None = Field(
        default=None,
        description="一键设为元婴大圆满并灌满进度",
    )
    spirit_root_tags: list[str] | None = Field(
        default=None,
        description="设置灵根环境标签（如 thunder_root）",
    )
    force_tribulation_outcome: str | None = Field(
        default=None,
        description="强制渡劫结局：won / failed / fallen（验收）",
    )
    grant_acceptance_constitution: bool | None = Field(
        default=None,
        description="发放验收体质主/副词条并自动镶嵌",
    )
    # --- M6 大道 / 道主 ---
    force_true_immortal: bool | None = Field(
        default=None,
        description="一键设为真仙初期（可开道）",
    )
    grant_dao_pool: list[str] | None = Field(
        default=None,
        description="灌入指定道 id 入道池",
    )
    set_dao_lord: str | None = Field(
        default=None,
        description="强制任命为该道道主；空字符串清空自己的道主身份",
    )
    open_dao_challenge_window: bool | None = Field(
        default=None,
        description="强制当前处于道主开窗（进程标志；赛会日程仍以 contest 为准）",
    )
    open_dao_contest_now: bool | None = Field(
        default=None,
        description="立刻开赛：关闭报名并收口本场道主之争（P1）",
    )
    clear_dao_challenge_cooldown: bool | None = Field(
        default=None,
        description="清空挑战冷却",
    )
    push_world_env: bool | None = Field(
        default=None,
        description="经 WS 推一条 world.env（若 Hub 有连接）",
    )
    set_dao_qi: int | None = Field(default=None, ge=0, description="直接设置道值")
    set_dao_level: int | None = Field(default=None, ge=1, description="直接设置道等级")
    lock_fate_dao: str | None = Field(
        default=None,
        description="跳过 roll 直接锁定本命道（联调）",
    )
    m6_quick_kit: bool | None = Field(
        default=None,
        description="一键：真仙+锁炎道+灌池+道等级3+道值500+开窗+清冷却+刷快照",
    )

    @model_validator(mode="after")
    def at_least_one_field(self) -> "GmSetCharacterRequest":
        """确保至少修改一项。"""
        values = [
            self.major_realm,
            self.realm_stage,
            self.cultivation_points,
            self.realm_progress,
            self.body_tempering_points,
            self.crafting_exp,
            self.breakthrough_grade,
            self.membership_tier,
            self.spirit_stones,
            self.idle_direction,
            self.status,
            self.clear_offline_pending,
            self.set_stamina,
            self.trial_puppet_count,
            self.reset_snapshot_cooldown,
            self.force_refresh_snapshot,
            self.divine_sense_capacity_bonus,
            self.array_craft_level,
            self.force_jindan,
            self.grant_craft_materials,
            self.grant_test_pet,
            self.clear_craft_jobs,
            self.clear_divine_sense_backlash,
            self.force_shichen,
            self.force_weather,
            self.start_tribulation,
            self.set_awaiting_ferry,
            self.force_ferry_timeout,
            self.mark_story_node,
            self.fate_luck,
            self.demonic_nature,
            self.force_yuanying_peak,
            self.spirit_root_tags,
            self.force_tribulation_outcome,
            self.grant_acceptance_constitution,
            self.force_true_immortal,
            self.grant_dao_pool,
            self.set_dao_lord,
            self.open_dao_challenge_window,
            self.open_dao_contest_now,
            self.clear_dao_challenge_cooldown,
            self.push_world_env,
            self.set_dao_qi,
            self.set_dao_level,
            self.lock_fate_dao,
            self.m6_quick_kit,
        ]
        if all(item is None for item in values):
            raise ValueError("至少提供一项要修改的字段")
        return self
