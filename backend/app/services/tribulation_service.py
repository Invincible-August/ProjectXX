"""
渡劫应用服务：准备格 → 开渡 → 批次结算 → 成/败/陨落（M5 E4）。
"""

from __future__ import annotations

import json
import logging
import random
import secrets
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import now_utc, to_utc_iso
from app.db.models.character import Character
from app.db.models.tribulation_session import TribulationSession
from app.db.models.user import User
from app.domain.display_labels import (
    label_zh_or_unknown,
    tribulation_phase_label_zh,
)
from app.domain.env_modifiers import combine_env_multipliers, lookup_modifier
from app.domain.reincarnation_rules import dump_story_flags, parse_story_flags
from app.domain.tribulation_prep import (
    normalize_prep_slots,
    next_consumable_mitigation,
    prep_exhausted,
    validate_prep_slots,
)
from app.domain.tribulation_rules import (
    apply_axis_b_mitigation,
    compress_batch_events,
    compute_strike_nominal,
    demonic_nature_band,
    fate_luck_band,
    lower_power_tier,
    map_grade_to_tribulation,
    map_layer_tribulation,
    raise_power_tier,
    try_guardian_proc,
)
from app.schemas.common import AppError
from app.services.calendar_service import CalendarService
from app.services.ferry_service import FerryService
from app.services.grade_service import GradeService, grade_name_map
from app.services.m5_features import is_tribulation_enabled, require_tribulation_enabled
from app.services.play_gate import PlayGate
from app.services.realm_config import (
    build_realm_display,
    get_current_stage,
    get_game_config,
    get_major_realm,
    is_perfection_stage,
)
from app.services.weather_service import WeatherService

logger = logging.getLogger(__name__)

_ACTIVE_PHASES = frozenset({"preparing", "committed", "running"})


def needs_tribulation_for_advance(
    character: Character,
    *,
    advance_type: str,
    target_major: str | None,
) -> bool:
    """
    Decide whether this breakthrough must enter tribulation instead of advancing.

    Rules (D5 · 2026-08-06 修订)：
    - **小境界**（同大境内层/期进阶，``advance_type=layer``）**永不渡劫**。
    - **首次跨境雷劫**：元婴大圆满 → 化神。
    - 首次渡劫成功后（``first_tribulation_done``）：之后每一次 **跨大境界** 均渡劫。
    - 锻体～元婴（含跨入元婴）无雷劫。

    Args:
        character: Character entity.
        advance_type: ``layer``（小境界）或 ``major``（跨大境界）。
        target_major: Next major key when cross-major.

    Returns:
        bool: True when attempt should divert to start-prep.
    """
    if not is_tribulation_enabled():
        return False
    # 小境界突破：直接走 BreakthroughService 升层/期，不进渡劫
    if advance_type != "major":
        return False
    if not target_major:
        return False

    cfg = get_game_config().tribulation
    flags = parse_story_flags(character.story_flags_json)
    first_done = bool(flags.get("first_tribulation_done"))

    # 首次门槛：元婴大圆满跨境化神
    require_major = cfg.require_from_major
    at_require_peak = (
        character.major_realm == require_major
        and is_perfection_stage(character.major_realm, character.realm_stage)
    )
    if at_require_peak:
        return True

    # 首次渡劫完成后：仅后续「跨大境界」再渡劫（不含小境界）
    if cfg.always_after_first and first_done:
        return True

    return False


