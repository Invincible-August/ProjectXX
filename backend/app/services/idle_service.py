"""
挂机权威入账、三向产出、离线 pending 与方向切换（M1 + M2）。

``IdleService`` 为应用服务入口；模块级函数为兼容包装。
服务端：按 ``last_settled_at`` 切片写库（无全服定时任务）。
长离线缺口走 pending/claim；有 pending 时冻结在线累计。
WS Presence 仍在线时：长缺口按离线帽直接入账，不弹「离线领取」
（避免切页/切后台停 sync 被误判为离线）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import ensure_aware_utc, now_utc, to_utc_iso
from app.db.models.character import Character
from app.db.models.user import User
from app.domain.divine_sense import backlash_idle_multiplier
from app.domain.idle import (
    PRODUCTIVE_DIRECTIONS,
    IdleGainCalculator,
    OfflinePending,
    SettleResult,
)
from app.schemas.common import AppError
from app.services.realm_config import (
    DirectionRates,
    gain_per_tick_for,
    get_game_config,
    offline_cap_hours_for_tier,
    stones_per_tick_for,
)

logger = logging.getLogger(__name__)


def _character_ws_online(character_id: int | None) -> bool:
    """
    角色是否有存活 WS（含 Presence grace）。

    失败时视为离线，避免 Presence 异常时误吞离线领取弹窗。

    Args:
        character_id: 角色主键；缺省则 False。

    Returns:
        True 表示 Hub 认为在线。
    """
    if character_id is None:
        return False
    try:
        from app.services.presence_service import get_presence

        return bool(get_presence().is_online(int(character_id)))
    except Exception:  # noqa: BLE001
        return False

# 兼容旧测试：导出 SettleResult / PRODUCTIVE 别名
_PRODUCTIVE_DIRECTIONS = PRODUCTIVE_DIRECTIONS


@dataclass
class AvatarSettleResult:
    """化身线程 settle 摘要。"""

    stalled: bool
    ticks: int
    gained_cultivation: int = 0
    gained_body: int = 0
    gained_crafting: int = 0
    spent_spirit_stones: int = 0


@dataclass
class DualSettleResult:
    """双线程 + 工坊 settle 聚合。"""

    main: SettleResult
    avatar: AvatarSettleResult | None = None
    craft_ready_ids: list[int] | None = None


class IdleService:
    """
    挂机权威结算与离线 pending 用例。

    属性:
        _session: 请求级异步会话。
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        参数:
            session: SQLAlchemy 异步会话。
        """
        self._session = session

    async def _load_avatar_row(self, character_id: int) -> Any | None:
        """按角色 id 加载化身行（轻量仓储，避免构造完整 AvatarService）。"""
        from app.services.avatar_repo import fetch_avatar_row

        return await fetch_avatar_row(self._session, character_id)

    @staticmethod
    def _direction_rates(direction: str) -> DirectionRates | None:
        """按方向取速率配置。"""
        idle = get_game_config().idle
        if direction == "spirit":
            return idle.spirit if idle.spirit.enabled else None
        if direction == "body":
            return idle.body if idle.body.enabled else None
        if direction == "crafting":
            return idle.crafting if idle.crafting.enabled else None
        return None

    @staticmethod
    def is_productive_direction(direction: str) -> bool:
        """方向是否可能产出资源（配置 enabled）。"""
        return IdleService._direction_rates(direction) is not None

    @staticmethod
    def is_currently_stalled(character: Character) -> bool:
        """
        判断当前方向是否买不起下一 tick 灵石。

        参数:
            character: 角色实体。

        返回:
            任一产出方向且灵石不足则为 True。
        """
        direction = character.idle_direction
        if direction not in PRODUCTIVE_DIRECTIONS:
            return False
        rates = IdleService._direction_rates(direction)
        if rates is None:
            return False
        stone_cost = stones_per_tick_for(character)
        return int(character.spirit_stones) < stone_cost

    @staticmethod
    def parse_offline_pending(character: Character) -> dict | None:
        """解析角色 pending_offline_json。"""
        return OfflinePending.parse_raw(character.pending_offline_json)

    def _compute_settle_gains(
        self,
        character: Character,
        *,
        max_ticks: int,
        direction: str | None = None,
    ) -> tuple[int, int, int, int, int, bool]:
        """按方向、境界基础速率与灵石计算 used ticks 与三向产出。"""
        active_direction = direction if direction is not None else character.idle_direction
        rates = self._direction_rates(active_direction)
        # A 层：按大境界查表；方向未启用则 None
        gain_per_tick = (
            gain_per_tick_for(character, active_direction) if rates is not None else None
        )
        breakdown = IdleGainCalculator.compute(
            status=character.status,
            direction=active_direction,
            spirit_stones=int(character.spirit_stones),
            max_ticks=max_ticks,
            gain_per_tick=gain_per_tick,
            stone_cost_per_tick=stones_per_tick_for(character),
        )
        return (
            breakdown.used,
            breakdown.gained_cultivation,
            breakdown.gained_body,
            breakdown.gained_crafting,
            breakdown.spent_stones,
            breakdown.stalled,
        )

    @staticmethod
    def _resolve_env_ids_at(at: datetime) -> tuple[str, str]:
        """
        Resolve (shichen_id, weather_id) at a wall-clock instant.

        Notes:
            Prefer ``_make_segment_env_resolver`` for settle loops — this
            method is the uncached fallback (one-off lookups).
        """
        from app.services.calendar_service import CalendarService
        from app.services.weather_service import WeatherService

        cal = CalendarService().get_snapshot(now=at)
        weather = WeatherService().get_snapshot(now=at)
        return str(cal["shichen_id"]), str(weather["weather_id"])

    @staticmethod
    def _make_segment_env_resolver(
        settle_now: datetime,
    ) -> Callable[[datetime], tuple[str, str]]:
        """
        Build a cheap env resolver for one settle pass.

        - Weather: frozen at ``settle_now``（历史天气不可完美重放；切段权威在时辰）。
        - Shichen: pure ``current_shichen`` formula，按 slot 桶缓存。
        - Avoids constructing Calendar/Weather services per tick.
        """
        from app.core.config import get_settings
        from app.domain.calendar_rules import current_shichen
        from app.domain.idle_segments import memoize_env_resolve
        from app.services.calendar_service import _gm_force_shichen
        from app.services.weather_service import WeatherService

        settings = get_settings()
        bundle = get_game_config()
        cal_cfg = bundle.calendar
        weather_id = str(
            WeatherService().get_snapshot(now=settle_now)["weather_id"],
        )
        slot_seconds = max(1, int(cal_cfg.slot_seconds))

        def _raw(at: datetime) -> tuple[str, str]:
            if not settings.calendar_enabled:
                return "noon", weather_id
            if _gm_force_shichen:
                return str(_gm_force_shichen), weather_id
            snap = current_shichen(
                at,
                cal_cfg.epoch_utc,
                slot_seconds=slot_seconds,
                shichen_order=cal_cfg.shichen_order,
                labels=cal_cfg.labels,
            )
            return str(snap.shichen_id), weather_id

        return memoize_env_resolve(_raw, bucket_seconds=slot_seconds)

    @staticmethod
    def _apply_env_to_gains(
        gained_cultivation: int,
        gained_body: int,
        gained_crafting: int,
        *,
        now: datetime,
        character: Character | None = None,
        env_tags: Sequence[str] | None = None,
        channel_mult: float = 1.0,
        shichen_id: str | None = None,
        weather_id: str | None = None,
    ) -> tuple[int, int, int, float]:
        """
        Apply channel×shichen×weather×tag multipliers to settle gains.

        Formula::

            effective = floor(raw_gain * channel_mult * env_mult)

        matches ``domain.env_preview`` / IdlePanel preview.

        Args:
            gained_cultivation: Raw spirit cultivation gain.
            gained_body: Raw body gain.
            gained_crafting: Raw crafting gain.
            now: Settle moment for calendar/weather lookup (fallback).
            character: Optional character for spirit_root_tags_json.
            env_tags: Optional technique/other tags (merged with spirit roots).
            channel_mult: Clamped product of enabled bonus_channels.
            shichen_id: Optional explicit segment shichen.
            weather_id: Optional explicit segment weather.

        Returns:
            tuple: Adjusted (cultivation, body, crafting) and total multiplier.
        """
        from app.core.config import get_settings
        from app.domain.env_preview import (
            parse_spirit_root_tags_json,
            resolve_idle_cultivation_mult_with_tags,
        )
        from app.services.calendar_service import CalendarService
        from app.services.env_preview_service import get_idle_tag_tables
        from app.services.weather_service import WeatherService

        settings = get_settings()
        channel = float(channel_mult) if channel_mult else 1.0

        if not settings.calendar_enabled and not settings.weather_enabled:
            return (
                int(gained_cultivation * channel),
                int(gained_body * channel),
                int(gained_crafting * channel),
                channel,
            )

        if shichen_id is None or weather_id is None:
            cal = CalendarService().get_snapshot(now=now)
            weather = WeatherService().get_snapshot(now=now)
            shichen_id = str(cal["shichen_id"])
            weather_id = str(weather["weather_id"])

        bundle = get_game_config()
        shichen_table = bundle.calendar.modifiers.get("idle_cultivation") or {}
        weather_table = bundle.weather.modifiers.get("idle_cultivation") or {}

        # 合并灵根 JSON 与调用方传入的功法 tags（去重保序）
        tags: list[str] = []
        seen: set[str] = set()
        spirit_tags = (
            parse_spirit_root_tags_json(getattr(character, "spirit_root_tags_json", None))
            if character is not None
            else []
        )
        for tag in [*spirit_tags, *(env_tags or ())]:
            if tag and tag not in seen:
                seen.add(tag)
                tags.append(tag)

        shichen_tag_table, weather_tag_table = get_idle_tag_tables()
        env_mult = resolve_idle_cultivation_mult_with_tags(
            shichen_id=str(shichen_id),
            weather_id=str(weather_id),
            shichen_table=shichen_table if settings.calendar_enabled else None,
            weather_table=weather_table if settings.weather_enabled else None,
            tags=tags,
            shichen_tag_table=shichen_tag_table,
            weather_tag_table=weather_tag_table,
            clamp_min=min(bundle.calendar.clamp_min, bundle.weather.clamp_min),
            clamp_max=max(bundle.calendar.clamp_max, bundle.weather.clamp_max),
        )
        total = float(channel) * float(env_mult)
        return (
            int(gained_cultivation * total),
            int(gained_body * total),
            int(gained_crafting * total),
            total,
        )

    @staticmethod
    def _apply_gains_to_character(
        character: Character,
        *,
        used: int,
        gained_cultivation: int,
        gained_body: int,
        gained_crafting: int,
        spent_stones: int,
        last: datetime,
        tick: int,
    ) -> None:
        """将结算结果写入角色并推进锚点。"""
        if used > 0:
            character.cultivation_points = int(character.cultivation_points) + gained_cultivation
            character.body_tempering_points = int(character.body_tempering_points) + gained_body
            character.crafting_exp = int(character.crafting_exp) + gained_crafting
            character.spirit_stones = int(character.spirit_stones) - spent_stones
            character.last_settled_at = last + timedelta(seconds=used * tick)

    def _settle_segmented_gains(
        self,
        character: Character,
        *,
        last: datetime,
        max_ticks: int,
        tick: int,
        now: datetime,
        env_tags: Sequence[str] | None = None,
        channel_mult: float = 1.0,
        apply_to_character: bool = True,
    ) -> tuple[int, int, int, int, int, bool, list[dict[str, Any]]]:
        """
        Compute (and optionally apply) settle gains with per-segment env mults.

        Args:
            character: Mutable character (stones/pools updated when applying).
            last: Settle anchor.
            max_ticks: Complete ticks in the window.
            tick: Tick length seconds.
            now: Wall clock for fallback env lookup.
            env_tags: Optional technique tags.
            channel_mult: Bonus channel product.
            apply_to_character: When True, write pools/stones/last_settled_at.

        Returns:
            tuple: used, gc, gb, gcr, spent, stalled, segments.
        """
        from app.core.time_utils import to_utc_iso
        from app.domain.display_labels import label_zh_or_unknown
        from app.domain.idle_segments import group_ticks_by_env

        resolve_env = self._make_segment_env_resolver(now)
        groups = group_ticks_by_env(
            last,
            max_ticks,
            tick,
            resolve_env=resolve_env,
        )
        if not groups:
            return 0, 0, 0, 0, 0, False, []

        # 一次取 bundle labels，段摘要带中文（§0.0.2）
        bundle = get_game_config()
        cal_labels = bundle.calendar.labels
        wx_labels = bundle.weather.labels

        total_used = 0
        total_gc = 0
        total_gb = 0
        total_gcr = 0
        total_spent = 0
        stalled = False
        segments: list[dict[str, Any]] = []
        cursor = last
        # 离线 pending 不入池、不扣石；用虚拟灵石预算串联各段
        virtual_stones = int(character.spirit_stones)

        for group in groups:
            saved_stones = int(character.spirit_stones)
            if not apply_to_character:
                character.spirit_stones = virtual_stones
            used, gc_raw, gb_raw, gcr_raw, spent, stalled = self._compute_settle_gains(
                character,
                max_ticks=group.tick_count,
            )
            if not apply_to_character:
                character.spirit_stones = saved_stones
            gc, gb, gcr, env_mult = self._apply_env_to_gains(
                gc_raw,
                gb_raw,
                gcr_raw,
                now=now,
                character=character,
                env_tags=env_tags,
                channel_mult=channel_mult,
                shichen_id=group.shichen_id,
                weather_id=group.weather_id,
            )
            segments.append(
                {
                    "shichen": group.shichen_id,
                    "shichen_label": label_zh_or_unknown(
                        group.shichen_id,
                        cal_labels,
                    ),
                    "weather": group.weather_id,
                    "weather_label": label_zh_or_unknown(
                        group.weather_id,
                        wx_labels,
                    ),
                    "ticks": used,
                    "seconds": used * tick,
                    "env_mult": env_mult,
                    "cultivation": gc,
                    "body": gb,
                    "crafting": gcr,
                    "spent_spirit_stones": spent,
                    "from": to_utc_iso(cursor),
                    "to": to_utc_iso(cursor + timedelta(seconds=used * tick)),
                },
            )
            if apply_to_character and used > 0:
                self._apply_gains_to_character(
                    character,
                    used=used,
                    gained_cultivation=gc,
                    gained_body=gb,
                    gained_crafting=gcr,
                    spent_stones=spent,
                    last=cursor,
                    tick=tick,
                )
                cursor = ensure_aware_utc(character.last_settled_at)
            else:
                virtual_stones = max(0, virtual_stones - spent)
                cursor = cursor + timedelta(seconds=used * tick)

            total_used += used
            total_gc += gc
            total_gb += gb
            total_gcr += gcr
            total_spent += spent
            if used < group.tick_count or stalled:
                break

        return total_used, total_gc, total_gb, total_gcr, total_spent, stalled, segments

    def settle(
        self,
        character: Character,
        now: datetime | None = None,
        *,
        env_tags: Sequence[str] | None = None,
        channel_mult: float = 1.0,
    ) -> SettleResult:
        """
        按 ``last_settled_at`` 切片结算挂机（同步写角色字段，调用方负责 commit）。

        有 ``pending_offline_json`` 时不累计（调用方应先走 offline 逻辑）。

        参数:
            character: 可变角色实体。
            now: 结算时刻（UTC）。
            env_tags: 可选功法等环境标签；与灵根 JSON 合并后参与乘区。
            channel_mult: 已钳制的 bonus_channels 乘积（异步路径先 resolve）。

        返回:
            ticks / 收支 / 是否停滞。
        """
        if character.pending_offline_json:
            return SettleResult(stalled=False, ticks=0)

        now_aware = now_utc(now)
        last = ensure_aware_utc(character.last_settled_at)

        if last > now_aware:
            character.last_settled_at = now_aware
            return SettleResult(stalled=False, ticks=0)

        idle = get_game_config().idle
        tick = idle.tick_seconds
        elapsed = (now_aware - last).total_seconds()
        max_ticks = int(elapsed // tick)
        if max_ticks <= 0:
            return SettleResult(stalled=self.is_currently_stalled(character), ticks=0)

        direction = character.idle_direction
        # 采矿挂机由 SectFacilityService.settle_mining_character 权威结算；
        # 同步 settle 不推进锚点，避免吞掉采矿 tick。
        if direction == "sect_mining":
            return SettleResult(stalled=False, ticks=0, advanced_only=True)
        # 非产出方向：零产出零消耗，仍推进锚点
        if character.status != "normal" or direction not in PRODUCTIVE_DIRECTIONS:
            stalled_status = character.status in ("awaiting_ferry", "reincarnating")
            character.last_settled_at = last + timedelta(seconds=max_ticks * tick)
            return SettleResult(
                stalled=stalled_status,
                ticks=0,
                advanced_only=True,
            )

        rates = self._direction_rates(direction)
        if rates is None:
            character.last_settled_at = last + timedelta(seconds=max_ticks * tick)
            return SettleResult(stalled=False, ticks=0, advanced_only=True)

        # M5-D11：按时辰/天气切段乘区后汇总入账
        used, gc, gb, gcr, spent, stalled, segments = self._settle_segmented_gains(
            character,
            last=last,
            max_ticks=max_ticks,
            tick=tick,
            now=now_aware,
            env_tags=env_tags,
            channel_mult=channel_mult,
            apply_to_character=True,
        )

        final_stalled = stalled or self.is_currently_stalled(character)
        logger.debug(
            "settle_idle character_id=%s ticks=%s dir=%s stalled=%s channel=%s segments=%s",
            character.id,
            used,
            direction,
            final_stalled,
            channel_mult,
            len(segments),
        )
        return SettleResult(
            stalled=final_stalled,
            ticks=used,
            gained_cultivation=gc,
            gained_body=gb,
            gained_crafting=gcr,
            spent_spirit_stones=spent,
            segments=segments,
        )

    @staticmethod
    def _avatar_direction_rates(direction: str) -> tuple[int | None, bool]:
        """化身方向速率（avatar.yaml）。"""
        avatar_cfg = get_game_config().avatar
        if direction == "spirit":
            return avatar_cfg.spirit_rates.gain_per_tick, True
        if direction == "body":
            if not avatar_cfg.body_rates.enabled:
                return None, False
            return avatar_cfg.body_rates.gain_per_tick, True
        if direction == "crafting":
            return avatar_cfg.crafting_rates.gain_per_tick, True
        return None, False

    def _avatar_gain_breakdown(
        self,
        character: Character,
        avatar: Any,
        *,
        max_ticks: int,
        spirit_stones: int,
    ) -> AvatarSettleResult:
        """
        化身线程干跑：按共享 tick 窗与给定灵石预算计算产出（不写库）。

        参数:
            character: 本体（用于境界耗石曲线与反噬标记）。
            avatar: 化身 ORM。
            max_ticks: 角色级离线帽共享的有效 tick 上限。
            spirit_stones: 可用于本线程的灵石预算（本体优先扣完后的剩余）。
        """
        from app.db.models.avatar import Avatar

        if not isinstance(avatar, Avatar) or max_ticks <= 0:
            return AvatarSettleResult(stalled=False, ticks=0)

        direction = avatar.idle_direction
        if avatar.status == "disabled" or direction not in PRODUCTIVE_DIRECTIONS:
            return AvatarSettleResult(stalled=False, ticks=0)

        gain_per_tick, enabled = self._avatar_direction_rates(direction)
        if not enabled or gain_per_tick is None:
            return AvatarSettleResult(stalled=False, ticks=0)

        avatar_cfg = get_game_config().avatar
        ds_cfg = get_game_config().divine_sense
        # 本体筑基前免费时，化身同样不耗灵石
        base_stone = stones_per_tick_for(character)
        if base_stone <= 0:
            stone_cost = 0
        else:
            stone_cost = max(
                1,
                int(base_stone * avatar_cfg.spirit_stone_cost_per_tick_ratio),
            )
        # 反噬：严重超载时化身修炼速率 × backlash 表 idle_mult
        from app.domain.divine_sense import BacklashEntry, resolve_backlash_entry

        entry = None
        if character.divine_sense_backlash:
            entry = resolve_backlash_entry(
                over_hard=True,
                table=[
                    BacklashEntry(
                        id=t.id,
                        when=t.when,
                        idle_mult=t.idle_mult,
                        set_flag=t.set_flag,
                        summary=t.summary,
                    )
                    for t in ds_cfg.backlash_table
                ],
                fallback_idle_mult=ds_cfg.backlash_idle_mult,
            )
        backlash_mult = backlash_idle_multiplier(
            bool(character.divine_sense_backlash),
            backlash_idle_mult=ds_cfg.backlash_idle_mult,
            entry=entry,
        )
        effective_gain = max(1, int(gain_per_tick * backlash_mult))

        if stone_cost <= 0:
            used = max(0, int(max_ticks))
            stalled = False
        else:
            affordable = int(spirit_stones) // stone_cost
            used = min(max_ticks, affordable)
            stalled = affordable < max_ticks

        gc = effective_gain * used if direction == "spirit" else 0
        gb = effective_gain * used if direction == "body" else 0
        gcr = effective_gain * used if direction == "crafting" else 0
        spent = used * stone_cost
        return AvatarSettleResult(
            stalled=stalled,
            ticks=used,
            gained_cultivation=gc,
            gained_body=gb,
            gained_crafting=gcr,
            spent_spirit_stones=spent,
        )

    @staticmethod
    def _avatar_gains_dict(result: AvatarSettleResult, *, idle_direction: str) -> dict[str, Any]:
        """将化身 settle 摘要转为 pending 分列明细。"""
        return {
            "idle_direction": idle_direction,
            "settled_ticks": result.ticks,
            "gained_cultivation": result.gained_cultivation,
            "gained_body": result.gained_body,
            "gained_crafting": result.gained_crafting,
            "spent_spirit_stones": result.spent_spirit_stones,
            "is_stalled": result.stalled,
        }

    def _settle_avatar_thread(
        self,
        character: Character,
        avatar: Any,
        now: datetime | None = None,
        *,
        max_ticks: int | None = None,
    ) -> AvatarSettleResult:
        """
        化身线程惰性 settle（灵石从 character 扣；本体优先已在 main settle 后）。

        参数:
            character: 本体（灵石池）。
            avatar: 化身 ORM。
            now: 结算时刻。
            max_ticks: 可选 tick 上限（离线帽共用窗口）；缺省按化身锚点墙钟推算。
        """
        from app.db.models.avatar import Avatar

        if not isinstance(avatar, Avatar):
            return AvatarSettleResult(stalled=False, ticks=0)

        now_aware = now_utc(now)
        last = ensure_aware_utc(avatar.last_settled_at)
        if last > now_aware:
            avatar.last_settled_at = now_aware
            return AvatarSettleResult(stalled=False, ticks=0)

        idle = get_game_config().idle
        tick = idle.tick_seconds
        elapsed = (now_aware - last).total_seconds()
        calc_max = int(elapsed // tick) if max_ticks is None else max_ticks
        if calc_max <= 0:
            return AvatarSettleResult(stalled=False, ticks=0)

        direction = avatar.idle_direction
        if avatar.status == "disabled" or direction not in PRODUCTIVE_DIRECTIONS:
            avatar.last_settled_at = last + timedelta(seconds=calc_max * tick)
            return AvatarSettleResult(stalled=False, ticks=0)

        gain_per_tick, enabled = self._avatar_direction_rates(direction)
        if not enabled or gain_per_tick is None:
            avatar.last_settled_at = last + timedelta(seconds=calc_max * tick)
            return AvatarSettleResult(stalled=False, ticks=0)

        breakdown = self._avatar_gain_breakdown(
            character,
            avatar,
            max_ticks=calc_max,
            spirit_stones=int(character.spirit_stones),
        )
        if breakdown.ticks > 0:
            avatar.cultivation_points = int(avatar.cultivation_points) + breakdown.gained_cultivation
            avatar.body_tempering_points = (
                int(avatar.body_tempering_points) + breakdown.gained_body
            )
            avatar.crafting_exp = int(avatar.crafting_exp) + breakdown.gained_crafting
            character.spirit_stones = int(character.spirit_stones) - breakdown.spent_spirit_stones
            avatar.last_settled_at = last + timedelta(seconds=breakdown.ticks * tick)
        elif calc_max > 0 and breakdown.stalled:
            # 灵石不足：不推锚点，便于补石后继续结算
            pass
        return breakdown

    def settle_dual(
        self,
        character: Character,
        now: datetime | None = None,
        *,
        avatar: Any | None = None,
        max_ticks: int | None = None,
        env_tags: Sequence[str] | None = None,
        channel_mult: float = 1.0,
    ) -> DualSettleResult:
        """
        双线程 settle：本体 → 化身（同步路径，不含工坊 async settle）。

        参数:
            character: 角色。
            now: UTC 时刻。
            avatar: 可选已加载的化身行。
            max_ticks: 可选共享 tick 帽（离线 D10）；在线路径通常为 None。
            env_tags: 可选环境标签（传入本体 settle）。
            channel_mult: 本体 bonus_channels 乘积（化身暂不吃通道）。
        """
        if max_ticks is not None:
            # 共享帽窗口：本体与化身各自在该 tick 上限内产（本体优先耗石）
            main = self._settle_main_capped(character, now=now, max_ticks=max_ticks)
            av_result: AvatarSettleResult | None = None
            if avatar is not None:
                av_result = self._settle_avatar_thread(
                    character,
                    avatar,
                    now=now,
                    max_ticks=max_ticks,
                )
            return DualSettleResult(main=main, avatar=av_result)

        main = self.settle(
            character,
            now=now,
            env_tags=env_tags,
            channel_mult=channel_mult,
        )
        av_result = None
        if avatar is not None:
            av_result = self._settle_avatar_thread(character, avatar, now=now)
        return DualSettleResult(main=main, avatar=av_result)

    def _settle_main_capped(
        self,
        character: Character,
        now: datetime | None = None,
        *,
        max_ticks: int,
    ) -> SettleResult:
        """在显式 tick 上限内结算本体（用于 D10 共享窗入账；一般 pending 路径用干跑）。"""
        if character.pending_offline_json:
            return SettleResult(stalled=False, ticks=0)
        now_aware = now_utc(now)
        last = ensure_aware_utc(character.last_settled_at)
        idle = get_game_config().idle
        tick = idle.tick_seconds
        direction = character.idle_direction
        if character.status != "normal" or direction not in PRODUCTIVE_DIRECTIONS:
            character.last_settled_at = last + timedelta(seconds=max_ticks * tick)
            return SettleResult(stalled=False, ticks=0, advanced_only=True)
        rates = self._direction_rates(direction)
        if rates is None:
            character.last_settled_at = last + timedelta(seconds=max_ticks * tick)
            return SettleResult(stalled=False, ticks=0, advanced_only=True)
        used, gc, gb, gcr, spent, stalled = self._compute_settle_gains(
            character,
            max_ticks=max_ticks,
        )
        self._apply_gains_to_character(
            character,
            used=used,
            gained_cultivation=gc,
            gained_body=gb,
            gained_crafting=gcr,
            spent_stones=spent,
            last=last,
            tick=tick,
        )
        return SettleResult(
            stalled=stalled,
            ticks=used,
            gained_cultivation=gc,
            gained_body=gb,
            gained_crafting=gcr,
            spent_spirit_stones=spent,
        )

    async def settle_dual_async(
        self,
        character: Character,
        now: datetime | None = None,
    ) -> DualSettleResult:
        """双线程 settle + 工坊惰性完成（async 完整路径）。"""
        from app.services.craft_service import CraftService
        from app.services.env_preview_service import (
            load_character_env_tags,
            resolve_idle_bonus_channels,
        )

        avatar_row = await self._load_avatar_row(character.id)
        env_tags = await load_character_env_tags(self._session, character)
        channel_mult, _ = await resolve_idle_bonus_channels(self._session, character)
        dual = self.settle_dual(
            character,
            now=now,
            avatar=avatar_row,
            env_tags=env_tags,
            channel_mult=channel_mult,
        )
        # 采矿挂机：若上方 prepare 路径未走，仍保证 dual 路径结算一次
        if character.idle_direction == "sect_mining":
            from app.services.sect_facility_service import SectFacilityService

            mining = await SectFacilityService(self._session).settle_mining_character(
                character,
                now=now,
            )
            m_ticks = int(mining.get("ticks") or 0)
            dual.main.ticks = int(dual.main.ticks) + m_ticks
            dual.main.gained_mining_stones = int(mining.get("personal_stones") or 0)
            dual.main.spent_stamina = int(mining.get("spent_stamina") or 0)
            dual.main.mining_pool_stones = int(mining.get("pool_stones") or 0)
            if m_ticks > 0:
                dual.main.advanced_only = False
        # 化身采矿结算（独立于本体席位）
        if avatar_row is not None and str(getattr(avatar_row, "idle_direction", "") or "") == "sect_mining":
            from app.services.sect_facility_service import SectFacilityService

            av_mining = await SectFacilityService(self._session).settle_avatar_mining(
                character,
                avatar_row,
                now=now,
            )
            av_ticks = int(av_mining.get("ticks") or 0)
            if dual.avatar is not None:
                dual.avatar.ticks = int(dual.avatar.ticks) + av_ticks
            if av_ticks > 0 and dual.main is not None:
                dual.main.gained_mining_stones = int(dual.main.gained_mining_stones or 0) + int(
                    av_mining.get("personal_stones") or 0,
                )
                dual.main.spent_stamina = int(dual.main.spent_stamina or 0) + int(
                    av_mining.get("spent_stamina") or 0,
                )
                dual.main.mining_pool_stones = int(dual.main.mining_pool_stones or 0) + int(
                    av_mining.get("pool_stones") or 0,
                )
        craft = CraftService(self._session)
        ready = await craft.settle_jobs_async(character, now=now)
        dual.craft_ready_ids = ready
        return dual

    @staticmethod
    def _write_offline_pending(
        character: Character,
        pending: dict,
        *,
        capped: bool,
        now_aware: datetime,
    ) -> None:
        """写入 pending JSON；锚点暂不推到 now。"""
        character.pending_offline_json = OfflinePending.to_json(pending)
        if capped:
            character.offline_capped_at = now_aware

    def prepare_offline_or_settle(
        self,
        character: Character,
        now: datetime | None = None,
        *,
        avatar: Any | None = None,
        env_tags: Sequence[str] | None = None,
        channel_mult: float = 1.0,
    ) -> dict | SettleResult | None:
        """
        在线短缺口 settle；长缺口写 pending 不入池。

        D10：长缺口在角色级 effective 窗口内分列 main_gains / avatar_gains；
        短缺口若传入 avatar 则双线程 settle。

        参数:
            character: 角色。
            now: 当前 UTC。
            avatar: 可选化身行（异步封装会预加载）。
            env_tags: 可选环境标签（短缺口 settle 乘区）。
            channel_mult: 短缺口 settle 的通道乘区。

        返回:
            pending 字典、本体 SettleResult，或 None（已有 pending）。
        """
        if character.pending_offline_json:
            return None

        now_aware = now_utc(now)
        last = ensure_aware_utc(character.last_settled_at)
        offline_cfg = get_game_config().offline
        elapsed = (now_aware - last).total_seconds()

        if elapsed < offline_cfg.preview_threshold_seconds:
            if avatar is not None:
                dual = self.settle_dual(
                    character,
                    now=now_aware,
                    avatar=avatar,
                    env_tags=env_tags,
                    channel_mult=channel_mult,
                )
                return dual.main
            return self.settle(
                character,
                now=now_aware,
                env_tags=env_tags,
                channel_mult=channel_mult,
            )

        idle = get_game_config().idle
        tick = idle.tick_seconds
        # M7 L8：付费会员过期惰性回落（纯内存；外层 flush）
        from app.domain.commerce_rules import apply_membership_expiry_inplace

        apply_membership_expiry_inplace(character, now=now_aware)
        cap_hours = offline_cap_hours_for_tier(character.membership_tier)
        cap_seconds = cap_hours * 3600.0
        effective = min(elapsed, cap_seconds)
        max_ticks = int(effective // tick)
        capped = elapsed > cap_seconds

        # M5-D11：离线 pending 亦按时辰切段乘环境（claim 时按汇总入账）
        used, gc, gb, gcr, spent, stalled, segments = self._settle_segmented_gains(
            character,
            last=last,
            max_ticks=max_ticks,
            tick=tick,
            now=now_aware,
            env_tags=env_tags,
            channel_mult=channel_mult,
            apply_to_character=False,
        )
        main_gains = {
            "gained_cultivation": gc,
            "gained_body": gb,
            "gained_crafting": gcr,
            "spent_spirit_stones": spent,
            "settled_ticks": used,
            "is_stalled": stalled,
            "segments": segments,
        }

        # 化身共享同一 effective tick 窗；灵石预算 = 本体扣完后剩余（本体优先）
        avatar_gains: dict[str, Any] | None = None
        avatar_spent = 0
        if avatar is not None:
            stones_left = max(0, int(character.spirit_stones) - spent)
            av_break = self._avatar_gain_breakdown(
                character,
                avatar,
                max_ticks=max_ticks,
                spirit_stones=stones_left,
            )
            avatar_gains = self._avatar_gains_dict(
                av_break,
                idle_direction=str(getattr(avatar, "idle_direction", "none")),
            )
            avatar_spent = av_break.spent_spirit_stones

        total_spent = spent + avatar_spent
        pending = OfflinePending.build_payload(
            last=last,
            used=used,
            tick=tick,
            cap_hours=cap_hours,
            wall_elapsed=elapsed,
            capped=capped,
            direction=character.idle_direction,
            gained_cultivation=gc,
            gained_body=gb,
            gained_crafting=gcr,
            spent_stones=total_spent,
            stalled=stalled,
            main_gains=main_gains,
            avatar_gains=avatar_gains,
            craft_completed=[],
            segments=segments,
        )
        self._write_offline_pending(
            character,
            pending,
            capped=capped,
            now_aware=now_aware,
        )
        logger.info(
            "offline pending created character_id=%s ticks=%s avatar_ticks=%s capped=%s",
            character.id,
            used,
            avatar_gains.get("settled_ticks") if avatar_gains else 0,
            capped,
        )
        # 仍连着玩法壳 WS：长缺口视为「在线漏同步」，带帽直接入账，不卡领取弹窗
        if _character_ws_online(getattr(character, "id", None)):
            applied = self.claim_offline_pending(
                character,
                now=now_aware,
                avatar=avatar,
            )
            av_ticks = 0
            if isinstance(avatar_gains, dict):
                av_ticks = int(avatar_gains.get("settled_ticks") or 0)
            logger.info(
                "offline auto-settled while online character_id=%s ticks=%s "
                "avatar_ticks=%s capped=%s",
                character.id,
                applied.get("settled_ticks"),
                av_ticks,
                capped,
            )
            main = applied.get("main_gains") or applied
            return SettleResult(
                stalled=bool(main.get("is_stalled", applied.get("is_stalled"))),
                ticks=int(main.get("settled_ticks", applied.get("settled_ticks") or 0)),
                gained_cultivation=int(
                    main.get("gained_cultivation", applied.get("gained_cultivation") or 0),
                ),
                gained_body=int(main.get("gained_body", applied.get("gained_body") or 0)),
                gained_crafting=int(
                    main.get("gained_crafting", applied.get("gained_crafting") or 0),
                ),
                spent_spirit_stones=int(applied.get("spent_spirit_stones") or 0),
            )
        return pending

    async def prepare_offline_or_settle_async(
        self,
        character: Character,
        now: datetime | None = None,
    ) -> dict | SettleResult | None:
        """异步封装：预加载化身、环境标签与加成通道后执行 prepare_offline_or_settle。"""
        from app.services.env_preview_service import (
            load_character_env_tags,
            resolve_idle_bonus_channels,
        )

        avatar = await self._load_avatar_row(character.id)
        env_tags = await load_character_env_tags(self._session, character)
        channel_mult, _ = await resolve_idle_bonus_channels(self._session, character)
        result = self.prepare_offline_or_settle(
            character,
            now=now,
            avatar=avatar,
            env_tags=env_tags,
            channel_mult=channel_mult,
        )
        # sync / 切方向共用此路径：采矿须在 async 侧结算体力与个人灵石
        if character.idle_direction == "sect_mining":
            from app.services.sect_facility_service import SectFacilityService

            mining = await SectFacilityService(self._session).settle_mining_character(
                character,
                now=now,
            )
            if isinstance(result, SettleResult):
                m_ticks = int(mining.get("ticks") or 0)
                result.ticks = int(result.ticks) + m_ticks
                result.gained_mining_stones = int(mining.get("personal_stones") or 0)
                result.spent_stamina = int(mining.get("spent_stamina") or 0)
                result.mining_pool_stones = int(mining.get("pool_stones") or 0)
                if m_ticks > 0:
                    result.advanced_only = False
        if avatar is not None and str(getattr(avatar, "idle_direction", "") or "") == "sect_mining":
            from app.services.sect_facility_service import SectFacilityService

            av_mining = await SectFacilityService(self._session).settle_avatar_mining(
                character,
                avatar,
                now=now,
            )
            if isinstance(result, SettleResult):
                av_ticks = int(av_mining.get("ticks") or 0)
                result.ticks = int(result.ticks) + av_ticks
                result.gained_mining_stones = int(result.gained_mining_stones or 0) + int(
                    av_mining.get("personal_stones") or 0,
                )
                result.spent_stamina = int(result.spent_stamina or 0) + int(
                    av_mining.get("spent_stamina") or 0,
                )
                result.mining_pool_stones = int(result.mining_pool_stones or 0) + int(
                    av_mining.get("pool_stones") or 0,
                )
                if av_ticks > 0:
                    result.advanced_only = False
        return result
    def ensure_offline_pending(
        self,
        character: Character,
        now: datetime | None = None,
        *,
        avatar: Any | None = None,
    ) -> dict | None:
        """
        确保离线逻辑已处理：短缺口 settle，长缺口写 pending。

        参数:
            character: 角色。
            now: 当前 UTC。
            avatar: 可选化身（建议走 async 封装以覆盖 D10）。

        返回:
            若存在或新生成 pending 则返回明细。
        """
        if character.pending_offline_json:
            return self.parse_offline_pending(character)
        result = self.prepare_offline_or_settle(character, now=now, avatar=avatar)
        if isinstance(result, dict):
            return result
        return None

    async def ensure_offline_pending_async(
        self,
        character: Character,
        now: datetime | None = None,
    ) -> dict | None:
        """异步 ensure：含化身分列 pending（D10）。"""
        if character.pending_offline_json:
            return self.parse_offline_pending(character)
        result = await self.prepare_offline_or_settle_async(character, now=now)
        if isinstance(result, dict):
            return result
        return None

    def claim_offline_pending(
        self,
        character: Character,
        now: datetime | None = None,
        *,
        avatar: Any | None = None,
    ) -> dict:
        """
        领取 pending：入池、扣石、清 pending、推进锚点。

        异常:
            AppError: 40031 无 pending；40038 灵石不足以支付 pending 消耗。
        """
        pending = self.parse_offline_pending(character)
        if pending is None:
            raise AppError(code=40031, message="无待领取离线收益", http_status=400)

        now_aware = now_utc(now)
        offline_cfg = get_game_config().offline
        spent_stones = int(pending.get("spent_spirit_stones", 0))
        if int(character.spirit_stones) < spent_stones:
            raise AppError(
                code=40038,
                message="灵石不足以支付离线结算消耗，请先获取灵石后再领取",
                http_status=400,
            )

        main_gains = pending.get("main_gains") or {}
        character.cultivation_points = int(character.cultivation_points) + int(
            main_gains.get("gained_cultivation", pending.get("gained_cultivation", 0)),
        )
        character.body_tempering_points = int(character.body_tempering_points) + int(
            main_gains.get("gained_body", pending.get("gained_body", 0)),
        )
        character.crafting_exp = int(character.crafting_exp) + int(
            main_gains.get("gained_crafting", pending.get("gained_crafting", 0)),
        )
        character.spirit_stones = int(character.spirit_stones) - spent_stones

        # 化身分列入账（D10）
        avatar_gains = pending.get("avatar_gains")
        if isinstance(avatar_gains, dict) and avatar is not None:
            avatar.cultivation_points = int(avatar.cultivation_points) + int(
                avatar_gains.get("gained_cultivation", 0),
            )
            avatar.body_tempering_points = int(avatar.body_tempering_points) + int(
                avatar_gains.get("gained_body", 0),
            )
            avatar.crafting_exp = int(avatar.crafting_exp) + int(
                avatar_gains.get("gained_crafting", 0),
            )

        if offline_cfg.discard_over_cap_wall_time:
            character.last_settled_at = now_aware
            if avatar is not None:
                avatar.last_settled_at = now_aware
        else:
            to_effective = pending.get("to_effective")
            if to_effective:
                effective_at = datetime.fromisoformat(
                    to_effective.replace("Z", "+00:00"),
                )
                character.last_settled_at = effective_at
                if avatar is not None:
                    avatar.last_settled_at = effective_at
            else:
                character.last_settled_at = now_aware
                if avatar is not None:
                    avatar.last_settled_at = now_aware

        character.pending_offline_json = None
        applied = dict(pending)
        from app.domain.event_logs import take_pending_event_logs

        event_logs = take_pending_event_logs(character)
        if event_logs:
            applied["event_logs"] = event_logs
        logger.info(
            "offline claimed character_id=%s ticks=%s avatar_ticks=%s",
            character.id,
            pending.get("settled_ticks"),
            (avatar_gains or {}).get("settled_ticks") if isinstance(avatar_gains, dict) else 0,
        )
        return applied

    async def claim_offline_pending_async(
        self,
        character: Character,
        now: datetime | None = None,
    ) -> dict:
        """异步领取：若 pending 含 avatar_gains 则加载化身行一并入账。"""
        pending = self.parse_offline_pending(character)
        avatar = None
        if pending and pending.get("avatar_gains") is not None:
            avatar = await self._load_avatar_row(character.id)
        return self.claim_offline_pending(character, now=now, avatar=avatar)

    async def resolve_pending_before_play(
        self,
        character: Character,
        now: datetime | None = None,
    ) -> dict | None:
        """突破/战斗/分配前自动 claim pending；短缺口走双线程 settle。"""
        if not character.pending_offline_json:
            await self.ensure_offline_pending_async(character, now=now)
            if character.pending_offline_json:
                applied = await self.claim_offline_pending_async(character, now=now)
                await self._session.flush()
                await self._session.refresh(character)
                return applied
            # 短缺口已在 ensure 内 settle_dual（若有化身）；再走完整 async 覆盖工坊
            await self.settle_dual_async(character, now=now)
            await self._session.flush()
            return None

        applied = await self.claim_offline_pending_async(character, now=now)
        await self._session.flush()
        await self._session.refresh(character)
        return applied

    def compute_next_tick_at(
        self,
        character: Character,
        now: datetime | None = None,
    ) -> str | None:
        """计算下一片理论到期时间（ISO UTC）。"""
        _ = now
        if character.pending_offline_json:
            return None
        if character.status != "normal" or not self.is_productive_direction(
            character.idle_direction,
        ):
            return None
        if self.is_currently_stalled(character):
            return None
        idle = get_game_config().idle
        last = ensure_aware_utc(character.last_settled_at)
        next_at = last + timedelta(seconds=idle.tick_seconds)
        return to_utc_iso(next_at)

    async def settle_result_to_payload(
        self,
        settle: SettleResult,
        character: Character,
    ) -> dict:
        """将结算摘要与最新角色拼成 idle API 响应 data。"""
        from app.services.character_service import CharacterService

        characters = CharacterService(self._session)
        pending = self.parse_offline_pending(character)
        public = await characters.enrich_public(
            character,
            offline_pending=pending,
        )
        payload: dict[str, Any] = {
            "character": characters.public_to_dict(public),
            "settled_ticks": settle.ticks,
            "gained_cultivation": settle.gained_cultivation,
            "gained_body": settle.gained_body,
            "gained_crafting": settle.gained_crafting,
            "spent_spirit_stones": settle.spent_spirit_stones,
            "gained_mining_stones": settle.gained_mining_stones,
            "spent_stamina": settle.spent_stamina,
            "mining_pool_stones": settle.mining_pool_stones,
            "next_tick_at": self.compute_next_tick_at(character),
        }
        if pending is not None:
            payload["offline_pending"] = pending
        return payload

    async def _frozen_pending_payload(
        self,
        character: Character,
        *,
        settle: SettleResult | None = None,
    ) -> dict:
        """有 pending 时返回冻结在线累计的 idle 响应。"""
        from app.services.character_service import CharacterService

        characters = CharacterService(self._session)
        pending = self.parse_offline_pending(character)
        public = await characters.enrich_public(
            character,
            offline_pending=pending,
        )
        return {
            "character": characters.public_to_dict(public),
            "settled_ticks": settle.ticks if settle else 0,
            "gained_cultivation": settle.gained_cultivation if settle else 0,
            "gained_body": settle.gained_body if settle else 0,
            "gained_crafting": settle.gained_crafting if settle else 0,
            "spent_spirit_stones": settle.spent_spirit_stones if settle else 0,
            "gained_mining_stones": settle.gained_mining_stones if settle else 0,
            "spent_stamina": settle.spent_stamina if settle else 0,
            "mining_pool_stones": settle.mining_pool_stones if settle else 0,
            "next_tick_at": None,
            "offline_pending": pending,
        }

    async def require_character(self, user: User) -> Character:
        """加载当前用户角色；无角色 → ``40005``。"""
        from app.services.character_service import CharacterService

        character = await CharacterService(self._session).get_by_user_id(user.id)
        if character is None:
            raise AppError(code=40005, message="尚未创建角色", http_status=404)
        return character

    async def set_direction(
        self,
        user: User,
        direction: str,
        now: datetime | None = None,
    ) -> dict:
        """切换挂机方向：先 prepare_offline_or_settle（帽优先），再校验，再写入。"""
        character = await self.require_character(user)
        if character.pending_offline_json:
            raise AppError(code=40030, message="存在未领取离线收益，请先领取", http_status=400)

        prepared = await self.prepare_offline_or_settle_async(character, now=now)
        if isinstance(prepared, dict) or character.pending_offline_json:
            await self._session.flush()
            raise AppError(code=40030, message="存在未领取离线收益，请先领取", http_status=400)

        settle = (
            prepared if isinstance(prepared, SettleResult) else SettleResult(stalled=False, ticks=0)
        )

        if character.status != "normal":
            # 渡劫中禁止改本体挂机方向
            if character.status == "tribulation":
                raise AppError(
                    code=40061,
                    message="渡劫中禁止改本体挂机方向",
                    http_status=409,
                )
            raise AppError(
                code=40022,
                message="当前状态不可切换挂机方向",
                http_status=409,
            )

        allowed = {"none", "spirit", "body", "crafting"}
        if direction not in allowed:
            raise AppError(
                code=40000,
                message="无效的挂机方向（采矿请走宗门矿脉入口）",
                http_status=400,
            )

        # 活动互斥：进入修炼前先 settle 工坊到期任务；停修炼走 STOP_IDLE
        from app.domain.activity_mutex import Activity
        from app.services.craft_service import CraftService
        from app.services.play_gate import PlayGate

        gate = PlayGate(self._session)
        if direction != "none":
            await CraftService(self._session).settle_jobs_async(character, now=now)
        await gate.assert_activity(
            character,
            Activity.STOP_IDLE if direction == "none" else Activity.ENTER_IDLE,
        )

        idle = get_game_config().idle
        if direction == "body" and not idle.body.enabled:
            raise AppError(code=40020, message="炼体挂机未开放", http_status=400)
        if direction == "crafting" and not idle.crafting.enabled:
            raise AppError(code=40020, message="制造业挂机未开放", http_status=400)

        # 离开采矿挂机时释放矿脉席位
        if character.idle_direction == "sect_mining" and direction != "sect_mining":
            from app.services.sect_facility_service import SectFacilityService

            await SectFacilityService(self._session).settle_mining_character(
                character,
                now=now,
            )
            await SectFacilityService(self._session).release_miner_slot(character)

        character.idle_direction = direction
        # 从点击切换起重新计时一整段 tick（非墙钟整分对齐）
        if direction in {"spirit", "body", "crafting"}:
            character.last_settled_at = now_utc(now)
        character.updated_at = now_utc(now)
        await self._session.flush()
        await self._session.refresh(character)

        logger.info(
            "idle direction changed character_id=%s direction=%s settled_ticks=%s",
            character.id,
            direction,
            settle.ticks,
        )
        return await self.settle_result_to_payload(settle, character)

    async def sync(self, user: User, now: datetime | None = None) -> dict:
        """惰性结算或冻结 pending 并返回最新角色。"""
        character = await self.require_character(user)
        if character.pending_offline_json:
            return await self._frozen_pending_payload(character)

        prepared = await self.prepare_offline_or_settle_async(character, now=now)
        if isinstance(prepared, dict) or character.pending_offline_json:
            await self._session.flush()
            await self._session.refresh(character)
            return await self._frozen_pending_payload(character)

        settle = (
            prepared if isinstance(prepared, SettleResult) else SettleResult(stalled=False, ticks=0)
        )
        if settle.ticks > 0 or settle.advanced_only:
            character.updated_at = now_utc(now)
            await self._session.flush()
            await self._session.refresh(character)
        return await self.settle_result_to_payload(settle, character)

    async def preview_offline(self, user: User, now: datetime | None = None) -> dict:
        """离线预览：幂等生成 pending 并返回明细。"""
        from app.services.character_service import CharacterService

        characters = CharacterService(self._session)
        character = await self.require_character(user)
        pending = await self.ensure_offline_pending_async(character, now=now)
        await self._session.flush()
        await self._session.refresh(character)
        public = await characters.enrich_public(character, offline_pending=pending)
        return {
            "has_pending": pending is not None,
            "pending": pending,
            "character": characters.public_to_dict(public),
        }

    async def claim_offline(self, user: User, now: datetime | None = None) -> dict:
        """领取离线 pending。"""
        from app.services.character_service import CharacterService

        characters = CharacterService(self._session)
        character = await self.require_character(user)
        applied = await self.claim_offline_pending_async(character, now=now)
        character.updated_at = now_utc(now)
        await self._session.flush()
        await self._session.refresh(character)
        public = await characters.enrich_public(character)
        return {
            "applied": applied,
            "event_logs": list(applied.get("event_logs") or []),
            "character": characters.public_to_dict(public),
            "next_tick_at": self.compute_next_tick_at(character),
        }


# ---------------------------------------------------------------------------
# 兼容包装：保持旧 import 路径与函数签名
# ---------------------------------------------------------------------------


def is_productive_direction(direction: str) -> bool:
    """兼容包装。"""
    return IdleService.is_productive_direction(direction)


def is_currently_stalled(character: Character) -> bool:
    """兼容包装。"""
    return IdleService.is_currently_stalled(character)


def parse_offline_pending(character: Character) -> dict | None:
    """兼容包装。"""
    return IdleService.parse_offline_pending(character)


def settle_idle(character: Character, now: datetime | None = None) -> SettleResult:
    """
    兼容包装：无 session 的同步 settle。

    使用占位 session=None 不安全，因此直接走无 IO 的静态逻辑路径：
    实例化时传入的 session 仅用于 async 方法；settle 本身不读 session。
    """
    # settle 不触碰 session；用 object.__new__ 绕过依赖注入
    service = object.__new__(IdleService)
    service._session = None  # type: ignore[assignment]
    return IdleService.settle(service, character, now=now)


def prepare_offline_or_settle(
    character: Character,
    now: datetime | None = None,
) -> dict | SettleResult | None:
    """兼容包装。"""
    service = object.__new__(IdleService)
    service._session = None  # type: ignore[assignment]
    return IdleService.prepare_offline_or_settle(service, character, now=now)


def ensure_offline_pending(
    character: Character,
    now: datetime | None = None,
) -> dict | None:
    """兼容包装。"""
    service = object.__new__(IdleService)
    service._session = None  # type: ignore[assignment]
    return IdleService.ensure_offline_pending(service, character, now=now)


def claim_offline_pending(
    character: Character,
    now: datetime | None = None,
) -> dict:
    """兼容包装。"""
    service = object.__new__(IdleService)
    service._session = None  # type: ignore[assignment]
    return IdleService.claim_offline_pending(service, character, now=now)


async def resolve_pending_before_play(
    session: AsyncSession,
    character: Character,
    now: datetime | None = None,
) -> dict | None:
    """兼容包装。"""
    return await IdleService(session).resolve_pending_before_play(character, now=now)


def compute_next_tick_at(
    character: Character,
    now: datetime | None = None,
) -> str | None:
    """兼容包装。"""
    service = object.__new__(IdleService)
    service._session = None  # type: ignore[assignment]
    return IdleService.compute_next_tick_at(service, character, now=now)


async def settle_result_to_payload(
    session: AsyncSession,
    settle: SettleResult,
    character: Character,
) -> dict:
    """兼容包装。"""
    return await IdleService(session).settle_result_to_payload(settle, character)


async def require_character_for_user(session: AsyncSession, user: User) -> Character:
    """兼容包装。"""
    return await IdleService(session).require_character(user)


async def set_idle_direction(
    session: AsyncSession,
    user: User,
    direction: str,
    now: datetime | None = None,
) -> dict:
    """兼容包装。"""
    return await IdleService(session).set_direction(user, direction, now=now)


async def sync_idle(
    session: AsyncSession,
    user: User,
    now: datetime | None = None,
) -> dict:
    """兼容包装。"""
    return await IdleService(session).sync(user, now=now)


async def preview_offline(
    session: AsyncSession,
    user: User,
    now: datetime | None = None,
) -> dict:
    """兼容包装。"""
    return await IdleService(session).preview_offline(user, now=now)


async def claim_offline(
    session: AsyncSession,
    user: User,
    now: datetime | None = None,
) -> dict:
    """兼容包装。"""
    return await IdleService(session).claim_offline(user, now=now)
