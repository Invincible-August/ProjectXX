"""
突破预览、同步 attempt 与异步真读条（M1 + M2 品阶 + M5-D05）。

真读条：开读条扣灵石并占用 ``breaking_through``，到期懒结算掷骰；
``async_channel.enabled=false`` 时回退同步 attempt。
"""

from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time_utils import ensure_aware_utc, now_utc, to_utc_iso
from app.db.models.breakthrough_grade import BreakthroughGradeHistory
from app.db.models.breakthrough_session import BreakthroughSession
from app.db.models.character import Character
from app.db.models.user import User
from app.schemas.common import AppError
from app.services import character_service
from app.services.grade_service import (
    GradeService,
    grade_name_map,
    grade_preview_text,
)
from app.services.play_gate import PlayGate
from app.services.realm_config import (
    BreakthroughRule,
    build_realm_display,
    get_current_stage,
    get_game_config,
    get_major_realm,
    is_perfection_stage,
)

logger = logging.getLogger(__name__)

_ADVANCE_TYPE_LABEL_ZH = {
    "layer": "层进阶",
    "major": "跨境突破",
}


def _settle_idle_before_breakthrough(character: Character, *, now: datetime) -> None:
    """
    Lazy-import idle settle to avoid breakthrough ↔ idle service cycles.

    Args:
        character: Character being settled.
        now: Wall-clock for settle.
    """
    from app.services.idle_service import settle_idle

    settle_idle(character, now=now)