class TribulationService:
    """
    Application service for tribulation prep, begin, and batch resolve.

    Attributes:
        _session: Async SQLAlchemy session.
        _gate: Play gate.
        _calendar: Calendar service.
        _weather: Weather service.
        _grades: Grade roller.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: Request-scoped async session.
        """
        self._session = session
        self._gate = PlayGate(session)
        self._calendar = CalendarService()
        self._weather = WeatherService()
        self._grades = GradeService(session)

    def _rng(self, seed: int | None = None) -> random.Random:
        """Build RNG; optional seed for reproducibility."""
        if seed is not None:
            return random.Random(int(seed))
        return random.Random()

    async def _active_session(
        self,
        character_id: int,
    ) -> TribulationSession | None:
        """Load the latest active tribulation session for character."""
        result = await self._session.execute(
            select(TribulationSession)
            .where(
                TribulationSession.character_id == character_id,
                TribulationSession.phase.in_(tuple(_ACTIVE_PHASES)),
            )
            .order_by(TribulationSession.id.desc())
            .limit(1),
        )
        return result.scalar_one_or_none()

    async def _character_public_dict(self, character: Character) -> dict[str, Any]:
        """Enrich character for mutation envelopes (陨落→待引渡须同步前端)."""
        from app.services.character_service import CharacterService, character_public_to_dict

        # flush 后 updated_at 等列会过期；异步会话禁止隐式懒加载（MissingGreenlet）
        await self._session.refresh(character)
        public = await CharacterService(self._session).enrich_public(character)
        return character_public_to_dict(public)

    def _session_to_dict(self, row: TribulationSession) -> dict[str, Any]:
        """Serialize session for API (skip unloaded timestamp attrs after flush)."""
        from sqlalchemy import inspect as sa_inspect

        prep = []
        if row.prep_slots_json:
            try:
                prep = json.loads(row.prep_slots_json)
            except json.JSONDecodeError:
                prep = []
        bundle = get_game_config()
        cfg = bundle.tribulation
        power = cfg.power_tiers.get(row.power_tier)
        count = cfg.count_tiers.get(row.count_tier)
        # 时辰/天气中文名（§0.0.2：禁止把英文 id 塞进 *_label）
        shichen_label = label_zh_or_unknown(
            row.locked_shichen,
            bundle.calendar.labels,
        )
        weather_label = label_zh_or_unknown(
            row.locked_weather,
            bundle.weather.labels,
        )
        state = sa_inspect(row)
        unloaded = state.unloaded

        def _iso(attr: str) -> str | None:
            if attr in unloaded:
                return None
            value = getattr(row, attr, None)
            return to_utc_iso(value) if value is not None else None

        # 准备格对外字段：补 slot / item_uid / item_name，供前端装备栏展示
        prep_public: list[dict[str, Any]] = []
        for index, raw_slot in enumerate(prep if isinstance(prep, list) else []):
            if not isinstance(raw_slot, dict):
                prep_public.append({"slot": index, "kind": "empty"})
                continue
            meta = raw_slot.get("meta") if isinstance(raw_slot.get("meta"), dict) else {}
            prep_public.append(
                {
                    **raw_slot,
                    "slot": index,
                    "item_uid": meta.get("item_uid") or raw_slot.get("item_id"),
                    "item_name": meta.get("item_name"),
                    "inefficient": raw_slot.get("kind") == "artifact"
                    or bool(meta.get("tribulation_inefficient")),
                },
            )

        return {
            "id": row.id,
            "phase": row.phase,
            "phase_label_zh": tribulation_phase_label_zh(row.phase),
            "target_major": row.target_major,
            "target_stage": row.target_stage,
            "target_stage_label": row.target_stage_label,
            "target_display": build_realm_display(
                row.target_major,
                row.target_stage_label,
            ),
            # 前端契约别名（显性字段，避免 NaN/空白）
            "target_label": build_realm_display(
                row.target_major,
                row.target_stage_label,
            ),
            "is_cross_major": row.is_cross_major,
            "projected_grade": row.projected_grade,
            "projected_grade_name": (
                grade_name_map().get(row.projected_grade)
                or label_zh_or_unknown(row.projected_grade)
                if row.projected_grade
                else None
            ),
            "power_tier": row.power_tier,
            "power_tier_label": power.label if power else label_zh_or_unknown(row.power_tier),
            "power_label": power.label if power else label_zh_or_unknown(row.power_tier),
            "count_tier": row.count_tier,
            "count_tier_label": count.label if count else label_zh_or_unknown(row.count_tier),
            "count_label": count.label if count else label_zh_or_unknown(row.count_tier),
            "strike_total": row.strike_total,
            "strike_done": row.strike_done,
            "locked_shichen": row.locked_shichen,
            "locked_shichen_label": shichen_label,
            "locked_weather": row.locked_weather,
            "locked_weather_label": weather_label,
            "display_weather": (
                "tribulation_cloud" if row.phase == "running" else row.locked_weather
            ),
            "display_weather_label": (
                "劫云" if row.phase == "running" else weather_label
            ),
            "in_cloud_double": row.in_cloud_double,
            "cloud_radius": row.cloud_radius,
            "prep_slots": prep_public,
            "prep_cursor": row.prep_cursor,
            "formation_id": row.formation_id,
            "veil_chosen": row.veil_chosen,
            "veil_selected": row.veil_chosen,
            "veil_resolved": row.veil_resolved,
            # 会话表无独立 outcome 列；成功与否以 veil-check 响应的 veil_outcome 为准
            "veil_result": None,
            "hp_current": row.hp_current,
            "hp_max": row.hp_max,
            "guardian_used": row.guardian_used,
            "created_at": _iso("created_at"),
            "updated_at": _iso("updated_at"),
        }

    async def get_me(self, user: User) -> dict[str, Any]:
        """
        Return current tribulation session or null.

        Args:
            user: Authenticated user.

        Returns:
            dict: ``{ session: ... | null }``.
        """
        character = await self._gate.require_character(user)
        row = await self._active_session(character.id)
        return {"session": self._session_to_dict(row) if row else None}

    async def start_prep(
        self,
        user: User,
        now: datetime | None = None,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Create a preparing tribulation session from breakthrough divert / GM.

        Args:
            user: Authenticated user.
            now: Optional frozen time.
            force: GM bypass of needs_tribulation check.

        Returns:
            dict: Session payload.

        Raises:
            AppError: Mutex / config errors ``40060``–``40073``.
        """
        require_tribulation_enabled()
        character, _ = await self._gate.prepare_for_play(user, now=now, settle=True)
        current = now_utc(now)

        if character.status in ("awaiting_ferry", "reincarnating"):
            raise AppError(code=40060, message="当前状态不可进入渡劫", http_status=409)
        if character.status == "tribulation":
            existing = await self._active_session(character.id)
            if existing is not None:
                raise AppError(code=40063, message="已在渡劫流程中", http_status=409)

        from app.domain.activity_mutex import Activity

        # 须先停止修炼；工坊进行中也不允许开渡（与积极玩法一致）
        await self._gate.assert_activity(character, Activity.START_TRIBULATION)

        major = get_major_realm(character.major_realm)
        if major is None:
            raise AppError(code=40026, message="当前境界配置缺失", http_status=400)

        is_cross = is_perfection_stage(character.major_realm, character.realm_stage)
        if is_cross:
            next_key = major.next_major
            if not next_key:
                raise AppError(code=40026, message="已达境界开放上限", http_status=400)
            next_major = get_major_realm(next_key)
            if next_major is None:
                raise AppError(code=40026, message="下一境界尚未配置", http_status=400)
            first = next_major.stages[0]
            target_major = next_key
            target_stage = first.stage
            target_label = first.label
            advance_type = "major"
        else:
            next_stage_num = character.realm_stage + 1
            next_stage = major.stage_by_number(next_stage_num)
            if next_stage is None:
                raise AppError(code=40026, message="下一层期未配置", http_status=400)
            target_major = character.major_realm
            target_stage = next_stage.stage
            target_label = next_stage.label
            advance_type = "layer"

        if not force and not needs_tribulation_for_advance(
            character,
            advance_type=advance_type,
            target_major=target_major if is_cross else None,
        ):
            raise AppError(
                code=40073,
                message="当前突破无需渡劫，请走常规突破",
                http_status=400,
            )

        stage = get_current_stage(character.major_realm, character.realm_stage)
        if stage is None:
            raise AppError(code=40026, message="当前境界配置缺失", http_status=400)
        if int(character.realm_progress) < stage.cultivation_required and not force:
            raise AppError(code=40023, message="境界进度不足，无法渡劫", http_status=400)

        cfg = get_game_config().tribulation
        cal = self._calendar.get_snapshot(now=current)
        weather_id = self._weather.get_underlying_weather_id(now=current)
        in_cloud = self._weather.is_region_under_cloud(now=current)

        projected_grade: str | None = None
        if is_cross:
            # 预估品阶：与 M2 权重一致（占位）
            grade_cfg = await self._grades.roll_breakthrough_grade(character)
            projected_grade = grade_cfg.grade_id
            dims = map_grade_to_tribulation(
                projected_grade,
                cfg.grade_to_tribulation,
            )
        else:
            dims = map_layer_tribulation(target_major, cfg.layer_mapping)

        power = cfg.power_tiers[dims.power_tier]
        count = cfg.count_tiers[dims.count_tier]
        cloud_radius = power.cloud_radius
        if dims.count_tier == "myriad":
            cloud_radius = min(4, cloud_radius + cfg.cloud_radius_bonus_on_myriad)

        # 渡劫专用 HP：取当前境界 base_hp
        hp_max = float(stage.base_hp)
        seed = secrets.randbits(63)
        empty_prep = [
            {"kind": "empty"} for _ in range(cfg.prep_slots_default)
        ]

        row = TribulationSession(
            character_id=character.id,
            target_major=target_major,
            target_stage=target_stage,
            target_stage_label=target_label,
            is_cross_major=is_cross,
            projected_grade=projected_grade,
            power_tier=dims.power_tier,
            count_tier=dims.count_tier,
            strike_total=count.strikes,
            strike_done=0,
            locked_shichen=str(cal["shichen_id"]),
            locked_weather=weather_id,
            in_cloud_double=in_cloud,
            cloud_radius=cloud_radius,
            prep_slots_json=json.dumps(empty_prep, ensure_ascii=False),
            prep_cursor=0,
            hp_current=hp_max,
            hp_max=hp_max,
            seed=seed,
            phase="preparing",
        )
        self._session.add(row)
        character.status = "tribulation"
        # 进入渡劫时强制停修炼，避免零产却仍显示修炼中
        character.idle_direction = "none"
        character.updated_at = current
        await self._session.flush()
        await self._session.refresh(row)
        logger.info(
            "tribulation start-prep character_id=%s power=%s count=%s grade=%s",
            character.id,
            dims.power_tier,
            dims.count_tier,
            projected_grade,
        )
        return {"session": self._session_to_dict(row)}

    def _map_inventory_type_to_prep_kind(self, item_type: str) -> str:
        """
        Map backpack ``item_type`` to tribulation prep ``kind``.

        Args:
            item_type: Inventory item_type string.

        Returns:
            str: Prep kind (pill / artifact / guard_artifact / …).
        """
        normalized = (item_type or "").lower()
        if normalized in {"pill", "dan", "medicine"}:
            return "pill"
        if normalized in {"guard_artifact", "guard", "talisman"}:
            return "guard_artifact"
        if normalized in {"veil"}:
            return "veil"
        if normalized in {"artifact", "weapon", "equipment", "fabao"}:
            return "artifact"
        # 默认按普通法宝抵劫（效率差），避免未知类型直接拒绝冒烟路径
        return "artifact"

    async def _resolve_client_prep_slots(
        self,
        character: Character,
        slots: list[dict[str, Any]] | None,
        *,
        slot_count: int,
    ) -> list[dict[str, Any]]:
        """
        Resolve frontend prep payload (``item_uid``) into server PrepSlot dicts.

        Args:
            character: Owner character.
            slots: Client slots (may use ``item_uid``).
            slot_count: Configured prep slot count.

        Returns:
            list[dict]: Length ``slot_count`` payloads for ``normalize_prep_slots``.

        Raises:
            AppError: Item missing from inventory or duplicate over-quantity.
        """
        from app.db.models.inventory_item import InventoryItem

        inv_cfg = get_game_config().inventory
        raw_list = list(slots or [])
        resolved: list[dict[str, Any]] = []
        # 同 uid 占用次数，校验数量足够
        uid_counts: dict[str, int] = {}

        for index in range(slot_count):
            if index >= len(raw_list) or not raw_list[index]:
                resolved.append({"kind": "empty"})
                continue
            entry = raw_list[index]
            if not isinstance(entry, dict):
                resolved.append({"kind": "empty"})
                continue

            item_uid = entry.get("item_uid") or entry.get("item_id")
            kind_hint = entry.get("kind")
            if not item_uid and (not kind_hint or kind_hint == "empty"):
                resolved.append({"kind": "empty"})
                continue

            # 已是服务端格式且无 uid：原样保留（测试/旧数据）
            if kind_hint and kind_hint != "empty" and not entry.get("item_uid"):
                resolved.append(dict(entry))
                continue

            uid = str(item_uid)
            result = await self._session.execute(
                select(InventoryItem)
                .where(
                    InventoryItem.character_id == character.id,
                    InventoryItem.item_uid == uid,
                )
                .limit(1),
            )
            inv = result.scalar_one_or_none()
            if inv is None:
                raise AppError(
                    code=40071,
                    message=f"准备格道具不在背包中（uid={uid}）",
                    http_status=400,
                )

            uid_counts[uid] = uid_counts.get(uid, 0) + 1
            if uid_counts[uid] > int(inv.quantity):
                raise AppError(
                    code=40071,
                    message=f"准备格同一道具数量不足：需要 {uid_counts[uid]}，持有 {inv.quantity}",
                    http_status=400,
                )

            kind = self._map_inventory_type_to_prep_kind(str(inv.item_type))
            defn = inv_cfg.items.get(inv.item_id)
            name = defn.name if defn else inv.item_id
            # 护劫类默认减伤；普通法宝低减伤（与 domain 0.2× 叠加前的基数）
            default_mit = 0.15 if kind == "artifact" else 0.5
            mitigation = float(entry.get("mitigation", default_mit))
            meta: dict[str, Any] = {
                "item_uid": inv.item_uid,
                "item_name": name,
                "item_type": inv.item_type,
            }
            if inv.meta_json:
                try:
                    extra = json.loads(inv.meta_json)
                    if isinstance(extra, dict) and extra.get("tribulation_inefficient"):
                        meta["tribulation_inefficient"] = True
                except json.JSONDecodeError:
                    pass
            resolved.append(
                {
                    "kind": kind,
                    "item_id": inv.item_id,
                    "mitigation": mitigation,
                    "meta": meta,
                },
            )
        return resolved

    async def _consume_prep_inventory(
        self,
        character: Character,
        prep_raw: list[Any],
    ) -> None:
        """
        Permanently remove prep-slot items from inventory when beginning tribulation.

        Args:
            character: Owner character.
            prep_raw: Parsed ``prep_slots_json`` list.

        Raises:
            AppError: Item vanished between commit and begin.
        """
        from app.services.inventory_service import InventoryService

        inventory = InventoryService(self._session)
        for raw in prep_raw:
            if not isinstance(raw, dict):
                continue
            kind = str(raw.get("kind") or "empty")
            if kind in {"empty", "formation_ref"}:
                continue
            meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
            item_uid = meta.get("item_uid") or raw.get("item_id")
            if not item_uid:
                continue
            # use_item：无 use_effect 时仅扣数量；有则一并生效（护劫丹等）
            await inventory.use_item(character, item_uid=str(item_uid), quantity=1)

    async def save_prep(
        self,
        user: User,
        *,
        slots: list[dict[str, Any]] | None = None,
        formation_id: str | None = None,
        veil_chosen: bool | None = None,
    ) -> dict[str, Any]:
        """
        Save prep slots / formation / veil choice while preparing.

        Args:
            user: Authenticated user.
            slots: Prep slot payloads (``item_uid`` from frontend).
            formation_id: Optional formation id.
            veil_chosen: Whether to attempt veil on begin/veil-check.

        Returns:
            dict: Updated session.
        """
        require_tribulation_enabled()
        character = await self._gate.require_character(user)
        row = await self._active_session(character.id)
        if row is None or row.phase != "preparing":
            raise AppError(code=40073, message="当前阶段不可编辑准备格", http_status=409)

        cfg = get_game_config().tribulation
        resolved = await self._resolve_client_prep_slots(
            character,
            slots,
            slot_count=cfg.prep_slots_default,
        )
        normalized = normalize_prep_slots(resolved, slot_count=cfg.prep_slots_default)
        try:
            validate_prep_slots(normalized, max_slots=cfg.prep_slots_default)
        except ValueError as exc:
            raise AppError(code=40071, message=str(exc), http_status=400) from exc

        row.prep_slots_json = json.dumps(
            [s.to_dict() for s in normalized],
            ensure_ascii=False,
        )
        if formation_id is not None:
            row.formation_id = formation_id
        if veil_chosen is not None:
            row.veil_chosen = bool(veil_chosen)
        await self._session.flush()
        return {"session": self._session_to_dict(row)}

    async def commit_prep(self, user: User) -> dict[str, Any]:
        """Lock prep → phase committed. Empty prep allowed for M5 smoke."""
        require_tribulation_enabled()
        character = await self._gate.require_character(user)
        row = await self._active_session(character.id)
        if row is None or row.phase != "preparing":
            raise AppError(code=40073, message="当前阶段不可确认准备", http_status=409)
        row.phase = "committed"
        await self._session.flush()
        await self._session.refresh(row)
        logger.info("tribulation commit-prep session_id=%s", row.id)
        return {"session": self._session_to_dict(row)}

    async def veil_check(self, user: User) -> dict[str, Any]:
        """
        Resolve optional 遮天检定 (may lower/raise power tier).

        Args:
            user: Authenticated user.

        Returns:
            dict: Session + veil outcome.
        """
        require_tribulation_enabled()
        character = await self._gate.require_character(user)
        row = await self._active_session(character.id)
        if row is None or row.phase not in ("committed", "preparing"):
            raise AppError(code=40073, message="当前阶段不可遮天检定", http_status=409)
        if row.veil_resolved:
            raise AppError(code=40072, message="遮天检定已提交", http_status=409)
        if not row.veil_chosen:
            raise AppError(code=40071, message="未选择遮天道具", http_status=400)

        cfg = get_game_config().tribulation
        veil = cfg.veil
        rng = self._rng(int(row.seed) + 17)
        from app.services.dice_service import DiceService

        success = DiceService.chance(float(veil.get("success_chance", 0.4)), rng=rng)
        fail_effect: dict[str, Any] | None = None
        if success:
            row.power_tier = lower_power_tier(row.power_tier)
            outcome = "success"
        else:
            # M5-D10：加权失败副作用表；空表回落旧布尔键
            fail_effect = self._resolve_veil_fail_effect(veil, rng=rng)
            if fail_effect.get("raise_power_tier"):
                row.power_tier = raise_power_tier(row.power_tier)
            if fail_effect.get("force_cloud_double"):
                row.in_cloud_double = True
            hp_ratio = float(fail_effect.get("hp_damage_ratio") or 0.0)
            if hp_ratio > 0:
                # 重伤：按 hp_max 扣气血，不低于 1（未开渡时仍可预伤）
                damage = float(row.hp_max) * hp_ratio
                row.hp_current = max(1.0, float(row.hp_current) - damage)
            outcome = "fail"
        row.veil_resolved = True
        # 遮天后按新档刷新 cloud_radius / strike 不变
        power = cfg.power_tiers.get(row.power_tier)
        if power:
            row.cloud_radius = power.cloud_radius
        await self._session.flush()
        payload: dict[str, Any] = {
            "veil_outcome": outcome,
            "session": self._session_to_dict(row),
        }
        if fail_effect is not None:
            payload["veil_fail_effect"] = fail_effect
        return payload

    @staticmethod
    def _resolve_veil_fail_effect(
        veil: dict[str, Any],
        *,
        rng: random.Random,
    ) -> dict[str, Any]:
        """
        Pick a veil failure side-effect from the weighted YAML table.

        Args:
            veil: ``tribulation.yaml`` veil section.
            rng: Seeded RNG for reproducible tests.

        Returns:
            dict: Chosen effect fields (id/label/flags/hp_damage_ratio).
        """
        from app.domain.dice_rules import weighted_pick

        raw_effects = veil.get("fail_effects") or []
        by_id: dict[str, dict[str, Any]] = {}
        weights: dict[str, float] = {}
        if isinstance(raw_effects, list):
            for item in raw_effects:
                if not isinstance(item, dict):
                    continue
                effect_id = str(item.get("id") or "").strip()
                if not effect_id:
                    continue
                weight = float(item.get("weight") or 0.0)
                if weight <= 0:
                    continue
                by_id[effect_id] = item
                weights[effect_id] = weight

        chosen_id = weighted_pick(weights, rng=rng) if weights else None
        if chosen_id and chosen_id in by_id:
            item = by_id[chosen_id]
            return {
                "id": chosen_id,
                "label": str(item.get("label") or chosen_id),
                "raise_power_tier": bool(item.get("raise_power_tier", False)),
                "force_cloud_double": bool(item.get("force_cloud_double", False)),
                "hp_damage_ratio": float(item.get("hp_damage_ratio") or 0.0),
            }

        # 回落：旧布尔键同时生效
        return {
            "id": "legacy_default",
            "label": "遮天失败（兼容惩罚）",
            "raise_power_tier": bool(veil.get("fail_raise_power_tier", True)),
            "force_cloud_double": bool(veil.get("fail_force_cloud_double", True)),
            "hp_damage_ratio": 0.0,
        }

    async def begin(self, user: User, now: datetime | None = None) -> dict[str, Any]:
        """
        Begin tribulation: require committed, set cloud, phase=running.

        Args:
            user: Authenticated user.
            now: Optional frozen time.

        Returns:
            dict: Running session.
        """
        require_tribulation_enabled()
        character = await self._gate.require_character(user)
        row = await self._active_session(character.id)
        if row is None:
            raise AppError(code=40073, message="无进行中的渡劫会话", http_status=404)
        if row.phase == "preparing":
            raise AppError(code=40070, message="准备格未确认不可开渡", http_status=400)
        if row.phase != "committed":
            raise AppError(code=40073, message="当前阶段不可开渡", http_status=409)

        # 开渡即永久消耗准备格道具（确认后不可取回）
        try:
            prep_raw = json.loads(row.prep_slots_json or "[]")
        except json.JSONDecodeError:
            prep_raw = []
        if isinstance(prep_raw, list):
            await self._consume_prep_inventory(character, prep_raw)

        cfg = get_game_config().tribulation
        cal_cfg = get_game_config().calendar
        weather_cfg = get_game_config().weather

        # 轴 A：阵法占位 × 气运 × 魔性（结算用锁前天气压力）
        fate_mult = cfg.fate_luck_power_mult.get(
            fate_luck_band(int(character.fate_luck)),
            1.0,
        )
        demo_mult = cfg.demonic_nature_power_mult.get(
            demonic_nature_band(int(character.demonic_nature)),
            1.0,
        )
        formation_mult = 1.0
        axis_a = float(fate_mult) * float(demo_mult) * float(formation_mult)

        shichen_pressure = lookup_modifier(
            (get_game_config().calendar.modifiers.get("breakthrough_success") or {}),
            row.locked_shichen,
        )
        # 渡劫压力用 weather tribulation_pressure
        weather_pressure = lookup_modifier(
            (weather_cfg.modifiers.get("tribulation_pressure") or {}),
            row.locked_weather,
        )
        env_mult = combine_env_multipliers(
            base=1.0,
            shichen_mult=shichen_pressure,
            weather_mult=weather_pressure,
            clamp_min=min(cal_cfg.clamp_min, weather_cfg.clamp_min),
            clamp_max=max(cal_cfg.clamp_max, weather_cfg.clamp_max),
        )

        row.axis_a_snapshot = json.dumps(
            {
                "axis_a_mult": axis_a,
                "env_mult": env_mult,
                "fate_mult": fate_mult,
                "demonic_mult": demo_mult,
            },
            ensure_ascii=False,
        )
        row.phase = "running"
        self._weather.begin_cloud(
            region_id="default",
            source_character_id=character.id,
            cloud_radius=row.cloud_radius,
        )
        await self._session.flush()
        logger.info("tribulation begin session_id=%s", row.id)
        return {"session": self._session_to_dict(row)}

    def _load_axis(self, row: TribulationSession) -> tuple[float, float]:
        """Load axis_a_mult and env_mult from snapshot."""
        if not row.axis_a_snapshot:
            return 1.0, 1.0
        try:
            data = json.loads(row.axis_a_snapshot)
        except json.JSONDecodeError:
            return 1.0, 1.0
        return float(data.get("axis_a_mult", 1.0)), float(data.get("env_mult", 1.0))

    async def resolve_batch(
        self,
        user: User,
        *,
        batch_size: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Resolve the next batch of strikes.

        Args:
            user: Authenticated user.
            batch_size: Override strikes in this batch.
            now: Optional frozen time.

        Returns:
            dict: Events + session + terminal outcome if finished.
        """
        require_tribulation_enabled()
        character = await self._gate.require_character(user)
        row = await self._active_session(character.id)
        if row is None or row.phase != "running":
            raise AppError(code=40073, message="渡劫未在进行中", http_status=409)

        cfg = get_game_config().tribulation
        count = cfg.count_tiers.get(row.count_tier)
        raw_batch = (
            int(batch_size)
            if batch_size and batch_size > 0
            else (count.strikes_per_batch if count else 3)
        )
        # 批次大小必须为正整数；0/小数会导致本批不推进 strike_done → auto_resolve 空转
        per_batch = max(1, int(raw_batch))
        power = cfg.power_tiers.get(row.power_tier)
        base_weight = power.base_weight if power else 1.0
        # 名义总伤按 hp_max 比例缩放，使空准备渡劫可陨落、有减伤可过
        scale_factor = float(
            cfg.realm_scale.get(row.target_major, cfg.realm_scale.get("default", 1.2)),
        )
        realm_scale = float(row.hp_max) * scale_factor
        axis_a, env_mult = self._load_axis(row)
        rng = self._rng(row.seed + row.strike_done)

        prep_raw = json.loads(row.prep_slots_json or "[]")
        prep_slots = normalize_prep_slots(prep_raw, slot_count=len(prep_raw) or cfg.prep_slots_default)

        events: list[dict[str, Any]] = []
        remaining = row.strike_total - row.strike_done
        to_do = min(per_batch, remaining)

        for _ in range(to_do):
            if row.hp_current <= 0:
                break
            nominal = compute_strike_nominal(
                power_base_weight=base_weight,
                realm_scale=realm_scale,
                strike_count=row.strike_total,
                env_mult=env_mult,
                in_cloud_double=row.in_cloud_double,
                cloud_double_mult=cfg.in_existing_cloud_damage_mult,
                axis_a_mult=axis_a,
                mercy_damage_mult=row.mercy_damage_mult,
            )
            mit, new_cursor = next_consumable_mitigation(prep_slots, row.prep_cursor)
            row.prep_cursor = new_cursor
            damage = apply_axis_b_mitigation(nominal, prep_mitigation=mit)

            exhausted = prep_exhausted(prep_slots, row.prep_cursor)
            # M5：身上灵宝占位 — 用空列表则护主不触发（无背包法宝钩子）
            guardian = try_guardian_proc(
                hp_current=row.hp_current,
                hp_max=row.hp_max,
                incoming_damage=damage,
                prep_exhausted=exhausted,
                guardian_already_used=row.guardian_used,
                available_artifact_ids=[],
                proc_chance=cfg.guardian_proc_chance,
                restore_ratio=cfg.guardian_hp_restore_ratio,
                current_power_tier=row.power_tier,
                mercy_damage_mult=row.mercy_damage_mult,
                rng=rng,
            )
            event: dict[str, Any] = {
                "strike": row.strike_done + 1,
                "damage": round(damage, 2),
                "mitigation": mit,
            }
            if guardian.triggered:
                row.guardian_used = True
                row.hp_current = guardian.hp_after
                row.power_tier = guardian.new_power_tier
                row.mercy_damage_mult = guardian.mercy_damage_mult
                power = cfg.power_tiers.get(row.power_tier)
                if power:
                    base_weight = power.base_weight
                event["guardian"] = True
            else:
                row.hp_current = max(0.0, row.hp_current - damage)

            row.strike_done += 1
            events.append(event)

        events = compress_batch_events(events, count_tier=row.count_tier)
        existing_events: list[dict[str, Any]] = []
        if row.events_json:
            try:
                existing_events = json.loads(row.events_json)
            except json.JSONDecodeError:
                existing_events = []
        existing_events.extend(events)
        row.events_json = json.dumps(existing_events, ensure_ascii=False)

        outcome = await self._maybe_finish(character, row, now=now)
        await self._session.flush()
        payload: dict[str, Any] = {
            "events": events,
            "session": self._session_to_dict(row),
        }
        if outcome is not None:
            payload["outcome"] = outcome
            # 陨落/结束须带回角色，前端才能切 awaiting_ferry 并弹引渡框
            payload["character"] = await self._character_public_dict(character)
        return payload

    async def auto_resolve(
        self,
        user: User,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Resolve until tribulation ends."""
        require_tribulation_enabled()
        all_events: list[dict[str, Any]] = []
        outcome = None
        for _ in range(10_000):
            result = await self.resolve_batch(user, now=now)
            all_events.extend(result.get("events") or [])
            if "outcome" in result:
                outcome = result["outcome"]
                return {
                    "events": all_events,
                    "session": result["session"],
                    "outcome": outcome,
                    "character": result.get("character"),
                }
            session = result.get("session") or {}
            if session.get("phase") not in _ACTIVE_PHASES:
                return {
                    "events": all_events,
                    "session": session,
                    "outcome": outcome,
                    "character": result.get("character"),
                }
        raise AppError(code=50000, message="渡劫自动结算超过上限", http_status=500)

    async def _maybe_finish(
        self,
        character: Character,
        row: TribulationSession,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Apply win / fail / fall when terminal conditions met."""
        current = now_utc(now)
        cfg = get_game_config().tribulation

        if row.hp_current <= 0:
            self._weather.clear_cloud_for_character(character.id)
            if cfg.fall_on_hp_zero:
                row.phase = "fallen"
                row.result_json = json.dumps({"result": "fallen"}, ensure_ascii=False)
                ferry = FerryService(self._session)
                await ferry.enter_awaiting_ferry(character, now=current)
                logger.info(
                    "tribulation fallen character_id=%s session_id=%s",
                    character.id,
                    row.id,
                )
                return {"result": "fallen"}
            row.phase = "failed"
            character.status = "normal"
            row.result_json = json.dumps({"result": "failed"}, ensure_ascii=False)
            return {"result": "failed"}

        if row.strike_done >= row.strike_total and row.hp_current > 0:
            self._weather.clear_cloud_for_character(character.id)
            await self._apply_win(character, row, now=current)
            row.phase = "won"
            row.result_json = json.dumps(
                {
                    "result": "won",
                    "grade": row.projected_grade,
                },
                ensure_ascii=False,
            )
            character.status = "normal"
            logger.info(
                "tribulation won character_id=%s -> %s",
                character.id,
                row.target_major,
            )
            return {
                "result": "won",
                "target_display": build_realm_display(
                    row.target_major,
                    row.target_stage_label,
                ),
                "grade": row.projected_grade,
            }
        return None

    async def _apply_win(
        self,
        character: Character,
        row: TribulationSession,
        now: datetime,
    ) -> None:
        """Advance realm and write grade / first_tribulation_done flag."""
        stage = get_current_stage(character.major_realm, character.realm_stage)
        required = stage.cultivation_required if stage else 0
        character.realm_progress = max(0, int(character.realm_progress) - required)
        character.major_realm = row.target_major
        character.realm_stage = row.target_stage
        character.realm_stage_label = row.target_stage_label
        character.last_settled_at = now
        character.updated_at = now

        if row.is_cross_major and row.projected_grade:
            character.breakthrough_grade = row.projected_grade
            from_display = build_realm_display(
                get_game_config().tribulation.require_from_major
                if row.target_major == "huashen"
                else "yuanying",
                "perfection",
            )
            to_display = build_realm_display(row.target_major, row.target_stage_label)
            await self._grades.write_grade_history(
                character,
                from_display=from_display,
                to_display=to_display,
                grade_id=row.projected_grade,
            )
            grades_cfg = get_game_config().grades
            grade_def = grades_cfg.grade_by_id(row.projected_grade)
            if grade_def is not None:
                character.divine_ability_slots = int(grade_def.divine_slots)

        flags = parse_story_flags(character.story_flags_json)
        flags["first_tribulation_done"] = True
        character.story_flags_json = dump_story_flags(flags)

    async def gm_force_outcome(
        self,
        user: User,
        outcome: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        DEV/GM：强制结束当前渡劫为 won / failed / fallen（验收用）。

        无活跃会话时会先 ``start_prep(force=True)`` 再结算。

        Args:
            user: GM 用户。
            outcome: ``won`` | ``failed`` | ``fallen``。
            now: 可选冻结时间。

        Returns:
            dict: session + character + outcome。

        Raises:
            AppError: 非法 outcome。
        """
        require_tribulation_enabled()
        allowed = {"won", "failed", "fallen"}
        key = str(outcome or "").strip().lower()
        if key not in allowed:
            raise AppError(
                code=40000,
                message=f"outcome 须为 {sorted(allowed)}",
                http_status=400,
            )

        character = await self._gate.require_character(user)
        current = now_utc(now)
        # 重复验收：若已在待引渡，先清回 normal 再强制开渡结算
        if character.status == "awaiting_ferry":
            character.status = "normal"
            character.ferry_deadline_at = None
        if character.status == "tribulation":
            # 旧会话已结束但 status 残留时允许重建
            existing = await self._active_session(character.id)
            if existing is None:
                character.status = "normal"

        row = await self._active_session(character.id)
        if row is None:
            await self.start_prep(user, force=True, now=current)
            row = await self._active_session(character.id)
        if row is None:
            raise AppError(code=40073, message="无法创建渡劫会话", http_status=409)

        self._weather.clear_cloud_for_character(character.id)

        if key == "fallen":
            row.hp_current = 0.0
            row.phase = "fallen"
            row.result_json = json.dumps({"result": "fallen", "gm": True}, ensure_ascii=False)
            from app.services.ferry_service import FerryService

            await FerryService(self._session).enter_awaiting_ferry(character, now=current)
            logger.warning("gm tribulation fallen character_id=%s", character.id)
        elif key == "failed":
            # 普通失败：回 normal，境界进度腰斩作可见惩罚（占位）
            row.hp_current = 0.0
            row.phase = "failed"
            before = int(character.realm_progress)
            character.realm_progress = max(0, before // 2)
            character.status = "normal"
            character.idle_direction = "none"
            row.result_json = json.dumps(
                {
                    "result": "failed",
                    "gm": True,
                    "penalty": {"realm_progress_before": before, "after": character.realm_progress},
                },
                ensure_ascii=False,
            )
            logger.warning("gm tribulation failed character_id=%s", character.id)
        else:
            await self._apply_win(character, row, now=current)
            row.phase = "won"
            character.status = "normal"
            row.result_json = json.dumps(
                {"result": "won", "gm": True, "grade": row.projected_grade},
                ensure_ascii=False,
            )
            logger.warning("gm tribulation won character_id=%s", character.id)

        character.updated_at = current
        await self._session.flush()
        await self._session.refresh(row)
        return {
            "outcome": {"result": key},
            "session": self._session_to_dict(row),
            "character": await self._character_public_dict(character),
            "message": f"GM 强制渡劫结局={key}",
        }
