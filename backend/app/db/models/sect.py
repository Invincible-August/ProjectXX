"""
宗门相关 ORM（M7 L1 + M7-V+ 深化）。

含：宗门行、成员、贡献流水、任务进度、设施等级、人事申请、
藏宝阁、藏经阁、捐赠审核、代工、阵法、矿脉日结、灵药园。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Sect(Base):
    """宗门主表：NPC 模板实例或玩家自建。"""

    __tablename__ = "sects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # npc = 配置驱动；player = 自建
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="npc", index=True)
    # NPC 对应 sects.yaml npc_sects 键；自建可为 null
    template_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    motto: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    # 宗门等级键：hut / mountain_gate / … / dao_court
    grade: Mapped[str] = mapped_column(String(32), nullable=False, default="hut")
    # 专精键：beast / sword / alchemy / formation / talisman
    specialty: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    # 议事厅公告（玩家可见中文）
    announcement: Mapped[str | None] = mapped_column(String(256), nullable=True, default=None)
    # 宗门灵石库（矿脉产出、阵法消耗等）
    spirit_stone_pool: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # 已开启 buff id 列表 JSON，如 ["idle_boost"]
    buffs_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    # 祖师（创建者）；NPC 宗可为 null
    founder_character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # 掌门（可≠祖师）
    leader_character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SectMember(Base):
    """宗门成员：一角色同时最多隶属一个宗门。"""

    __tablename__ = "sect_members"
    __table_args__ = (
        UniqueConstraint("character_id", name="uq_sect_members_character"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sect_id: Mapped[int] = mapped_column(
        ForeignKey("sects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 兼容旧字段：founder / leader / elder / member
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="member")
    # M7-V+ 十二档职位键（laborer … founder）
    rank: Mapped[str] = mapped_column(String(32), nullable=False, default="laborer")
    contribution: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # 最近一次被任命的游戏日号（当日不可再改任命）
    last_appoint_game_day: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    # 最近领取俸禄的游戏日号
    salary_claimed_game_day: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class SectContributionLedger(Base):
    """贡献流水：入宗奖励/任务/商店/兑宠/轮回归零均可审计。"""

    __tablename__ = "sect_contribution_ledger"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sect_id: Mapped[int] = mapped_column(
        ForeignKey("sects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    # 机读原因键：join_bonus / quest_reward / shop_buy / pet_exchange / reincarnation_zero …
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    # 玩家可见中文摘要
    note_zh: Mapped[str | None] = mapped_column(String(128), nullable=True, default=None)
    balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )


class SectQuestProgress(Base):
    """宗门任务进度：同角色同任务按接取方唯一；完成后可再接。"""

    __tablename__ = "sect_quest_progress"
    __table_args__ = (
        UniqueConstraint(
            "character_id",
            "quest_id",
            "assignee",
            name="uq_sect_quest_char_quest_assignee",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sect_id: Mapped[int] = mapped_column(
        ForeignKey("sects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quest_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # body = 本体；avatar = 化身独立接（M4-D06）
    assignee: Mapped[str] = mapped_column(String(16), nullable=False, default="body")
    # accepted / completed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="accepted")
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    meta_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)


class SectFacility(Base):
    """宗门设施等级行。"""

    __tablename__ = "sect_facilities"
    __table_args__ = (
        UniqueConstraint("sect_id", "facility_id", name="uq_sect_facility"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sect_id: Mapped[int] = mapped_column(
        ForeignKey("sects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    facility_id: Mapped[str] = mapped_column(String(64), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class SectRankApplication(Base):
    """职位自荐 / 贡献晋升申请（次日懒自动通过）。"""

    __tablename__ = "sect_rank_applications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sect_id: Mapped[int] = mapped_column(
        ForeignKey("sects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 目标职位键
    target_rank: Mapped[str] = mapped_column(String(32), nullable=False)
    # contrib_self = 贡献自升；self_recommend = 需任命职位的毛遂自荐
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="contrib_self")
    # pending / auto_passed / appointed / rejected / cancelled
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    apply_game_day: Mapped[int] = mapped_column(Integer, nullable=False)
    resolve_game_day: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class SectTreasuryItem(Base):
    """藏宝阁库存条目（按页管理；page=0 为基础兑换区不占分配权）。"""

    __tablename__ = "sect_treasury_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sect_id: Mapped[int] = mapped_column(
        ForeignKey("sects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    label_zh: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    deposited_by: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class SectScriptureEntry(Base):
    """藏经阁已收录功法。"""

    __tablename__ = "sect_scripture_entries"
    __table_args__ = (
        UniqueConstraint("sect_id", "technique_id", name="uq_sect_scripture"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sect_id: Mapped[int] = mapped_column(
        ForeignKey("sects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    technique_id: Mapped[str] = mapped_column(String(64), nullable=False)
    label_zh: Mapped[str] = mapped_column(String(64), nullable=False)
    specialty_tag: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # catalog = 配置目录；donated = 弟子上供；self_research = 自研（须审核）
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="catalog")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class SectDonationReview(Base):
    """上供审核：功法 / 图纸 / 阵法。"""

    __tablename__ = "sect_donation_reviews"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sect_id: Mapped[int] = mapped_column(
        ForeignKey("sects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # scripture / blueprint / formation
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # pending / approved / rejected
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    reviewer_character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )


class SectCraftJob(Base):
    """宗门工坊代工任务。"""

    __tablename__ = "sect_craft_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sect_id: Mapped[int] = mapped_column(
        ForeignKey("sects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch: Mapped[str] = mapped_column(String(32), nullable=False)
    craftsman_id: Mapped[str] = mapped_column(String(64), nullable=False)
    recipe_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # running / claimed / failed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    quality: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    finish_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )


class SectFormationState(Base):
    """宗门大阵状态（每宗一条）。"""

    __tablename__ = "sect_formation_state"
    __table_args__ = (
        UniqueConstraint("sect_id", name="uq_sect_formation_state"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sect_id: Mapped[int] = mapped_column(
        ForeignKey("sects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    formation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 已学习/上供的阵法 id 列表 JSON
    learned_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    # 阵法加点：{"attack":0,"defense":0,"resistance":0}
    attr_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)


class SectMineState(Base):
    """矿脉被动产出锚点（每宗一条；灵石直接入宗门库）。"""

    __tablename__ = "sect_mine_states"
    __table_args__ = (
        UniqueConstraint("sect_id", name="uq_sect_mine_state"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sect_id: Mapped[int] = mapped_column(
        ForeignKey("sects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    last_accrued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class SectMineMiner(Base):
    """矿脉采矿挂机席位（一名弟子同时最多占一席）。"""

    __tablename__ = "sect_mine_miners"
    __table_args__ = (
        UniqueConstraint("character_id", name="uq_sect_mine_miner_char"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sect_id: Mapped[int] = mapped_column(
        ForeignKey("sects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    last_settled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class SectMineClaim(Base):
    """（废弃兼容）旧矿脉日领记录表；新逻辑不再写入。"""

    __tablename__ = "sect_mine_claims"
    __table_args__ = (
        UniqueConstraint("sect_id", "game_day", name="uq_sect_mine_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sect_id: Mapped[int] = mapped_column(
        ForeignKey("sects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    game_day: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claimed_by: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class SectWorkshopBlueprint(Base):
    """宗门工坊已收录图纸（配置目录 + 弟子上缴）。"""

    __tablename__ = "sect_workshop_blueprints"
    __table_args__ = (
        UniqueConstraint(
            "sect_id",
            "branch",
            "recipe_id",
            name="uq_sect_workshop_blueprint",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sect_id: Mapped[int] = mapped_column(
        ForeignKey("sects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # smithing / alchemy / talisman
    branch: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    recipe_id: Mapped[str] = mapped_column(String(64), nullable=False)
    label_zh: Mapped[str] = mapped_column(String(64), nullable=False)
    cost_contribution: Mapped[int] = mapped_column(Integer, nullable=False, default=40)
    # catalog = 配置初始；donated = 弟子上缴；self_research = 自创（审核后）
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="donated")
    sellable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deposited_by: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class SectHerbPlot(Base):
    """灵药园种植地块。"""

    __tablename__ = "sect_herb_plots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sect_id: Mapped[int] = mapped_column(
        ForeignKey("sects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    herbalist_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # True=托管种植（须聘灵植师）
    hosted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    plant_game_day: Mapped[int] = mapped_column(Integer, nullable=False)
    ready_game_day: Mapped[int] = mapped_column(Integer, nullable=False)
    # growing / harvested
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="growing")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