class BreakthroughService:
    """
    Application service for realm breakthrough preview, sync attempts, and async channel.

    Attributes:
        _session: Request-scoped async SQLAlchemy session.
        _gate: Cross-play precondition gate.
        _grades: Grade rolling and history helper service.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize breakthrough service dependencies.

        Args:
            session: Async SQLAlchemy session bound to the current request.
        """
        self._session = session
        self._gate = PlayGate(session)
        self._grades = GradeService(session)

    @staticmethod
    def _rng() -> random.Random:
        """
        Construct breakthrough attempt RNG; tests may inject via ``BREAKTHROUGH_RNG_SEED``.

        Returns:
            random.Random: Isolated RNG instance.
        """
        settings = get_settings()
        if settings.breakthrough_rng_seed is not None:
            return random.Random(settings.breakthrough_rng_seed)
        return random.Random()

    @staticmethod
    def _async_enabled() -> bool:
        """Whether async true-channel is enabled in game config."""
        return bool(get_game_config().breakthrough.async_channel.enabled)

    @staticmethod
    def _resolve_advance(
        character: Character,
    ) -> tuple[str, BreakthroughRule, str | None]:
        """
        Determine layer vs major-realm advance and return rule plus display name.

        Args:
            character: Character entity to evaluate.

        Returns:
            tuple: ``(advance_type, rule, next_realm_display)`` where advance_type is
                ``"layer"`` or ``"major"``.

        Raises:
            AppError: ``40026`` when advancement is blocked or misconfigured.
        """
        major = get_major_realm(character.major_realm)
        if major is None:
            raise AppError(code=40026, message="当前境界未开放突破", http_status=400)

        if character.major_realm == "huashen" and is_perfection_stage(
            character.major_realm,
            character.realm_stage,
        ):
            raise AppError(
                code=40026,
                message="已达当前版本境界开放上限（化神圆满）",
                http_status=400,
            )

        cfg = get_game_config().breakthrough
        if is_perfection_stage(character.major_realm, character.realm_stage):
            next_key = major.next_major
            if not next_key:
                raise AppError(
                    code=40026,
                    message="已达当前版本境界开放上限",
                    http_status=400,
                )
            next_major = get_major_realm(next_key)
            if next_major is None:
                raise AppError(
                    code=40026,
                    message="下一境界尚未配置",
                    http_status=400,
                )
            first = next_major.stages[0]
            next_display = build_realm_display(next_key, first.label)
            return "major", cfg.major_advance, next_display

        next_stage_num = character.realm_stage + 1
        next_stage = major.stage_by_number(next_stage_num)
        if next_stage is None:
            raise AppError(code=40026, message="下一层期未配置", http_status=400)
        next_display = build_realm_display(character.major_realm, next_stage.label)
        return "layer", cfg.layer_advance, next_display

    @staticmethod
    def resolve_spirit_stone_cost(
        character: Character,
        advance_type: str,
        rule: BreakthroughRule,
    ) -> int:
        """
        解析本次突破实际灵石消耗。

        筑基前（锻体/炼气）默认免费；仅「炼气圆满→筑基」跨境扣 ``major_advance`` 费用。
        与轮回次数无关。

        Args:
            character: 当前角色（读 major_realm）。
            advance_type: ``layer`` / ``major``。
            rule: 对应进阶规则（提供筑基后或入筑基时的标价）。

        Returns:
            int: 实际应扣灵石（≥0）。
        """
        cfg = get_game_config().breakthrough
        if not cfg.pre_foundation_free:
            return max(0, int(rule.spirit_stone_cost))
        major = str(character.major_realm or "")
        # 锻体/炼气：层进阶与锻体→炼气跨境均免费；炼气→筑基收费
        if major in ("body_tempering", "qi_refining"):
            if advance_type == "major" and major == "qi_refining":
                return max(0, int(rule.spirit_stone_cost))
            return 0
        return max(0, int(rule.spirit_stone_cost))

    async def _apply_success(
        self,
        character: Character,
        advance_type: str,
        required: int,
        rule: BreakthroughRule,
        *,
        charge_stones: bool = True,
    ) -> tuple[int, int, str, str | None, str | None, int | None]:
        """
        Apply breakthrough success: deduct costs, advance realm, roll grade on major jump.

        Args:
            character: Mutable character entity.
            advance_type: ``"layer"`` or ``"major"``.
            required: Cultivation progress threshold consumed on success.
            rule: Breakthrough rule from game config.
            charge_stones: When False, stones were already charged at channel start.

        Returns:
            tuple: cultivation_delta, stones_delta, message, grade_id, grade_name, divine_slots.
        """
        stones_delta = 0
        if charge_stones:
            stones_delta = -rule.spirit_stone_cost
            character.spirit_stones = int(character.spirit_stones) + stones_delta
        else:
            # 读条开局已扣；响应仍报告消耗以便前端展示
            stones_delta = -rule.spirit_stone_cost

        character.realm_progress = max(0, int(character.realm_progress) - required)
        cultivation_delta = -required

        grade_id: str | None = None
        grade_name: str | None = None
        divine_slots: int | None = None

        if advance_type == "layer":
            major = get_major_realm(character.major_realm)
            assert major is not None
            next_stage = major.stage_by_number(character.realm_stage + 1)
            assert next_stage is not None
            character.realm_stage = next_stage.stage
            character.realm_stage_label = next_stage.label
            display = build_realm_display(character.major_realm, next_stage.label)
            message = f"突破成功，抵达{display}"
            await self._apply_reincarnation_growth(character, advance_type="layer")
        else:
            from_display = build_realm_display(
                character.major_realm,
                character.realm_stage_label,
            )
            major = get_major_realm(character.major_realm)
            assert major is not None and major.next_major
            next_key = major.next_major
            next_major = get_major_realm(next_key)
            assert next_major is not None
            first = next_major.stages[0]
            character.major_realm = next_key
            character.realm_stage = first.stage
            character.realm_stage_label = first.label
            from app.domain.reincarnation_rules import resolve_peak_major

            character.peak_major_realm = resolve_peak_major(
                next_key,
                getattr(character, "peak_major_realm", None),
            )
            display = build_realm_display(next_key, first.label)

            rolled = await self._grades.roll_breakthrough_grade(character)
            grade_id = rolled.grade_id
            grade_name = rolled.name
            divine_slots = rolled.divine_slots
            character.breakthrough_grade = grade_id
            character.divine_ability_slots = divine_slots

            await self._grades.write_grade_history(
                character,
                from_display=from_display,
                to_display=display,
                grade_id=grade_id,
            )
            message = f"跨境突破成功，抵达{display}（品阶：{grade_name}）"
            logger.info(
                "breakthrough major grade=%s character_id=%s -> %s",
                grade_id,
                character.id,
                display,
            )
            await self._apply_reincarnation_growth(character, advance_type="major")

        return cultivation_delta, stones_delta, message, grade_id, grade_name, divine_slots

    async def _apply_reincarnation_growth(
        self,
        character: Character,
        *,
        advance_type: str,
    ) -> None:
        """
        On breakthrough success, add permanent minor/major growth into this-life applied growth.

        Args:
            character: Character entity.
            advance_type: ``layer`` (minor) or ``major``.
        """
        from app.db.models.reincarnation_bonus import CharacterReincarnationBonus

        result = await self._session.execute(
            select(CharacterReincarnationBonus).where(
                CharacterReincarnationBonus.character_id == character.id,
            ),
        )
        bonus = result.scalar_one_or_none()
        if bonus is None:
            return
        if advance_type == "layer":
            bonus.lifetime_applied_growth = float(bonus.lifetime_applied_growth) + float(
                bonus.minor_growth_bonus,
            )
        else:
            bonus.lifetime_applied_growth = float(bonus.lifetime_applied_growth) + float(
                bonus.major_growth_bonus,
            )

    def _effective_success_rate(
        self,
        character: Character,
        base_rate: float,
        break_rate_bonus: float = 0.0,
    ) -> float:
        """Clamp base success rate + permanent break_rate_bonus."""
        from app.domain.reincarnation_rules import clamp_break_success_rate

        cfg = get_game_config()
        clamp_cfg = dict(cfg.breakthrough.success_rate_clamp)
        rein_clamp = (cfg.reincarnation.permanent_bonus_on_settle or {}).get(
            "break_rate_clamp",
        )
        if isinstance(rein_clamp, dict) and rein_clamp:
            clamp_cfg = {
                "min": float(rein_clamp.get("min", clamp_cfg.get("min", 0.05))),
                "max": float(rein_clamp.get("max", clamp_cfg.get("max", 0.95))),
            }
        return clamp_break_success_rate(base_rate, break_rate_bonus, clamp_cfg)

    @staticmethod
    def _apply_failure(
        character: Character,
        rule: BreakthroughRule,
        *,
        charge_stones: bool = True,
        refund_charged: int = 0,
    ) -> tuple[int, int, str]:
        """
        Apply breakthrough failure: rollback realm_progress by keep_ratio.

        Args:
            character: Mutable character entity.
            rule: Breakthrough rule from game config.
            charge_stones: When True and fail_still_charge, deduct stones now (sync path).
            refund_charged: Async path: stones charged at start to refund when failure
                should not keep the charge.

        Returns:
            tuple: cultivation_delta, stones_delta, user-facing message.
        """
        before = int(character.realm_progress)
        kept = int(before * rule.fail_cultivation_keep_ratio)
        character.realm_progress = kept
        cultivation_delta = kept - before

        stones_delta = 0
        if charge_stones and rule.fail_still_charge_stones:
            stones_delta = -rule.spirit_stone_cost
            character.spirit_stones = max(0, int(character.spirit_stones) + stones_delta)
        elif refund_charged > 0 and not rule.fail_still_charge_stones:
            # 开读条已扣，失败配置不扣 → 退回
            character.spirit_stones = int(character.spirit_stones) + int(refund_charged)
            stones_delta = 0
        elif not charge_stones and rule.fail_still_charge_stones:
            # 开读条已扣且失败仍扣 → 报告已扣额度
            stones_delta = -int(refund_charged or rule.spirit_stone_cost)

        message = f"突破失败，境界进度回退至 {kept}"
        return cultivation_delta, stones_delta, message

    async def _break_rate_bonus(self, character: Character) -> float:
        """Load permanent reincarnation break_rate_bonus for character."""
        from app.db.models.reincarnation_bonus import CharacterReincarnationBonus

        bonus_row = (
            await self._session.execute(
                select(CharacterReincarnationBonus).where(
                    CharacterReincarnationBonus.character_id == character.id,
                ),
            )
        ).scalar_one_or_none()
        return float(bonus_row.break_rate_bonus) if bonus_row else 0.0

    async def _get_active_session(
        self,
        character_id: int,
    ) -> BreakthroughSession | None:
        """Load the active breakthrough channel session if any."""
        result = await self._session.execute(
            select(BreakthroughSession)
            .where(
                BreakthroughSession.character_id == character_id,
                BreakthroughSession.status == "active",
            )
            .order_by(BreakthroughSession.id.desc())
            .limit(1),
        )
        return result.scalar_one_or_none()

    def _channel_progress_dict(
        self,
        row: BreakthroughSession,
        *,
        now: datetime,
        state: str = "in_progress",
        result: dict | None = None,
    ) -> dict[str, Any]:
        """Build player-visible channel envelope (Chinese labels)."""
        channel_cfg = get_game_config().breakthrough.async_channel
        duration = max(1, int(row.duration_seconds))
        started = ensure_aware_utc(row.started_at)
        ends = ensure_aware_utc(row.ends_at)
        elapsed = max(0.0, (now - started).total_seconds())
        ratio = min(1.0, elapsed / duration)
        remaining = max(0, int((ends - now).total_seconds()))
        payload: dict[str, Any] = {
            "state": state,
            "session_id": row.id,
            "progress_ratio": round(ratio, 4),
            "started_at": to_utc_iso(started),
            "ends_at": to_utc_iso(ends),
            "remaining_seconds": remaining if state == "in_progress" else 0,
            "duration_seconds": duration,
            "advance_type": row.advance_type,
            "advance_type_label_zh": _ADVANCE_TYPE_LABEL_ZH.get(
                row.advance_type,
                row.advance_type,
            ),
            "label_zh": channel_cfg.label_zh,
            "hint_zh": channel_cfg.hint_zh,
            "client_poll_ms": channel_cfg.client_poll_ms,
        }
        if result is not None:
            payload["result"] = result
        return payload

    async def lazy_resolve_channel_for_character(
        self,
        character: Character,
        *,
        now: datetime | None = None,
        user: User | None = None,
    ) -> dict | None:
        """
        懒结算：若存在到期的 active 会话则掷骰落库；未到期返回 None。

        Args:
            character: Character entity (may be mutated).
            now: Frozen UTC clock.
            user: Optional owner for building public character in result.

        Returns:
            dict | None: Resolved attempt payload when settled; else None.
        """
        if not self._async_enabled() and character.status != "breaking_through":
            return None

        current_time = now_utc(now)
        row = await self._get_active_session(int(character.id))
        if row is None:
            # 状态残留而无会话：纠偏回 normal，避免永久锁死
            if character.status == "breaking_through":
                logger.warning(
                    "breakthrough orphan status character_id=%s -> normal",
                    character.id,
                )
                character.status = "normal"
                await self._session.flush()
            return None

        if current_time < ensure_aware_utc(row.ends_at):
            return None

        return await self._resolve_session(
            character,
            row,
            now=current_time,
            user=user,
            force=True,
        )

    async def _resolve_session(
        self,
        character: Character,
        row: BreakthroughSession,
        *,
        now: datetime,
        user: User | None,
        force: bool,
    ) -> dict:
        """
        Apply dice + success/fail for an active session; mark resolved.

        Args:
            character: Character entity.
            row: Active session row.
            now: Settlement UTC time.
            user: Owner for public envelope (required for full payload).
            force: When False and not yet ended, raise ``40028``.

        Returns:
            dict: Attempt-compatible result payload.

        Raises:
            AppError: ``40028`` if not ended and force is False.
        """
        if row.status != "active":
            if row.result_json:
                cached = json.loads(row.result_json)
                if user is not None:
                    public = await character_service.get_my_character(self._session, user)
                    cached["character"] = character_service.character_public_to_dict(public)
                return cached
            raise AppError(code=40029, message="无进行中的闭关突破", http_status=400)

        if now < ensure_aware_utc(row.ends_at):
            raise AppError(
                code=40028,
                message="闭关尚未完成，请稍候再查看结果",
                http_status=409,
            )

        snapshot = json.loads(row.rule_snapshot_json or "{}")
        rule = BreakthroughRule(
            success_rate=float(snapshot.get("success_rate", 0.5)),
            spirit_stone_cost=int(snapshot.get("spirit_stone_cost", row.spirit_stones_charged)),
            fail_cultivation_keep_ratio=float(
                snapshot.get("fail_cultivation_keep_ratio", 0.7),
            ),
            fail_still_charge_stones=bool(snapshot.get("fail_still_charge_stones", True)),
        )
        required = int(snapshot.get("required_cultivation", 0))
        advance_type = row.advance_type
        effective_rate = float(row.effective_success_rate)

        from app.services.dice_service import DiceService

        dice_svc = DiceService(self._session)
        dice_result = await dice_svc.roll_breakthrough(
            character,
            success_rate=effective_rate,
            rng=self._rng(),
        )
        success = bool(dice_result["success"])
        roll = int(dice_result["roll"])
        grade_id: str | None = None
        grade_name: str | None = None
        divine_slots: int | None = None

        try:
            if success:
                (
                    cultivation_delta,
                    stones_delta,
                    message,
                    grade_id,
                    grade_name,
                    divine_slots,
                ) = await self._apply_success(
                    character,
                    advance_type,
                    required,
                    rule,
                    charge_stones=False,
                )
            else:
                cultivation_delta, stones_delta, message = self._apply_failure(
                    character,
                    rule,
                    charge_stones=False,
                    refund_charged=int(row.spirit_stones_charged),
                )
        finally:
            character.status = "normal"
            character.last_settled_at = now
            character.updated_at = now
            row.status = "resolved"
            row.resolved_at = now

        await self._session.flush()
        await self._session.refresh(character)

        logger.info(
            "breakthrough channel resolve character_id=%s session_id=%s success=%s "
            "type=%s roll=%s",
            character.id,
            row.id,
            success,
            advance_type,
            roll,
        )

        if user is None:
            # 无 user 时仍写精简缓存，供后续带 user 的查询补全 character
            owner = await self._session.get(User, character.user_id)
            user = owner

        public = (
            await character_service.get_my_character(self._session, user)
            if user is not None
            else None
        )
        payload: dict[str, Any] = {
            "success": success,
            "advance_type": advance_type,
            "message": message,
            "cultivation_delta": cultivation_delta,
            "spirit_stones_delta": stones_delta,
            "character": (
                character_service.character_public_to_dict(public)
                if public is not None
                else None
            ),
            "dice": {
                "roll": roll,
                "threshold": dice_result.get("threshold"),
                "lo": dice_result.get("lo"),
                "hi": dice_result.get("hi"),
                "base_min": dice_result.get("base_min"),
                "base_max": dice_result.get("base_max"),
                "success_rate": dice_result.get("success_rate"),
            },
            "channel_resolved": True,
        }
        if grade_id is not None:
            payload["grade"] = grade_id
            payload["grade_name"] = grade_name
            payload["divine_ability_slots"] = divine_slots

        row.result_json = json.dumps(payload, ensure_ascii=False)
        await self._session.flush()
        return payload

    async def preview_breakthrough(
        self,
        user: User,
        now: datetime | None = None,
    ) -> dict:
        """
        Return breakthrough preview after settle, pending resolution, and lazy channel resolve.

        Args:
            user: Authenticated user.
            now: Optional frozen UTC timestamp.

        Returns:
            dict: Read-only breakthrough preview payload (+ optional channel).
        """
        character = await self._gate.require_character(user)
        current_time = now_utc(now)
        await self._gate.resolve_pending_before_play(character, now=current_time)
        _settle_idle_before_breakthrough(character, now=current_time)
        resolved = await self.lazy_resolve_channel_for_character(
            character,
            now=current_time,
            user=user,
        )
        await self._session.flush()
        data = preview_breakthrough_for_character(character)
        channel_cfg = get_game_config().breakthrough.async_channel
        data["async_channel_enabled"] = bool(channel_cfg.enabled)
        data["async_channel_label_zh"] = channel_cfg.label_zh
        data["async_channel_hint_zh"] = channel_cfg.hint_zh
        data["client_poll_ms"] = channel_cfg.client_poll_ms

        if resolved is not None:
            data["just_resolved"] = True
            data["resolved_result"] = resolved
            data["channel"] = None
            return data

        active = await self._get_active_session(int(character.id))
        if active is not None:
            data["can_attempt"] = False
            data["reason"] = "闭关突破进行中"
            data["channel"] = self._channel_progress_dict(active, now=current_time)
        else:
            data["channel"] = None
        return data

    async def start_channel(
        self,
        user: User,
        now: datetime | None = None,
    ) -> dict:
        """
        开异步真读条：校验 → 扣灵石 → 建会话 → ``status=breaking_through``。

        Args:
            user: Authenticated user.
            now: Optional frozen UTC timestamp.

        Returns:
            dict: ``{ channel, character, needs_tribulation? }``.

        Raises:
            AppError: Validation / mutex errors（同 attempt）.
        """
        character = await self._gate.require_character(user)
        current_time = now_utc(now)
        auto_claimed = await self._gate.resolve_pending_before_play(
            character,
            now=current_time,
        )
        _settle_idle_before_breakthrough(character, now=current_time)
        await self.lazy_resolve_channel_for_character(
            character,
            now=current_time,
            user=user,
        )

        if character.status == "breaking_through":
            raise AppError(code=40024, message="已在突破中", http_status=409)
        if character.status == "tribulation":
            raise AppError(code=40063, message="已在渡劫中，不可常规突破", http_status=409)

        from app.domain.activity_mutex import Activity

        await self._gate.assert_activity(character, Activity.BREAKTHROUGH)

        stage = get_current_stage(character.major_realm, character.realm_stage)
        if stage is None:
            raise AppError(code=40026, message="当前境界配置缺失", http_status=400)

        required = stage.cultivation_required
        if int(character.realm_progress) < required:
            raise AppError(code=40023, message="境界进度不足，无法突破", http_status=400)

        advance_type, rule, _next_display = self._resolve_advance(character)

        from app.services.tribulation_service import needs_tribulation_for_advance

        major = get_major_realm(character.major_realm)
        target_major = None
        if advance_type == "major" and major is not None:
            target_major = major.next_major
        if needs_tribulation_for_advance(
            character,
            advance_type=advance_type,
            target_major=target_major,
        ):
            public = await character_service.get_my_character(self._session, user)
            return {
                "success": False,
                "needs_tribulation": True,
                "advance_type": advance_type,
                "message": "跨大境界进阶须渡天劫，请前往渡劫准备（小境界进阶无需渡劫）",
                "cultivation_delta": 0,
                "spirit_stones_delta": 0,
                "character": character_service.character_public_to_dict(public),
                "hint": "POST /tribulation/start-prep",
                "channel": None,
            }

        # 筑基前免费；仅炼气→筑基跨境扣费
        cost = self.resolve_spirit_stone_cost(character, advance_type, rule)
        if int(character.spirit_stones) < cost:
            raise AppError(code=40021, message="灵石不足", http_status=400)

        # 已有 active 会话（竞态）
        existing = await self._get_active_session(int(character.id))
        if existing is not None:
            raise AppError(code=40024, message="已在突破中", http_status=409)

        break_bonus = await self._break_rate_bonus(character)
        effective_rate = self._effective_success_rate(
            character,
            rule.success_rate,
            break_bonus,
        )
        channel_cfg = get_game_config().breakthrough.async_channel
        duration = channel_cfg.duration_for(advance_type)
        ends_at = current_time + timedelta(seconds=duration)

        # 开读条扣灵石（cost 可为 0；失败且 fail_still_charge=false 时结算退回）
        character.spirit_stones = int(character.spirit_stones) - cost
        character.status = "breaking_through"
        character.updated_at = current_time

        snapshot = {
            "success_rate": rule.success_rate,
            "spirit_stone_cost": cost,
            "fail_cultivation_keep_ratio": rule.fail_cultivation_keep_ratio,
            # 免费突破失败无需「仍扣石」语义
            "fail_still_charge_stones": (
                rule.fail_still_charge_stones if cost > 0 else False
            ),
            "required_cultivation": required,
        }
        row = BreakthroughSession(
            character_id=int(character.id),
            status="active",
            advance_type=advance_type,
            started_at=current_time,
            ends_at=ends_at,
            duration_seconds=duration,
            spirit_stones_charged=cost,
            effective_success_rate=effective_rate,
            rule_snapshot_json=json.dumps(snapshot, ensure_ascii=False),
            from_major=str(character.major_realm),
            from_stage=int(character.realm_stage),
            realm_progress_at_start=int(character.realm_progress),
        )
        self._session.add(row)
        await self._session.flush()

        logger.info(
            "breakthrough channel start character_id=%s session_id=%s type=%s duration=%ss",
            character.id,
            row.id,
            advance_type,
            duration,
        )

        public = await character_service.get_my_character(self._session, user)
        payload: dict[str, Any] = {
            "success": None,
            "channel_started": True,
            "advance_type": advance_type,
            "message": f"{channel_cfg.label_zh}已开始，请等待闭关完成",
            "cultivation_delta": 0,
            "spirit_stones_delta": -cost,
            "character": character_service.character_public_to_dict(public),
            "channel": self._channel_progress_dict(row, now=current_time),
        }
        if auto_claimed is not None:
            payload["auto_claimed_offline"] = auto_claimed
        return payload

    async def get_channel(
        self,
        user: User,
        now: datetime | None = None,
    ) -> dict:
        """
        查询读条进度；到期则懒结算并返回 ``state=resolved`` + result。

        Args:
            user: Authenticated user.
            now: Optional frozen UTC.

        Returns:
            dict: ``{ channel, character }``；无会话时 channel 为 null。
        """
        character = await self._gate.require_character(user)
        current_time = now_utc(now)
        # 先自行懒结算并捕获结果（PlayGate 内也会结算，但返回值在此更可控）
        resolved = await self.lazy_resolve_channel_for_character(
            character,
            now=current_time,
            user=user,
        )
        await self._gate.resolve_pending_before_play(character, now=current_time)
        _settle_idle_before_breakthrough(character, now=current_time)

        # resolve_pending 可能又结算了一次（幂等）；若上面未捕获则再查最近 resolved
        if resolved is None:
            resolved = await self._latest_resolved_payload(character, user=user)

        public = await character_service.get_my_character(self._session, user)
        public_dict = character_service.character_public_to_dict(public)

        if resolved is not None:
            result = await self._session.execute(
                select(BreakthroughSession)
                .where(
                    BreakthroughSession.character_id == character.id,
                    BreakthroughSession.status == "resolved",
                )
                .order_by(BreakthroughSession.id.desc())
                .limit(1),
            )
            row = result.scalar_one_or_none()
            channel = None
            if row is not None:
                channel = self._channel_progress_dict(
                    row,
                    now=current_time,
                    state="resolved",
                    result=resolved,
                )
            return {"channel": channel, "character": public_dict, "just_resolved": True}

        active = await self._get_active_session(int(character.id))
        if active is None:
            return {"channel": None, "character": public_dict}
        return {
            "channel": self._channel_progress_dict(active, now=current_time),
            "character": public_dict,
        }

    async def _latest_resolved_payload(
        self,
        character: Character,
        *,
        user: User | None,
    ) -> dict | None:
        """Read cached result from the latest resolved session, if any."""
        result = await self._session.execute(
            select(BreakthroughSession)
            .where(
                BreakthroughSession.character_id == character.id,
                BreakthroughSession.status == "resolved",
            )
            .order_by(BreakthroughSession.id.desc())
            .limit(1),
        )
        row = result.scalar_one_or_none()
        if row is None or not row.result_json:
            return None
        cached = json.loads(row.result_json)
        if user is not None:
            public = await character_service.get_my_character(self._session, user)
            cached["character"] = character_service.character_public_to_dict(public)
        return cached

    async def resolve_channel(
        self,
        user: User,
        now: datetime | None = None,
    ) -> dict:
        """
        显式结算：未到期 → ``40028``；无会话 → ``40029``。

        Args:
            user: Authenticated user.
            now: Optional frozen UTC.

        Returns:
            dict: Attempt-compatible result + channel envelope.
        """
        character = await self._gate.require_character(user)
        current_time = now_utc(now)
        _settle_idle_before_breakthrough(character, now=current_time)

        row = await self._get_active_session(int(character.id))
        if row is None:
            # 可能已被其它入口懒结算：若刚结算完则返回缓存，否则 40029
            cached = await self._latest_resolved_payload(character, user=user)
            if cached is not None and cached.get("channel_resolved"):
                # 仅当角色已不在进阶中时视为「本次可读的结算」
                if character.status == "normal":
                    result_row = await self._session.execute(
                        select(BreakthroughSession)
                        .where(
                            BreakthroughSession.character_id == character.id,
                            BreakthroughSession.status == "resolved",
                        )
                        .order_by(BreakthroughSession.id.desc())
                        .limit(1),
                    )
                    done = result_row.scalar_one_or_none()
                    channel = (
                        self._channel_progress_dict(
                            done,
                            now=current_time,
                            state="resolved",
                            result=cached,
                        )
                        if done is not None
                        else None
                    )
                    return {**cached, "channel": channel}
            raise AppError(code=40029, message="无进行中的闭关突破", http_status=400)

        result = await self._resolve_session(
            character,
            row,
            now=current_time,
            user=user,
            force=False,
        )
        channel = self._channel_progress_dict(
            row,
            now=current_time,
            state="resolved",
            result=result,
        )
        return {**result, "channel": channel}

    async def attempt_breakthrough(
        self,
        user: User,
        now: datetime | None = None,
    ) -> dict:
        """
        Execute breakthrough: async start when enabled, else synchronous attempt.

        Args:
            user: Authenticated user.
            now: Optional frozen UTC timestamp.

        Returns:
            dict: Channel start envelope or sync attempt outcome.

        Raises:
            AppError: ``40021``–``40026`` for validation failures; ``409`` for state mutex.
        """
        if self._async_enabled():
            return await self.start_channel(user, now=now)

        character = await self._gate.require_character(user)
        current_time = now_utc(now)
        auto_claimed = await self._gate.resolve_pending_before_play(character, now=current_time)
        _settle_idle_before_breakthrough(character, now=current_time)

        if character.status == "breaking_through":
            raise AppError(code=40024, message="已在突破中", http_status=409)
        if character.status == "tribulation":
            raise AppError(code=40063, message="已在渡劫中，不可常规突破", http_status=409)

        from app.domain.activity_mutex import Activity

        await self._gate.assert_activity(character, Activity.BREAKTHROUGH)

        stage = get_current_stage(character.major_realm, character.realm_stage)
        if stage is None:
            raise AppError(code=40026, message="当前境界配置缺失", http_status=400)

        required = stage.cultivation_required
        if int(character.realm_progress) < required:
            raise AppError(code=40023, message="境界进度不足，无法突破", http_status=400)

        advance_type, rule, _next_display = self._resolve_advance(character)

        from app.services.tribulation_service import needs_tribulation_for_advance

        major = get_major_realm(character.major_realm)
        target_major = None
        if advance_type == "major" and major is not None:
            target_major = major.next_major
        if needs_tribulation_for_advance(
            character,
            advance_type=advance_type,
            target_major=target_major,
        ):
            public = await character_service.get_my_character(self._session, user)
            return {
                "success": False,
                "needs_tribulation": True,
                "advance_type": advance_type,
                "message": "跨大境界进阶须渡天劫，请前往渡劫准备（小境界进阶无需渡劫）",
                "cultivation_delta": 0,
                "spirit_stones_delta": 0,
                "character": character_service.character_public_to_dict(public),
                "hint": "POST /tribulation/start-prep",
            }

        cost = self.resolve_spirit_stone_cost(character, advance_type, rule)
        if int(character.spirit_stones) < cost:
            raise AppError(code=40021, message="灵石不足", http_status=400)

        # 用有效灵石价覆盖规则，供成功/失败扣费路径复用
        billed_rule = BreakthroughRule(
            success_rate=rule.success_rate,
            spirit_stone_cost=cost,
            fail_cultivation_keep_ratio=rule.fail_cultivation_keep_ratio,
            fail_still_charge_stones=rule.fail_still_charge_stones if cost > 0 else False,
        )

        character.status = "breaking_through"
        await self._session.flush()

        break_bonus = await self._break_rate_bonus(character)
        effective_rate = self._effective_success_rate(
            character,
            rule.success_rate,
            break_bonus,
        )

        from app.services.dice_service import DiceService

        dice_svc = DiceService(self._session)
        dice_result = await dice_svc.roll_breakthrough(
            character,
            success_rate=effective_rate,
            rng=self._rng(),
        )
        success = bool(dice_result["success"])
        roll = int(dice_result["roll"])
        grade_id: str | None = None
        grade_name: str | None = None
        divine_slots: int | None = None

        try:
            if success:
                (
                    cultivation_delta,
                    stones_delta,
                    message,
                    grade_id,
                    grade_name,
                    divine_slots,
                ) = await self._apply_success(
                    character,
                    advance_type,
                    required,
                    billed_rule,
                )
            else:
                cultivation_delta, stones_delta, message = self._apply_failure(
                    character,
                    billed_rule,
                )
        finally:
            character.status = "normal"
            character.last_settled_at = current_time
            character.updated_at = current_time

        await self._session.flush()
        await self._session.refresh(character)

        logger.info(
            "breakthrough attempt character_id=%s success=%s type=%s roll=%s threshold=%s lo=%s hi=%s",
            character.id,
            success,
            advance_type,
            roll,
            dice_result.get("threshold"),
            dice_result.get("lo"),
            dice_result.get("hi"),
        )

        public = await character_service.get_my_character(self._session, user)
        payload: dict = {
            "success": success,
            "advance_type": advance_type,
            "message": message,
            "cultivation_delta": cultivation_delta,
            "spirit_stones_delta": stones_delta,
            "character": character_service.character_public_to_dict(public),
            "dice": {
                "roll": roll,
                "threshold": dice_result.get("threshold"),
                "lo": dice_result.get("lo"),
                "hi": dice_result.get("hi"),
                "base_min": dice_result.get("base_min"),
                "base_max": dice_result.get("base_max"),
                "success_rate": dice_result.get("success_rate"),
            },
        }
        if grade_id is not None:
            payload["grade"] = grade_id
            payload["grade_name"] = grade_name
            payload["divine_ability_slots"] = divine_slots
        if auto_claimed is not None:
            payload["auto_claimed_offline"] = auto_claimed
        return payload

    async def list_grade_history(
        self,
        user: User,
        *,
        limit: int = 20,
    ) -> list[dict]:
        """
        Return the most recent cross-realm grade history entries.

        Args:
            user: Authenticated user.
            limit: Maximum number of rows to return.

        Returns:
            list[dict]: Grade history records with display names and timestamps.
        """
        character = await self._gate.require_character(user)
        result = await self._session.execute(
            select(BreakthroughGradeHistory)
            .where(BreakthroughGradeHistory.character_id == character.id)
            .order_by(BreakthroughGradeHistory.created_at.desc())
            .limit(limit),
        )
        rows = result.scalars().all()
        names = grade_name_map()
        return [
            {
                "from_realm_display": row.from_realm_display,
                "to_realm_display": row.to_realm_display,
                "grade": row.grade,
                "grade_name": names.get(row.grade, row.grade),
                "created_at": to_utc_iso(row.created_at),
            }
            for row in rows
        ]


