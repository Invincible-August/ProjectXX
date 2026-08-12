"""
GM 调参服务：仅 development 且 GM_ENABLED 时可用（M1 + M2）。
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time_utils import now_utc
from app.db.models.user import User
from app.schemas.common import AppError
from app.services import character_service
from app.services.idle_service import settle_idle
from app.services.play_gate import PlayGate
from app.services.realm_config import get_current_stage, get_game_config, get_major_realm

logger = logging.getLogger(__name__)


class GmService:
    """
    Application service for development-only GM character field overrides.

    Enforces environment and whitelist gates before mutating character state.

    Attributes:
        _session: Request-scoped async SQLAlchemy session.
        _gate: Cross-play precondition gate.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize GM service with a database session.

        Args:
            session: Async SQLAlchemy session bound to the current request.
        """
        self._session = session
        self._gate = PlayGate(session)

    @staticmethod
    def assert_gm_allowed(user: User | None = None) -> None:
        """
        Verify GM operations are permitted in the current environment.

        When a whitelist is configured, ``user.id`` must be listed.

        Args:
            user: Current user; required when whitelist is non-empty.

        Raises:
            AppError: ``40310`` environment disallowed; ``40311`` not on whitelist.
        """
        settings = get_settings()
        if settings.app_env != "development" or not settings.gm_enabled:
            raise AppError(code=40310, message="GM 接口在非开发环境不可用", http_status=403)

        raw = (settings.gm_allowed_user_ids or "").strip()
        if not raw:
            return
        if user is None:
            raise AppError(code=40311, message="GM 白名单已启用但缺少用户上下文", http_status=403)
        allowed: set[int] = set()
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                allowed.add(int(part))
            except ValueError:
                logger.warning("invalid GM_ALLOWED_USER_IDS entry=%s", part)
        if user.id not in allowed:
            raise AppError(code=40311, message="当前账号不在 GM 白名单", http_status=403)

    async def gm_set_character(
        self,
        user: User,
        *,
        major_realm: str | None = None,
        realm_stage: int | None = None,
        cultivation_points: int | None = None,
        realm_progress: int | None = None,
        body_tempering_points: int | None = None,
        crafting_exp: int | None = None,
        breakthrough_grade: str | None = None,
        membership_tier: str | None = None,
        spirit_stones: int | None = None,
        idle_direction: str | None = None,
        status: str | None = None,
        clear_offline_pending: bool | None = None,
        set_stamina: int | None = None,
        trial_puppet_count: int | None = None,
        reset_snapshot_cooldown: bool | None = None,
        force_refresh_snapshot: bool | None = None,
        divine_sense_capacity_bonus: int | None = None,
        array_craft_level: int | None = None,
        force_jindan: bool | None = None,
        grant_craft_materials: bool | None = None,
        grant_test_pet: bool | None = None,
        clear_craft_jobs: bool | None = None,
        clear_divine_sense_backlash: bool | None = None,
        force_shichen: str | None = None,
        force_weather: str | None = None,
        start_tribulation: bool | None = None,
        set_awaiting_ferry: bool | None = None,
        force_ferry_timeout: bool | None = None,
        mark_story_node: str | None = None,
        fate_luck: int | None = None,
        demonic_nature: int | None = None,
        force_yuanying_peak: bool | None = None,
        spirit_root_tags: list[str] | None = None,
        force_tribulation_outcome: str | None = None,
        grant_acceptance_constitution: bool | None = None,
        force_true_immortal: bool | None = None,
        grant_dao_pool: list[str] | None = None,
        set_dao_lord: str | None = None,
        open_dao_challenge_window: bool | None = None,
        open_dao_contest_now: bool | None = None,
        clear_dao_challenge_cooldown: bool | None = None,
        push_world_env: bool | None = None,
        set_dao_qi: int | None = None,
        set_dao_level: int | None = None,
        lock_fate_dao: str | None = None,
        m6_quick_kit: bool | None = None,
    ) -> dict:
        """
        Write one or more character fields after settle and pending resolution.

        Args:
            user: Authenticated GM user.
            major_realm: Optional major realm key override.
            realm_stage: Optional stage number override.
            cultivation_points: Optional cultivation pool override.
            realm_progress: Optional realm progress override.
            body_tempering_points: Optional body pool override.
            crafting_exp: Optional crafting pool override.
            breakthrough_grade: Optional grade id override.
            membership_tier: Optional membership tier override.
            spirit_stones: Optional spirit stone balance override.
            idle_direction: Optional idle direction override.
            status: Optional status override (GM may only set ``normal``).
            clear_offline_pending: When True, clears offline pending JSON.
            set_stamina: Optional stamina value override (M3).
            trial_puppet_count: Optional trial puppet inventory override (M3).
            reset_snapshot_cooldown: When True, clears manual snapshot cooldown (M3).
            force_refresh_snapshot: When True, rebuilds defense snapshot now (M3).

        Returns:
            dict: Updated character envelope.

        Raises:
            AppError: ``40000`` validation; ``40310``/``40311`` GM gate failures.
        """
        self.assert_gm_allowed(user)

        fields = [
            major_realm,
            realm_stage,
            cultivation_points,
            realm_progress,
            body_tempering_points,
            crafting_exp,
            breakthrough_grade,
            membership_tier,
            spirit_stones,
            idle_direction,
            status,
            clear_offline_pending,
            set_stamina,
            trial_puppet_count,
            reset_snapshot_cooldown,
            force_refresh_snapshot,
            divine_sense_capacity_bonus,
            array_craft_level,
            force_jindan,
            grant_craft_materials,
            grant_test_pet,
            clear_craft_jobs,
            clear_divine_sense_backlash,
            force_shichen,
            force_weather,
            start_tribulation,
            set_awaiting_ferry,
            force_ferry_timeout,
            mark_story_node,
            fate_luck,
            demonic_nature,
            force_yuanying_peak,
            spirit_root_tags,
            force_tribulation_outcome,
            grant_acceptance_constitution,
            force_true_immortal,
            grant_dao_pool,
            set_dao_lord,
            open_dao_challenge_window,
            open_dao_contest_now,
            clear_dao_challenge_cooldown,
            push_world_env,
            set_dao_qi,
            set_dao_level,
            lock_fate_dao,
            m6_quick_kit,
        ]
        if all(item is None for item in fields):
            raise AppError(code=40000, message="至少提供一项要修改的字段", http_status=400)

        # M6 一键套装：在写库前展开，使快照刷新等前置分支也能吃到
        if m6_quick_kit:
            force_true_immortal = True
            lock_fate_dao = lock_fate_dao or "dao_flame"
            set_dao_level = set_dao_level if set_dao_level is not None else 3
            set_dao_qi = set_dao_qi if set_dao_qi is not None else 500
            open_dao_challenge_window = True
            clear_dao_challenge_cooldown = True
            force_refresh_snapshot = True
            grant_dao_pool = list(get_game_config().dao.entries.keys())

        character = await self._gate.require_character(user)
        await self._gate.resolve_pending_before_play(character)
        settle_idle(character)

        if clear_offline_pending:
            character.pending_offline_json = None
            character.offline_capped_at = None

        if status is not None:
            if status != "normal":
                raise AppError(code=40000, message="GM 仅允许将 status 设为 normal", http_status=400)
            character.status = "normal"

        if major_realm is not None:
            if get_major_realm(major_realm) is None:
                raise AppError(code=40000, message=f"未知大境界: {major_realm}", http_status=400)
            character.major_realm = major_realm

        if realm_stage is not None:
            target_major = character.major_realm
            stage_cfg = get_current_stage(target_major, realm_stage)
            if stage_cfg is None:
                raise AppError(code=40000, message=f"境界档位不存在: {realm_stage}", http_status=400)
            character.realm_stage = stage_cfg.stage
            character.realm_stage_label = stage_cfg.label

        if major_realm is not None and realm_stage is None:
            stage_cfg = get_current_stage(character.major_realm, character.realm_stage)
            if stage_cfg is not None:
                character.realm_stage_label = stage_cfg.label

        if cultivation_points is not None:
            if cultivation_points < 0:
                raise AppError(code=40000, message="修为池不可为负", http_status=400)
            character.cultivation_points = cultivation_points

        if realm_progress is not None:
            if realm_progress < 0:
                raise AppError(code=40000, message="境界进度不可为负", http_status=400)
            character.realm_progress = realm_progress

        if body_tempering_points is not None:
            if body_tempering_points < 0:
                raise AppError(code=40000, message="淬体度不可为负", http_status=400)
            character.body_tempering_points = body_tempering_points

        if crafting_exp is not None:
            if crafting_exp < 0:
                raise AppError(code=40000, message="制造业经验不可为负", http_status=400)
            character.crafting_exp = crafting_exp

        if breakthrough_grade is not None:
            character.breakthrough_grade = breakthrough_grade
            from app.services.grade_service import get_grade_config

            grade_cfg = get_grade_config(breakthrough_grade)
            if grade_cfg is not None:
                character.divine_ability_slots = grade_cfg.divine_slots

        if membership_tier is not None:
            if membership_tier not in {"free", "tier1", "tier2"}:
                raise AppError(code=40000, message="无效会员档位", http_status=400)
            character.membership_tier = membership_tier

        if spirit_stones is not None:
            if spirit_stones < 0:
                raise AppError(code=40000, message="灵石不可为负", http_status=400)
            character.spirit_stones = spirit_stones

        if idle_direction is not None:
            if idle_direction not in {"none", "spirit", "body", "crafting"}:
                raise AppError(code=40000, message="无效挂机方向", http_status=400)
            character.idle_direction = idle_direction

        # --- M3 战斗成型调试字段 ---
        if set_stamina is not None:
            if set_stamina < 0:
                raise AppError(code=40000, message="体力不可为负", http_status=400)
            character.stamina = set_stamina
            # 同步推进锚点，避免旧锚点叠加惰性恢复
            character.stamina_updated_at = now_utc()

        if trial_puppet_count is not None:
            if trial_puppet_count < 0:
                raise AppError(code=40000, message="傀儡数不可为负", http_status=400)
            character.trial_puppet_count = trial_puppet_count

        if reset_snapshot_cooldown or force_refresh_snapshot:
            from app.services.snapshot_service import SnapshotService

            snapshots = SnapshotService(self._session)
            row = await snapshots.ensure_snapshot(character)
            if reset_snapshot_cooldown:
                row.last_manual_update_at = None
            if force_refresh_snapshot:
                import json as _json

                payload = await snapshots.build_payload(character)
                row.payload_json = _json.dumps(payload, ensure_ascii=False)
                row.content_hash = str(payload["content_hash"])
                row.updated_at = now_utc()

        # --- M4 GM 便利操作 ---
        if force_jindan:
            character.major_realm = "jindan"
            character.realm_stage = 1
            character.realm_stage_label = "early"

        if divine_sense_capacity_bonus is not None:
            character.divine_sense_capacity_bonus = divine_sense_capacity_bonus

        if array_craft_level is not None:
            character.array_craft_level = array_craft_level

        if clear_divine_sense_backlash:
            character.divine_sense_backlash = False

        if clear_craft_jobs:
            from app.db.models.craft_job import CraftJob
            from sqlalchemy import delete

            await self._session.execute(
                delete(CraftJob).where(CraftJob.character_id == character.id),
            )

        if grant_craft_materials and get_settings().m4_gm_grant_materials:
            from app.services.inventory_service import InventoryService

            inv = InventoryService(self._session)
            for item_id, qty in (
                ("herb_spirit_grass", 20),
                ("ore_iron_raw", 20),
                ("talisman_paper", 20),
                ("array_fragment", 5),
                ("wood_spirit", 20),
                ("pet_food_basic", 5),
                ("egg_fox_trial", 3),
                ("egg_crane_qing", 1),
                ("pet_pill_atk_minor", 10),
                ("pet_pill_hp_minor", 10),
                ("pet_pill_speed_minor", 5),
                ("pet_lure_grass", 20),
                ("pet_spirit_bag", 1),
            ):
                if item_id.startswith("egg_"):
                    item_type = "pet_egg"
                elif item_id.startswith("pet_pill_"):
                    item_type = "consumable"
                else:
                    item_type = "material"
                await inv.add_item(
                    character.id,
                    item_type=item_type,
                    item_id=item_id,
                    quantity=qty,
                )

        if grant_test_pet:
            from app.services.pet_service import PetService

            pet_svc = PetService(self._session)
            if await pet_svc.count_pets(character.id) < get_game_config().pets.hold_cap:
                await pet_svc.capture_test(character, species_id="test_pet_fox")

        # --- M5 环境与轮回 ---
        if force_shichen is not None:
            from app.services.calendar_service import set_gm_force_shichen

            set_gm_force_shichen(force_shichen)

        if force_weather is not None:
            from app.services.weather_service import set_gm_force_weather

            set_gm_force_weather(force_weather)

        if force_yuanying_peak:
            character.major_realm = "yuanying"
            character.realm_stage = 4
            character.realm_stage_label = "perfection"
            stage_cfg = get_current_stage("yuanying", 4)
            if stage_cfg is not None:
                character.realm_progress = stage_cfg.cultivation_required

        if fate_luck is not None:
            character.fate_luck = int(fate_luck)
        if demonic_nature is not None:
            character.demonic_nature = int(demonic_nature)

        if spirit_root_tags is not None:
            import json

            # 仅保留非空字符串标签，供环境乘区 / IdlePanel 联调
            cleaned = [str(t).strip() for t in spirit_root_tags if str(t).strip()]
            character.spirit_root_tags_json = json.dumps(cleaned, ensure_ascii=False)

        if mark_story_node is not None:
            from app.domain.reincarnation_rules import (
                dump_story_flags,
                mark_story_node as mark_node,
                parse_story_flags,
            )

            flags = parse_story_flags(character.story_flags_json)
            mark_node(flags, mark_story_node)
            character.story_flags_json = dump_story_flags(flags)

        if set_awaiting_ferry:
            from app.services.ferry_service import FerryService

            await FerryService(self._session).enter_awaiting_ferry(character)

        if start_tribulation:
            from app.services.tribulation_service import TribulationService

            await TribulationService(self._session).start_prep(user, force=True)

        if force_tribulation_outcome:
            from app.services.tribulation_service import TribulationService

            await TribulationService(self._session).gm_force_outcome(
                user,
                force_tribulation_outcome,
            )
            # outcome 可能已改 character；刷新后再继续其它字段
            await self._session.refresh(character)

        if grant_acceptance_constitution:
            from app.services.constitution_service import ConstitutionService

            await ConstitutionService(self._session).grant_acceptance_constitution_kit(
                character,
                auto_equip=True,
            )

        # --- M6 大道 / 道主 ---
        if force_true_immortal:
            from app.services.dao_service import DaoService

            await DaoService(self._session).gm_force_true_immortal(character)

        if lock_fate_dao:
            from app.services.dao_service import DaoService

            await DaoService(self._session).gm_lock_fate_dao(
                character,
                str(lock_fate_dao).strip(),
            )

        if grant_dao_pool:
            from app.services.dao_service import DaoService

            await DaoService(self._session).gm_grant_pool(character, list(grant_dao_pool))

        if set_dao_qi is not None or set_dao_level is not None:
            from app.services.dao_service import DaoService

            await DaoService(self._session).gm_set_resources(
                character,
                dao_qi=set_dao_qi,
                dao_level=set_dao_level,
            )

        if set_dao_lord is not None:
            from app.services.dao_lord_service import DaoLordService

            dao_id = set_dao_lord.strip() if set_dao_lord else None
            await DaoLordService(self._session).gm_set_lord(
                character,
                dao_id if dao_id else None,
            )

        if open_dao_challenge_window:
            # 进程级覆盖：写 settings 缓存字段不可变；用模块标志
            import app.services.dao_lord_service as _lord_mod

            _lord_mod._GM_FORCE_WINDOW = True  # type: ignore[attr-defined]

        if open_dao_contest_now:
            from app.services.dao_contest_service import DaoContestService

            await DaoContestService(self._session).force_start(note="gm")

        if clear_dao_challenge_cooldown:
            from app.services.dao_service import DaoService

            row = await DaoService(self._session)._get_or_create_row(character.id)
            row.challenge_cooldown_until = None

        if push_world_env:
            from app.domain.ws_protocol import TYPE_WORLD_ENV
            from app.services.calendar_service import CalendarService
            from app.services.weather_service import WeatherService
            from app.services.ws_hub_service import get_ws_hub

            cal = CalendarService().get_snapshot()
            wx = WeatherService().get_snapshot()
            await get_ws_hub().broadcast_world(
                TYPE_WORLD_ENV,
                {
                    "shichen": cal.get("shichen_id"),
                    "shichen_label": cal.get("label"),
                    "weather": wx.get("weather_id"),
                    "weather_label": wx.get("label"),
                },
            )

        if force_ferry_timeout:
            from datetime import timedelta

            from app.services.ferry_service import FerryService

            if character.status != "awaiting_ferry":
                await FerryService(self._session).enter_awaiting_ferry(character)
            character.ferry_deadline_at = now_utc() - timedelta(seconds=1)
            await FerryService(self._session).check_timeout_and_force(character)

        character.updated_at = now_utc()
        await self._session.flush()
        await self._session.refresh(character)

        logger.warning(
            "gm_set_character user_id=%s character_id=%s realm_progress=%s",
            user.id,
            character.id,
            character.realm_progress,
        )

        public = await character_service.get_my_character(self._session, user)
        return {"character": character_service.character_public_to_dict(public)}


# ---------------------------------------------------------------------------
# Module-level wrappers (backward-compatible for tests and legacy imports)
# ---------------------------------------------------------------------------


def assert_gm_allowed(user: User | None = None) -> None:
    """Module wrapper delegating to ``GmService.assert_gm_allowed``."""
    GmService.assert_gm_allowed(user)


async def gm_set_character(
    session: AsyncSession,
    user: User,
    *,
    major_realm: str | None = None,
    realm_stage: int | None = None,
    cultivation_points: int | None = None,
    realm_progress: int | None = None,
    body_tempering_points: int | None = None,
    crafting_exp: int | None = None,
    breakthrough_grade: str | None = None,
    membership_tier: str | None = None,
    spirit_stones: int | None = None,
    idle_direction: str | None = None,
    status: str | None = None,
    clear_offline_pending: bool | None = None,
    set_stamina: int | None = None,
    trial_puppet_count: int | None = None,
    reset_snapshot_cooldown: bool | None = None,
    force_refresh_snapshot: bool | None = None,
) -> dict:
    """Module wrapper delegating to ``GmService.gm_set_character``."""
    return await GmService(session).gm_set_character(
        user,
        major_realm=major_realm,
        realm_stage=realm_stage,
        cultivation_points=cultivation_points,
        realm_progress=realm_progress,
        body_tempering_points=body_tempering_points,
        crafting_exp=crafting_exp,
        breakthrough_grade=breakthrough_grade,
        membership_tier=membership_tier,
        spirit_stones=spirit_stones,
        idle_direction=idle_direction,
        status=status,
        clear_offline_pending=clear_offline_pending,
        set_stamina=set_stamina,
        trial_puppet_count=trial_puppet_count,
        reset_snapshot_cooldown=reset_snapshot_cooldown,
        force_refresh_snapshot=force_refresh_snapshot,
    )
