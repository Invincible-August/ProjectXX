"""
角色应用服务：创建角色、查询、战力聚合、序列化为 CharacterPublic。

M2：进度读 realm_progress；含品阶/离线/功法/体质衍生字段。
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time_utils import now_utc, to_utc_iso
from app.db.models.character import Character
from app.db.models.user import User
from app.domain.reincarnation_rules import combat_attr_multiplier, parse_growth_attrs, parse_story_flags
from app.schemas.character import CharacterPublic, CreateCharacterRequest
from app.schemas.common import AppError
from app.services.realm_config import (
    IDLE_DIRECTION_NAMES,
    STATUS_NAMES,
    build_realm_display,
    gain_per_tick_for,
    get_current_stage,
    get_game_config,
    get_major_realm,
    offline_cap_hours_for_tier,
    stones_per_tick_for,
)

logger = logging.getLogger(__name__)


class CharacterService:
    """
    角色用例：创角、面板、战力权威入口。

    Attributes:
        _session: 请求级异步会话。
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: SQLAlchemy 异步会话。
        """
        self._session = session

    async def get_by_user_id(self, user_id: int) -> Character | None:
        """按 user_id 查询角色（一对一）。"""
        result = await self._session.execute(
            select(Character).where(Character.user_id == user_id).limit(1),
        )
        return result.scalar_one_or_none()

    async def user_has_character(self, user_id: int) -> bool:
        """判断账号是否已有角色。"""
        result = await self._session.execute(
            select(Character.id).where(Character.user_id == user_id).limit(1),
        )
        return result.scalar_one_or_none() is not None

    async def build_combat_attrs(
        self,
        character: Character,
        *,
        entity_kind: str = "player",
    ) -> dict:
        """
        组装统一 CombatAttrBlock + LifeAttrBlock（ATTR 权威入口）。

        Args:
            character: 角色 ORM。
            entity_kind: 实体类型（默认 player）。

        Returns:
            dict: combat / life / technique_summary / constitution_summary。
        """
        from sqlalchemy import select

        from app.db.models.reincarnation_bonus import CharacterReincarnationBonus
        from app.domain.combat import (
            PRIMARY_KEYS,
            assemble_combat_attr_block,
            assemble_life_attr_block,
            CombatAttrAssembleInput,
        )
        from app.services.constitution_service import ConstitutionService
        from app.services.grade_service import GradeService
        from app.services.technique_service import TechniqueService

        techniques_svc = TechniqueService(self._session)
        constitution_svc = ConstitutionService(self._session)
        cfg = get_game_config().combat_attrs

        stage = get_current_stage(character.major_realm, character.realm_stage)
        realm_atk = stage.base_atk if stage else 0
        realm_hp = stage.base_hp if stage else 0
        # 人物境界无 base_speed：回退 combat_attrs.defaults 或棋盘 main 默认
        realm_speed = int(cfg.defaults.get("speed", 10))
        main_defaults = get_game_config().board.unit_defaults.get("main")
        if main_defaults is not None:
            realm_speed = int(main_defaults.speed)

        bonus_row = (
            await self._session.execute(
                select(CharacterReincarnationBonus).where(
                    CharacterReincarnationBonus.character_id == character.id,
                ),
            )
        ).scalar_one_or_none()
        rein_mult = combat_attr_multiplier(
            float(bonus_row.initial_attr_bonus) if bonus_row else 0.0,
            float(bonus_row.lifetime_applied_growth) if bonus_row else 0.0,
        )

        grade_cfg = GradeService.get_grade_config(character.breakthrough_grade)
        grade_atk_mul = grade_cfg.atk_mul if grade_cfg is not None else 1.0
        grade_hp_mul = grade_cfg.hp_mul if grade_cfg is not None else 1.0

        techniques = await techniques_svc.list_my_techniques(character)
        tech_atk, tech_hp = TechniqueService.compute_technique_combat_bonuses(techniques)
        cons_atk, cons_hp = await constitution_svc.compute_constitution_combat_bonuses(
            character.id,
        )
        cons_state = await constitution_svc.get_constitution_state(character)

        growth_attrs = parse_growth_attrs(getattr(character, "growth_attrs_json", None))
        primary: dict[str, int] = {}
        for pk in PRIMARY_KEYS:
            # growth_attrs 可覆盖占位；缺省 0
            raw = growth_attrs.get(pk, cfg.attrs[pk].default if pk in cfg.attrs else 0)
            try:
                primary[pk] = int(raw)
            except (TypeError, ValueError):
                primary[pk] = 0

        labels = {k: a.label_zh for k, a in cfg.attrs.items()}
        # defaults：抗性/法攻等从 attrs.default 与顶层 defaults 合并
        defaults: dict[str, float] = dict(cfg.defaults)
        for key, adef in cfg.attrs.items():
            defaults.setdefault(key, float(adef.default))

        combat = assemble_combat_attr_block(
            CombatAttrAssembleInput(
                realm_phys_atk=realm_atk,
                realm_hp=realm_hp,
                realm_speed=realm_speed,
                rein_mult=rein_mult,
                grade_atk_mul=grade_atk_mul,
                grade_hp_mul=grade_hp_mul,
                technique_phys_atk=tech_atk,
                technique_hp=tech_hp,
                constitution_phys_atk=cons_atk,
                constitution_hp=cons_hp,
                primary=primary,
                primary_map=dict(cfg.primary_map),
                defaults=defaults,
                labels=labels,
                channels=dict(cfg.channels),
                schema_version=cfg.schema_version,
                entity_kind=entity_kind,
                growth={
                    "physique": int(growth_attrs.get("physique", 0) or 0),
                    "reincarnation_growth": float(
                        bonus_row.lifetime_applied_growth if bonus_row else 0.0,
                    ),
                    "fate_luck": int(getattr(character, "fate_luck", 0) or 0),
                    "demonic_nature": int(getattr(character, "demonic_nature", 0) or 0),
                },
            ),
        )

        life_values: dict[str, float | int] = {
            "comprehension": primary.get("comprehension", 0),
            "stamina": int(getattr(character, "stamina", 0) or 0),
            "resist_heart_demon": int(growth_attrs.get("resist_heart_demon", 0) or 0),
            "resist_tribulation": int(growth_attrs.get("resist_tribulation", 0) or 0),
            "breath_efficiency": float(
                growth_attrs.get(
                    "breath_efficiency",
                    defaults.get("breath_efficiency", 1.0),
                ),
            ),
            "endurance": int(growth_attrs.get("endurance", 0) or 0),
            "craft_dexterity": int(growth_attrs.get("craft_dexterity", 0) or 0),
            "precision": int(growth_attrs.get("precision", 0) or 0),
            "temperament": int(growth_attrs.get("temperament", 0) or 0),
        }
        life = assemble_life_attr_block(
            values=life_values,
            labels=labels,
            schema_version=cfg.schema_version,
            breakdown=[
                {
                    "source": "character",
                    "label_zh": "角色状态",
                    "stamina": life_values["stamina"],
                },
            ],
        )

        return {
            "combat": combat,
            "life": life,
            "technique_summary": TechniqueService.technique_summary_for_character(
                techniques,
            ),
            "constitution_summary": ConstitutionService.constitution_summary_from_state(
                cons_state,
            ),
        }

    async def build_combat_stats(
        self,
        character: Character,
    ) -> tuple[int, int, list[dict], dict]:
        """
        计算含品阶/功法/体质/轮回永久加成修正后的 atk/hp（兼容包装）。

        Returns:
            tuple: (final_atk, final_hp, technique_summary, constitution_summary)。
        """
        packed = await self.build_combat_attrs(character)
        final = packed["combat"]["final"]
        return (
            int(final["phys_atk"]),
            int(final["hp"]),
            packed["technique_summary"],
            packed["constitution_summary"],
        )

    def to_public(
        self,
        character: Character,
        *,
        technique_summary: list[dict] | None = None,
        constitution_summary: dict | None = None,
        offline_pending: dict | None = None,
        final_atk: int | None = None,
        final_hp: int | None = None,
        combat: dict | None = None,
        life: dict | None = None,
        has_avatar: bool = False,
        avatar_summary: dict | None = None,
        divine_sense: dict | None = None,
        array_craft_level: int | None = None,
        craft_jobs_summary: dict | None = None,
        inventory_count: int = 0,
        pets_count: int = 0,
        dual_idle_preview: dict | None = None,
        ferry: dict | None = None,
        tribulation: dict | None = None,
        world_env: dict | None = None,
        idle_env: dict | None = None,
        activity: dict | None = None,
        dao: dict | None = None,
        dao_lord: dict | None = None,
        sect: dict | None = None,
        friend_count: int = 0,
        social_badges: dict | None = None,
    ) -> CharacterPublic:
        """将 ORM 实体转为对外 CharacterPublic。"""
        from app.domain.activity_mutex import build_activity_snapshot
        from app.domain.env_preview import parse_spirit_root_tags_json
        from app.services.grade_service import GradeService
        from app.services.idle_service import IdleService

        major = get_major_realm(character.major_realm)
        major_name = major.name if major else character.major_realm
        stage = get_current_stage(character.major_realm, character.realm_stage)
        idle_cfg = get_game_config().idle
        from app.domain.body_temper import build_body_temper_public

        body_temper_pub = build_body_temper_public(character)

        cultivation_to_next: int | None = None
        progress_ratio = 0.0
        base_atk = 0
        base_hp = 0
        if stage is not None:
            cultivation_to_next = stage.cultivation_required
            if stage.cultivation_required > 0:
                progress_ratio = min(
                    1.0,
                    float(character.realm_progress) / float(stage.cultivation_required),
                )
            base_atk = stage.base_atk
            base_hp = stage.base_hp

        stone_cost = stones_per_tick_for(character)
        idle_cultivation = 0
        idle_body = 0
        idle_crafting = 0
        if character.idle_direction == "spirit" and idle_cfg.spirit.enabled:
            idle_cultivation = gain_per_tick_for(character, "spirit")
        elif character.idle_direction == "body" and idle_cfg.body.enabled:
            idle_body = gain_per_tick_for(character, "body")
        elif character.idle_direction == "crafting" and idle_cfg.crafting.enabled:
            idle_crafting = gain_per_tick_for(character, "crafting")

        grade_names = GradeService.grade_name_map()
        grade_id = character.breakthrough_grade
        grade_name = grade_names.get(grade_id, "无") if grade_id != "none" else "无"

        pending = (
            offline_pending
            if offline_pending is not None
            else IdleService.parse_offline_pending(character)
        )

        ferry_payload = ferry
        if ferry_payload is None and character.status == "awaiting_ferry":
            from app.domain.ferry_rules import can_self_rescue
            from app.core.time_utils import ensure_aware_utc, now_utc

            rein = get_game_config().reincarnation
            cost = int(rein.self_rescue.get("spirit_stone_cost", 500))
            cooldown_total = int(rein.self_rescue.get("cooldown_seconds", 0))
            current = now_utc()
            last = (
                ensure_aware_utc(character.last_self_rescue_at)
                if character.last_self_rescue_at is not None
                else None
            )
            ok, reason, cd_left = can_self_rescue(
                status=character.status,
                spirit_stones=int(character.spirit_stones),
                cost=cost,
                last_rescue_at=last,
                now=current,
                cooldown_seconds=cooldown_total,
            )
            ferry_payload = {
                "deadline_at": (
                    to_utc_iso(character.ferry_deadline_at)
                    if character.ferry_deadline_at
                    else None
                ),
                "can_self_rescue": ok,
                "self_rescue_reason": reason or None,
                "self_rescue_cost": cost,
                "self_rescue_cost_currency": "spirit_stones",
                "self_rescue_cost_label": "灵石",
                "self_rescue_cooldown_seconds": cd_left,
                "self_rescue_cooldown_total_seconds": cooldown_total,
                "spirit_stones": int(character.spirit_stones),
            }

        spirit_root_tags = parse_spirit_root_tags_json(
            getattr(character, "spirit_root_tags_json", None),
        )

        jobs_summary = craft_jobs_summary or {"running": 0, "ready": 0}
        activity_payload = activity
        if activity_payload is None:
            activity_payload = build_activity_snapshot(
                status=str(character.status or "normal"),
                idle_direction=str(character.idle_direction or "none"),
                craft_running=int(jobs_summary.get("running") or 0),
                in_secret_realm=False,
            )

        return CharacterPublic(
            id=character.id,
            name=character.name,
            gender=(
                str(character.gender).strip().lower()
                if getattr(character, "gender", None)
                else None
            ),
            gender_label_zh=(
                "乾道（男）"
                if str(getattr(character, "gender", "") or "").lower() == "male"
                else "坤道（女）"
                if str(getattr(character, "gender", "") or "").lower() == "female"
                else None
            ),
            major_realm=character.major_realm,
            major_realm_name=major_name,
            realm_stage=character.realm_stage,
            realm_stage_label=character.realm_stage_label,
            realm_display=build_realm_display(
                character.major_realm,
                character.realm_stage_label,
            ),
            cultivation_points=int(character.cultivation_points),
            body_tempering_points=int(character.body_tempering_points),
            body_temper_stage=str(body_temper_pub["body_temper_stage"]),
            body_temper_stage_name=str(body_temper_pub["body_temper_stage_name"]),
            body_temper_layer=int(body_temper_pub.get("body_temper_layer") or 1),
            body_temper_layer_label=str(
                body_temper_pub.get("body_temper_layer_label") or "layer_1",
            ),
            body_temper_progress=int(body_temper_pub["body_temper_progress"]),
            body_temper_to_next=body_temper_pub["body_temper_to_next"],
            body_temper_progress_ratio=float(body_temper_pub["body_temper_progress_ratio"]),
            body_temper_display=str(body_temper_pub["body_temper_display"]),
            body_temper_capped=bool(body_temper_pub["body_temper_capped"]),
            body_temper_ready_to_quench=bool(
                body_temper_pub.get("body_temper_ready_to_quench", False),
            ),
            body_temper_next_stage_name=body_temper_pub.get("body_temper_next_stage_name"),
            crafting_exp=int(character.crafting_exp),
            spirit_stones=int(character.spirit_stones),
            idle_direction=character.idle_direction,
            idle_direction_name=IDLE_DIRECTION_NAMES.get(
                character.idle_direction,
                character.idle_direction,
            ),
            status=character.status,
            status_name=STATUS_NAMES.get(character.status, character.status),
            last_settled_at=to_utc_iso(character.last_settled_at),
            created_at=to_utc_iso(character.created_at),
            updated_at=to_utc_iso(character.updated_at),
            cultivation_to_next=cultivation_to_next,
            cultivation_progress_ratio=progress_ratio,
            is_stalled=IdleService.is_currently_stalled(character),
            idle_cultivation_per_tick=idle_cultivation,
            idle_body_per_tick=idle_body,
            idle_crafting_per_tick=idle_crafting,
            idle_stones_per_tick=stone_cost if character.idle_direction != "none" else 0,
            idle_tick_seconds=idle_cfg.tick_seconds,
            base_atk=final_atk if final_atk is not None else base_atk,
            base_hp=final_hp if final_hp is not None else base_hp,
            combat=combat,
            life=life,
            realm_progress=int(character.realm_progress),
            breakthrough_grade=grade_id,
            breakthrough_grade_name=grade_name,
            divine_ability_slots=int(character.divine_ability_slots),
            membership_tier=character.membership_tier,
            membership_expires_at=(
                to_utc_iso(character.membership_expires_at)
                if getattr(character, "membership_expires_at", None) is not None
                else None
            ),
            offline_cap_hours=offline_cap_hours_for_tier(character.membership_tier),
            tiandao_points=int(getattr(character, "tiandao_points", 0) or 0),
            membership={
                "tier": character.membership_tier,
                "expires_at": (
                    to_utc_iso(character.membership_expires_at)
                    if getattr(character, "membership_expires_at", None) is not None
                    else None
                ),
                "idle_cap_hours": offline_cap_hours_for_tier(character.membership_tier),
            },
            offline_pending=pending,
            technique_summary=technique_summary or [],
            constitution_summary=constitution_summary or {"equipped": []},
            has_avatar=has_avatar,
            avatar_summary=avatar_summary,
            divine_sense=divine_sense,
            array_craft_level=int(array_craft_level if array_craft_level is not None else character.array_craft_level),
            craft_jobs_summary=craft_jobs_summary or {"running": 0, "ready": 0},
            inventory_count=inventory_count,
            pets_count=pets_count,
            dual_idle_preview=dual_idle_preview,
            reincarnation_points=int(getattr(character, "reincarnation_points", 0) or 0),
            reincarnation_count=int(getattr(character, "reincarnation_count", 0) or 0),
            peak_major_realm=str(
                getattr(character, "peak_major_realm", None) or character.major_realm,
            ),
            growth_attrs=parse_growth_attrs(getattr(character, "growth_attrs_json", None)),
            permanent_bonus=dict(getattr(character, "_permanent_bonus_public", None) or {}),
            story_flags=parse_story_flags(getattr(character, "story_flags_json", None)),
            ferry=ferry_payload,
            tribulation=tribulation,
            world_env=world_env,
            fate_luck=int(getattr(character, "fate_luck", 0) or 0),
            demonic_nature=int(getattr(character, "demonic_nature", 0) or 0),
            idle_env=idle_env,
            spirit_root_tags=spirit_root_tags,
            activity=activity_payload,
            dao=dao,
            dao_lord=dao_lord,
            sect=sect,
            friend_count=int(friend_count or 0),
            social_badges=social_badges
            or {"mail_unread": 0, "chat_unread": 0, "dual_invite": 0},
        )

    @staticmethod
    def public_to_dict(public: CharacterPublic) -> dict:
        """将 CharacterPublic 转为可 JSON 序列化的 dict。"""
        return public.model_dump()

    async def enrich_public(
        self,
        character: Character,
        *,
        offline_pending: dict | None = None,
    ) -> CharacterPublic:
        """将角色转为含完整战力/功法/体质/M4 摘要的 CharacterPublic。"""
        from app.services.avatar_service import AvatarService
        from app.services.commerce_service import refresh_membership_for_idle
        from app.services.craft_service import CraftService
        from app.services.divine_sense_service import DivineSenseService
        from app.services.inventory_service import InventoryService
        from app.services.pet_service import PetService

        await refresh_membership_for_idle(self._session, character)
        packed = await self.build_combat_attrs(character)
        final_atk = int(packed["combat"]["final"]["phys_atk"])
        final_hp = int(packed["combat"]["final"]["hp"])
        tech_sum = packed["technique_summary"]
        cons_sum = packed["constitution_summary"]
        combat_block = packed["combat"]
        life_block = packed["life"]
        # 挂载永久加成摘要供 to_public 序列化
        from sqlalchemy import select

        from app.db.models.reincarnation_bonus import CharacterReincarnationBonus

        bonus_row = (
            await self._session.execute(
                select(CharacterReincarnationBonus).where(
                    CharacterReincarnationBonus.character_id == character.id,
                ),
            )
        ).scalar_one_or_none()
        if bonus_row is not None:
            setattr(
                character,
                "_permanent_bonus_public",
                {
                    "initial_attr_bonus": float(bonus_row.initial_attr_bonus),
                    "minor_growth_bonus": float(bonus_row.minor_growth_bonus),
                    "major_growth_bonus": float(bonus_row.major_growth_bonus),
                    "break_rate_bonus": float(bonus_row.break_rate_bonus),
                    "lifetime_applied_growth": float(bonus_row.lifetime_applied_growth),
                    "constitution_slots_bought": int(bonus_row.constitution_slots_bought),
                    "spirit_root_slots_bought": int(bonus_row.spirit_root_slots_bought),
                },
            )
        else:
            setattr(character, "_permanent_bonus_public", {})

        avatar_svc = AvatarService(self._session)
        # 大厅/角色摘要走 lite，避免每次 enrich 重建功能表并脏写体力
        avatar_panel = await avatar_svc.get_summary(character)
        craft_svc = CraftService(self._session)
        inv_svc = InventoryService(self._session)
        pet_svc = PetService(self._session)

        avatar_cfg = get_game_config().avatar
        dual_preview = None
        if avatar_panel:
            # 双线程摘要：各方向速率 + 化身耗石（供大厅修炼区进度条预测）
            av_dir = str(avatar_panel.get("idle_direction") or "none")
            main_stones = stones_per_tick_for(character)
            avatar_stones = max(
                1,
                int(main_stones * avatar_cfg.spirit_stone_cost_per_tick_ratio),
            )
            dual_preview = {
                "main_idle_direction": character.idle_direction,
                "main_cultivation_per_tick": (
                    gain_per_tick_for(character, "spirit")
                    if character.idle_direction == "spirit"
                    else 0
                ),
                "main_body_per_tick": (
                    gain_per_tick_for(character, "body")
                    if character.idle_direction == "body"
                    else 0
                ),
                "main_crafting_per_tick": (
                    gain_per_tick_for(character, "crafting")
                    if character.idle_direction == "crafting"
                    else 0
                ),
                "avatar_idle_direction": av_dir,
                "avatar_cultivation_per_tick": (
                    avatar_cfg.spirit_rates.gain_per_tick if av_dir == "spirit" else 0
                ),
                "avatar_body_per_tick": (
                    avatar_cfg.body_rates.gain_per_tick if av_dir == "body" else 0
                ),
                "avatar_crafting_per_tick": (
                    avatar_cfg.crafting_rates.gain_per_tick if av_dir == "crafting" else 0
                ),
                "avatar_stones_per_tick": (
                    avatar_stones if av_dir in ("spirit", "body", "crafting") else 0
                ),
                "avatar_last_settled_at": avatar_panel.get("last_settled_at"),
            }

        # M5：渡劫摘要与世界环境（可选嵌入）
        tribulation_summary = None
        if character.status == "tribulation":
            from app.db.models.tribulation_session import TribulationSession
            from sqlalchemy import select as sa_select

            result = await self._session.execute(
                sa_select(TribulationSession)
                .where(
                    TribulationSession.character_id == character.id,
                    TribulationSession.phase.in_(
                        ("preparing", "committed", "running"),
                    ),
                )
                .order_by(TribulationSession.id.desc())
                .limit(1),
            )
            trib_row = result.scalar_one_or_none()
            if trib_row is not None:
                tribulation_summary = {
                    "session_id": trib_row.id,
                    "phase": trib_row.phase,
                    "power_tier": trib_row.power_tier,
                    "count_tier": trib_row.count_tier,
                    "strike_done": trib_row.strike_done,
                    "strike_total": trib_row.strike_total,
                    "hp_current": trib_row.hp_current,
                    "hp_max": trib_row.hp_max,
                    "locked_shichen": trib_row.locked_shichen,
                    "locked_weather": trib_row.locked_weather,
                }

        from app.services.calendar_service import CalendarService
        from app.services.env_preview_service import build_character_idle_env
        from app.services.weather_service import WeatherService

        cal = CalendarService().get_snapshot()
        wx = WeatherService().get_snapshot()
        world_env = {
            "shichen": cal["shichen_id"],
            "shichen_label": cal.get("label"),
            "weather": wx["weather_id"],
            "weather_label": wx.get("label"),
            "next_shichen_at": cal.get("next_at"),
            "in_cloud": wx.get("in_cloud", False),
        }
        idle_env = await build_character_idle_env(self._session, character)

        dao_summary = None
        dao_lord_summary = None
        try:
            from app.services.dao_service import DaoService
            from app.services.dao_lord_service import DaoLordService

            dao_summary = await DaoService(self._session).enrich_dao_summary(character)
            dao_lord_summary = await DaoLordService(self._session).enrich_lord_summary(
                character,
            )
        except Exception:  # noqa: BLE001
            logger.exception("dao enrich failed character_id=%s", character.id)

        sect_summary = None
        try:
            from app.services.sect_service import SectService

            sect_summary = await SectService(self._session).enrich_sect_summary(character)
        except Exception:  # noqa: BLE001
            logger.exception("sect enrich failed character_id=%s", character.id)

        friend_count = 0
        try:
            from app.services.friend_service import FriendService

            friend_count = await FriendService(self._session).friend_count(character.id)
        except Exception:  # noqa: BLE001
            logger.exception("friend count failed character_id=%s", character.id)

        mail_unread = 0
        try:
            from app.services.mail_service import MailService

            mail_unread = await MailService(self._session).unread_count(character.id)
        except Exception:  # noqa: BLE001
            logger.exception("mail unread failed character_id=%s", character.id)

        chat_unread = 0
        try:
            from app.services.chat_service import ChatService

            chat_unread = await ChatService(self._session).total_unread(character.id)
        except Exception:  # noqa: BLE001
            logger.exception("chat unread failed character_id=%s", character.id)

        return self.to_public(
            character,
            technique_summary=tech_sum,
            constitution_summary=cons_sum,
            offline_pending=offline_pending,
            final_atk=final_atk,
            final_hp=final_hp,
            combat=combat_block,
            life=life_block,
            has_avatar=avatar_panel is not None,
            avatar_summary=avatar_panel,
            divine_sense=await avatar_svc.get_sense(character),
            craft_jobs_summary=await craft_svc.jobs_summary(character.id),
            inventory_count=await inv_svc.count_items(character.id),
            pets_count=await pet_svc.count_pets(character.id),
            dual_idle_preview=dual_preview,
            tribulation=tribulation_summary,
            world_env=world_env,
            idle_env=idle_env,
            dao=dao_summary,
            dao_lord=dao_lord_summary,
            sect=sect_summary,
            friend_count=friend_count,
            social_badges={
                "mail_unread": mail_unread,
                "chat_unread": chat_unread,
                "dual_invite": 0,
            },
        )

    async def create(
        self,
        user: User,
        payload: CreateCharacterRequest,
    ) -> CharacterPublic:
        """
        为当前账号创建角色（一账号一角色；道号全服唯一）。

        M2：发放默认功法与体质样本。
        """
        from app.services.constitution_service import ConstitutionService
        from app.services.technique_service import TechniqueService

        settings = get_settings()

        if await self.user_has_character(user.id):
            raise AppError(code=40004, message="该账号已有角色", http_status=409)

        existing_name = await self._session.execute(
            select(Character.id).where(Character.name == payload.name).limit(1),
        )
        if existing_name.scalar_one_or_none() is not None:
            raise AppError(code=40003, message="角色名已存在", http_status=409)

        created_at = now_utc()
        character = Character(
            user_id=user.id,
            name=payload.name,
            gender=payload.gender,
            major_realm="body_tempering",
            realm_stage=1,
            realm_stage_label="layer_1",
            peak_major_realm="body_tempering",
            cultivation_points=0,
            body_tempering_points=0,
            body_temper_stage="refine_skin",
            body_temper_layer=1,
            body_temper_layer_label="layer_1",
            body_temper_progress=0,
            crafting_exp=0,
            realm_progress=0,
            spirit_stones=settings.initial_spirit_stones,
            idle_direction="none",
            status="normal",
            last_settled_at=created_at,
            created_at=created_at,
            updated_at=created_at,
        )
        self._session.add(character)
        await self._session.flush()
        await self._session.refresh(character)

        from app.db.models.reincarnation_bonus import CharacterReincarnationBonus

        self._session.add(CharacterReincarnationBonus(character_id=character.id))
        await self._session.flush()

        await TechniqueService(self._session).ensure_default_techniques(character.id)
        await ConstitutionService(self._session).grant_starter_constitution_kit(
            character.id,
        )

        logger.info(
            "character created user_id=%s character_id=%s name=%s",
            user.id,
            character.id,
            character.name,
        )
        return await self.enrich_public(character)

    async def get_mine(self, user: User) -> CharacterPublic:
        """
        获取当前账号角色面板。

        先 ``ensure_offline_pending_async``（短缺口双线程 settle / 长缺口写分列 pending），
        **禁止**先无帽 ``settle`` 再补 pending，否则会绕过离线帽。
        """
        from app.services.idle_service import IdleService

        character = await self.get_by_user_id(user.id)
        if character is None:
            raise AppError(code=40005, message="尚未创建角色", http_status=404)

        idle = IdleService(self._session)
        if not character.pending_offline_json:
            # 短缺口双线程 settle / 长缺口写分列 pending（D10）
            await idle.ensure_offline_pending_async(character)

        # M5-D05：大厅轮询拉取角色时懒结算到期读条
        from app.services.breakthrough_service import lazy_resolve_breakthrough_channel

        await lazy_resolve_breakthrough_channel(
            self._session,
            character,
            now=None,
            user=user,
        )

        await self._session.flush()
        await self._session.refresh(character)

        return await self.enrich_public(
            character,
            offline_pending=IdleService.parse_offline_pending(character),
        )


# ---------------------------------------------------------------------------
# 兼容包装
# ---------------------------------------------------------------------------


async def build_combat_stats(
    session: AsyncSession,
    character: Character,
) -> tuple[int, int, list[dict], dict]:
    """兼容包装。"""
    return await CharacterService(session).build_combat_stats(character)


async def enrich_character_public(
    session: AsyncSession,
    character: Character,
    *,
    offline_pending: dict | None = None,
) -> CharacterPublic:
    """兼容包装。"""
    return await CharacterService(session).enrich_public(
        character,
        offline_pending=offline_pending,
    )


def character_to_public(
    character: Character,
    *,
    technique_summary: list[dict] | None = None,
    constitution_summary: dict | None = None,
    offline_pending: dict | None = None,
    final_atk: int | None = None,
    final_hp: int | None = None,
) -> CharacterPublic:
    """兼容包装（无 session 的纯序列化路径）。"""
    service = object.__new__(CharacterService)
    service._session = None  # type: ignore[assignment]
    return CharacterService.to_public(
        service,
        character,
        technique_summary=technique_summary,
        constitution_summary=constitution_summary,
        offline_pending=offline_pending,
        final_atk=final_atk,
        final_hp=final_hp,
    )


def character_public_to_dict(public: CharacterPublic) -> dict:
    """兼容包装。"""
    return CharacterService.public_to_dict(public)


async def user_has_character(session: AsyncSession, user_id: int) -> bool:
    """兼容包装。"""
    return await CharacterService(session).user_has_character(user_id)


async def get_character_by_user_id(
    session: AsyncSession,
    user_id: int,
) -> Character | None:
    """兼容包装。"""
    return await CharacterService(session).get_by_user_id(user_id)


async def create_character(
    session: AsyncSession,
    user: User,
    payload: CreateCharacterRequest,
) -> CharacterPublic:
    """兼容包装。"""
    return await CharacterService(session).create(user, payload)


async def get_my_character(
    session: AsyncSession,
    user: User,
) -> CharacterPublic:
    """兼容包装。"""
    return await CharacterService(session).get_mine(user)