def preview_breakthrough_for_character(character: Character) -> dict:
    """
    Read-only breakthrough preview (caller must have settled first).

    Args:
        character: Character entity with up-to-date progress fields.

    Returns:
        dict: Preview payload with can_attempt, costs, and grade hint.
    """
    from app.domain.breakthrough import BreakthroughPreview

    stage = get_current_stage(character.major_realm, character.realm_stage)
    if stage is None:
        return BreakthroughPreview(
            can_attempt=False,
            reason="当前境界配置缺失",
            required_cultivation=0,
            current_cultivation=int(character.realm_progress),
            spirit_stone_cost=0,
            success_rate=0.0,
            advance_type=None,
            next_realm_display=None,
            grade_preview=None,
        ).to_dict()

    required = stage.cultivation_required
    current = int(character.realm_progress)

    try:
        advance_type, rule, next_display = BreakthroughService._resolve_advance(character)
    except AppError as exc:
        return BreakthroughPreview(
            can_attempt=False,
            reason=exc.message,
            required_cultivation=required,
            current_cultivation=current,
            spirit_stone_cost=0,
            success_rate=0.0,
            advance_type=None,
            next_realm_display=None,
            grade_preview=None,
        ).to_dict()

    stone_cost = BreakthroughService.resolve_spirit_stone_cost(
        character,
        advance_type,
        rule,
    )
    reason = ""
    can = True
    if character.status != "normal":
        can = False
        reason = "当前状态不可突破"
    elif current < required:
        can = False
        reason = f"境界进度不足（需 {required}）"
    elif int(character.spirit_stones) < stone_cost:
        can = False
        reason = f"灵石不足（需 {stone_cost}）"

    grade_preview = grade_preview_text() if advance_type == "major" else None

    return BreakthroughPreview(
        can_attempt=can,
        reason=reason,
        required_cultivation=required,
        current_cultivation=current,
        spirit_stone_cost=stone_cost,
        success_rate=rule.success_rate,
        advance_type=advance_type,
        next_realm_display=next_display,
        grade_preview=grade_preview,
    ).to_dict()


# ---------------------------------------------------------------------------
# Module-level wrappers (backward-compatible for tests and legacy imports)
# ---------------------------------------------------------------------------


async def preview_breakthrough(
    session: AsyncSession,
    user: User,
    now: datetime | None = None,
) -> dict:
    """Module wrapper delegating to ``BreakthroughService.preview_breakthrough``."""
    return await BreakthroughService(session).preview_breakthrough(user, now=now)


async def attempt_breakthrough(
    session: AsyncSession,
    user: User,
    now: datetime | None = None,
) -> dict:
    """Module wrapper delegating to ``BreakthroughService.attempt_breakthrough``."""
    return await BreakthroughService(session).attempt_breakthrough(user, now=now)


async def start_channel(
    session: AsyncSession,
    user: User,
    now: datetime | None = None,
) -> dict:
    """Module wrapper for async channel start."""
    return await BreakthroughService(session).start_channel(user, now=now)


async def get_channel(
    session: AsyncSession,
    user: User,
    now: datetime | None = None,
) -> dict:
    """Module wrapper for channel progress / lazy resolve."""
    return await BreakthroughService(session).get_channel(user, now=now)


async def resolve_channel(
    session: AsyncSession,
    user: User,
    now: datetime | None = None,
) -> dict:
    """Module wrapper for explicit channel resolve."""
    return await BreakthroughService(session).resolve_channel(user, now=now)


async def list_grade_history(
    session: AsyncSession,
    user: User,
    *,
    limit: int = 20,
) -> list[dict]:
    """Module wrapper delegating to ``BreakthroughService.list_grade_history``."""
    return await BreakthroughService(session).list_grade_history(user, limit=limit)


async def lazy_resolve_breakthrough_channel(
    session: AsyncSession,
    character: Character,
    *,
    now: datetime | None = None,
    user: User | None = None,
) -> dict | None:
    """
    跨服务懒结算入口（PlayGate / CharacterService 调用）。

    Args:
        session: DB session.
        character: Character entity.
        now: Optional frozen UTC.
        user: Optional owner for result envelope.

    Returns:
        dict | None: Resolved payload or None.
    """
    return await BreakthroughService(session).lazy_resolve_channel_for_character(
        character,
        now=now,
        user=user,
    )
