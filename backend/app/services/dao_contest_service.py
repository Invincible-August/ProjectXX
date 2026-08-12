"""
道主之争赛会服务（M6-D06 P1～P4）。

P1：报名 / 日程 / 立刻开赛
P2：同道淘汰、轮空、离线判负、对阵树、EarlyRounds 战报
P3：冠军 vs 道主双模决战与更替
P4：半决/决赛/道主战直播窗、单直播槽、下场开赛清回溯
"""

from __future__ import annotations

import json
import logging
import random
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import (
    Character,
    DaoContest,
    DaoContestEntry,
    DaoContestMatch,
    DaoLordship,
    User,
)
from app.schemas.common import AppError
from app.domain.battle_presentation import BattlePlaybackPolicy
from app.services.dao_service import DaoService
from app.services.play_gate import PlayGate
from app.services.realm_config import DaoLordContestConfig, get_game_config

logger = logging.getLogger(__name__)

# 进程内单直播槽：character_id → match_id（P4）
_SPECTATE_SLOTS: dict[int, int] = {}


def _as_utc(dt: datetime) -> datetime:
    """保证 aware UTC，兼容 SQLite 读出的 naive。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_hhmm(value: str) -> tuple[int, int]:
    """解析 HH:MM。"""
    parts = str(value or "00:00").strip().split(":")
    hour = int(parts[0]) if parts else 0
    minute = int(parts[1]) if len(parts) > 1 else 0
    return max(0, min(23, hour)), max(0, min(59, minute))


def _combine_local(day: date, hhmm: str, tz: ZoneInfo | timezone) -> datetime:
    """本地日 + HH:MM → aware UTC datetime。"""
    hour, minute = _parse_hhmm(hhmm)
    local = datetime.combine(day, time(hour=hour, minute=minute), tzinfo=tz)
    return local.astimezone(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    """UTC ISO-Z。"""
    if dt is None:
        return None
    return _as_utc(dt).isoformat().replace("+00:00", "Z")


def _round_kind_for_alive(alive_count: int) -> str:
    """
    按开打前存活人数标注本轮 round_kind（人数不足则跳过空轮）。

    - 1 人：不走本函数（上层直接道主决战）
    - 2 人 → final（总决赛）
    - 3～4 人 → semi
    - 更多 → early（淘汰）
    """
    if alive_count <= 2:
        return "final"
    if alive_count <= 4:
        return "semi"
    return "early"


class DaoContestService:
    """道主之争报名、淘汰、道主决战与观战。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._gate = PlayGate(session)
        self._dao = DaoService(session)

    def _require_enabled(self) -> None:
        settings = get_settings()
        if not settings.dao_lord_enabled or not settings.dao_system_enabled:
            raise AppError(code=40094, message="道主挑战未开启", http_status=403)

    def _contest_cfg(self) -> DaoLordContestConfig:
        return get_game_config().dao_lord.contest

    def _tz(self) -> ZoneInfo | timezone:
        """解析配置时区；Windows 无 tzdata 时回退 UTC+8。"""
        name = self._contest_cfg().tz or "Asia/Shanghai"
        try:
            return ZoneInfo(name)
        except Exception:  # noqa: BLE001
            if name in ("Asia/Shanghai", "Asia/Chongqing", "PRC"):
                return timezone(timedelta(hours=8))
            logger.warning("unknown contest tz=%s; fallback UTC", name)
            return timezone.utc

    def _cycle_date_for(self, now: datetime) -> str:
        """本地时刻未到当日 fight_at → 今日；已过 → 明日。"""
        cfg = self._contest_cfg()
        tz = self._tz()
        local = now.astimezone(tz)
        fight = _combine_local(local.date(), cfg.fight_at, tz).astimezone(tz)
        day = local.date() if local < fight else local.date() + timedelta(days=1)
        return day.isoformat()

    def _schedule_bounds(self, cycle_date: str) -> tuple[datetime, datetime, datetime]:
        """返回 (registration_open_utc, registration_close_utc, fight_utc)。"""
        cfg = self._contest_cfg()
        tz = self._tz()
        day = date.fromisoformat(cycle_date)
        open_at = _combine_local(day, cfg.registration_start, tz)
        end_at = _combine_local(day, cfg.registration_end, tz)
        fight_at = _combine_local(day, cfg.fight_at, tz)
        close_at = min(end_at, fight_at)
        return open_at, close_at, fight_at

    def _in_registration_window(self, now: datetime, cycle_date: str) -> bool:
        open_at, close_at, _fight = self._schedule_bounds(cycle_date)
        return open_at <= now < close_at

    def _is_online(self, character_id: int) -> bool:
        """在线判定；dev_assume_online 仅 development 生效，生产强制看 WS。"""
        cfg = self._contest_cfg()
        settings = get_settings()
        if (
            cfg.dev_assume_online
            and settings.app_env == "development"
        ):
            return True
        try:
            from app.services.ws_hub_service import get_ws_hub

            return get_ws_hub().is_character_online(character_id)
        except Exception:  # noqa: BLE001
            return False

    async def _get_by_cycle(self, cycle_date: str) -> DaoContest | None:
        result = await self._session.execute(
            select(DaoContest).where(DaoContest.cycle_date == cycle_date),
        )
        return result.scalar_one_or_none()

    async def _purge_previous_contest_logs(self, *, keep_contest_id: int) -> None:
        """下场赛会开始时清理上场战报/直播回溯（D20）。"""
        cfg = self._contest_cfg()
        if not cfg.log_retain_until_next_contest:
            return
        result = await self._session.execute(
            select(DaoContestMatch).where(DaoContestMatch.contest_id != keep_contest_id),
        )
        cleared = 0
        for match in result.scalars().all():
            if match.report_json or match.live_started_at:
                match.report_json = None
                match.live_started_at = None
                match.live_ends_at = None
                cleared += 1
        for cid in list(_SPECTATE_SLOTS.keys()):
            mid = _SPECTATE_SLOTS.get(cid)
            if mid is None:
                continue
            row = await self._session.get(DaoContestMatch, mid)
            if row is None or row.contest_id != keep_contest_id:
                _SPECTATE_SLOTS.pop(cid, None)
        if cleared:
            await self._session.flush()
            logger.info(
                "dao contest purged prior match logs keep=%s cleared=%s",
                keep_contest_id,
                cleared,
            )

    async def _advance_if_due(self, contest: DaoContest, *, now: datetime) -> DaoContest:
        """到点或已强制开赛则关闭报名并进入擂台（或旧路径瞬间结算）。"""
        if contest.status == "registration":
            fight_at = _as_utc(contest.fight_at)
            if now < fight_at and not contest.force_started:
                return contest
            return await self._close_registration(contest, force=bool(contest.force_started))
        if contest.status in ("rsvp", "arena"):
            from app.services.dao_contest_arena import tick_arena

            await tick_arena(self, contest.id)
            refreshed = await self._session.get(DaoContest, contest.id)
            return refreshed or contest
        return contest

    async def _close_registration(
        self,
        contest: DaoContest,
        *,
        force: bool = False,
    ) -> DaoContest:
        """关闭报名：分阶段进 RSVP，或 staging 关闭时瞬间演算收口。"""
        if contest.status != "registration":
            return contest
        contest.status = "matching"
        contest.force_started = contest.force_started or force
        await self._session.flush()

        counts = await self._entry_counts(contest.id)
        total = sum(counts.values())
        if total <= 0:
            summary = {
                "phase": "cancelled",
                "message_zh": "无人报名，本场取消",
                "by_dao": counts,
                "total_entrants": 0,
                "force_started": bool(contest.force_started),
                "tracks": [],
            }
            contest.summary_json = json.dumps(summary, ensure_ascii=False)
            contest.status = "cancelled"
            contest.settled_at = datetime.now(timezone.utc)
            await self._session.commit()
            await self._broadcast_contest_state(contest, extra={"action": "settled"})
            return contest

        cfg = self._contest_cfg()
        if cfg.staging_enabled:
            from app.services.dao_contest_arena import begin_staging

            return await begin_staging(self, contest)

        tracks = await self._run_all_dao_tracks(contest)
        summary = {
            "phase": "settled",
            "message_zh": "本场道主之争已收口",
            "by_dao": counts,
            "total_entrants": total,
            "force_started": bool(contest.force_started),
            "tracks": tracks,
        }
        contest.summary_json = json.dumps(summary, ensure_ascii=False)
        contest.status = "settled"
        contest.settled_at = datetime.now(timezone.utc)
        await self._session.commit()
        logger.info(
            "dao contest settled id=%s total=%s tracks=%s force=%s",
            contest.id,
            total,
            len(tracks),
            force,
        )
        await self._broadcast_contest_state(contest, extra={"action": "settled"})
        return contest

    async def tick_arena(self, contest_id: int) -> bool:
        """推进擂台一刻（供后台任务 / HTTP 惰性驱动）。"""
        from app.services.dao_contest_arena import tick_arena as _tick

        return await _tick(self, contest_id)

    async def drain_arena(self, contest_id: int) -> DaoContest:
        """测试：快进擂台至收口。"""
        from app.services.dao_contest_arena import drain_arena as _drain

        return await _drain(self, contest_id)

    async def _broadcast_contest_state(
        self,
        contest: DaoContest,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """推送赛会状态变更（有 WS 则广播；含开赛提示供前端进准备/直播）。"""
        try:
            from app.domain.ws_protocol import TYPE_DAO_LORD_CONTEST_STATE
            from app.services.ws_hub_service import get_ws_hub
            from app.services.dao_contest_arena import load_arena_state

            match_count = (
                await self._session.execute(
                    select(func.count()).select_from(DaoContestMatch).where(
                        DaoContestMatch.contest_id == contest.id,
                    ),
                )
            ).scalar_one()
            summary: dict[str, Any] | None = None
            if contest.summary_json:
                try:
                    summary = json.loads(contest.summary_json)
                except json.JSONDecodeError:
                    summary = None
            arena = load_arena_state(contest)
            # rsvp_update 等个人动作：不把个人文案塞进全服 message_zh
            action = str((extra or {}).get("action") or arena.get("action") or "arena_phase")
            message_zh = ""
            if "message_zh" in (extra or {}):
                message_zh = str((extra or {}).get("message_zh") or "")
            elif action != "rsvp_update":
                message_zh = str(arena.get("message_zh") or "")
            if not message_zh and action != "rsvp_update":
                if contest.status == "rsvp":
                    message_zh = "道主之争已开始：请确认是否前往擂台"
                elif contest.status == "arena":
                    message_zh = "道主之争擂台进行中"
                elif contest.status == "settled":
                    message_zh = "道主之争已收口"
                elif contest.status == "cancelled":
                    message_zh = "道主之争已取消（无人报名）"
                else:
                    message_zh = "道主之争状态更新"
            payload: dict[str, Any] = {
                "contest_id": contest.id,
                "status": contest.status,
                "phase": contest.phase,
                "phase_ends_at": _iso(contest.phase_ends_at),
                "cycle_date": contest.cycle_date,
                "force_started": bool(contest.force_started),
                "match_count": int(match_count or 0),
                "message_zh": message_zh,
                "action": action,
                "tracks": (summary or {}).get("tracks") if isinstance(summary, dict) else None,
                "active_match_ids": arena.get("active_match_ids") or [],
            }
            # 透传 extra 中的定向字段（如 character_id），供前端过滤
            for key in ("character_id", "rsvp_accept", "match_id", "rsvp_seconds"):
                if extra and key in extra:
                    payload[key] = extra[key]
            if extra:
                # 已处理的键勿被空 message_zh 覆盖；rsvp_update 刻意不带个人文案
                skip = {"message_zh"} if action == "rsvp_update" else set()
                payload.update(
                    {
                        k: v
                        for k, v in extra.items()
                        if v is not None and k not in skip
                    },
                )
            await get_ws_hub().broadcast_world(TYPE_DAO_LORD_CONTEST_STATE, payload)
        except Exception:  # noqa: BLE001
            logger.debug("contest state broadcast skipped", exc_info=True)

    async def _run_all_dao_tracks(self, contest: DaoContest) -> list[dict[str, Any]]:
        """按道演算。"""
        result = await self._session.execute(
            select(DaoContestEntry).where(DaoContestEntry.contest_id == contest.id),
        )
        entries = list(result.scalars().all())
        by_dao: dict[str, list[DaoContestEntry]] = {}
        for entry in entries:
            by_dao.setdefault(entry.dao_id, []).append(entry)

        tracks: list[dict[str, Any]] = []
        for dao_id in sorted(by_dao.keys()):
            track = await self._run_dao_track(contest, dao_id, by_dao[dao_id])
            tracks.append(track)
        return tracks

    async def _run_dao_track(
        self,
        contest: DaoContest,
        dao_id: str,
        entries: list[DaoContestEntry],
    ) -> dict[str, Any]:
        """单道：淘汰出冠军 → 决战道主。"""
        ordered = sorted(entries, key=lambda e: (_as_utc(e.registered_at), e.id))
        entrant_ids = [e.character_id for e in ordered]
        entry_rank = {e.character_id: idx for idx, e in enumerate(ordered)}

        champion_id: int | None = None
        match_ids: list[int] = []

        if len(entrant_ids) == 1:
            champion_id = entrant_ids[0]
        else:
            alive = list(entrant_ids)
            round_index = 0
            rng = random.Random(f"{contest.id}:{dao_id}:{contest.cycle_date}")
            while len(alive) > 1:
                round_index += 1
                kind = _round_kind_for_alive(len(alive))
                rng.shuffle(alive)
                next_alive: list[int] = []
                slot = 0
                i = 0
                while i < len(alive):
                    if i + 1 >= len(alive):
                        bye_id = alive[i]
                        match = await self._create_finished_match(
                            contest=contest,
                            dao_id=dao_id,
                            round_kind=kind,
                            round_index=round_index,
                            bracket_slot=slot,
                            side_a=bye_id,
                            side_b=None,
                            winner=bye_id,
                            resolve_reason="bye",
                            label_zh="轮空晋级",
                            report={"summary": "奇数轮空，直接晋级", "events": []},
                        )
                        match_ids.append(match.id)
                        next_alive.append(bye_id)
                        i += 1
                        slot += 1
                        continue
                    a_id, b_id = alive[i], alive[i + 1]
                    winner, reason, label, report = await self._resolve_challenger_pair(
                        a_id,
                        b_id,
                        entry_rank=entry_rank,
                    )
                    match = await self._create_finished_match(
                        contest=contest,
                        dao_id=dao_id,
                        round_kind=kind,
                        round_index=round_index,
                        bracket_slot=slot,
                        side_a=a_id,
                        side_b=b_id,
                        winner=winner,
                        resolve_reason=reason,
                        label_zh=label,
                        report=report,
                    )
                    match_ids.append(match.id)
                    if winner is not None:
                        next_alive.append(winner)
                    i += 2
                    slot += 1
                alive = next_alive
            champion_id = alive[0] if alive else None

        lord_match_id: int | None = None
        transferred = False
        lord_result = None
        if champion_id is not None:
            lord_match, transferred, lord_result = await self._resolve_lord_match(
                contest,
                dao_id=dao_id,
                champion_id=champion_id,
            )
            if lord_match is not None:
                lord_match_id = lord_match.id
                match_ids.append(lord_match.id)

        return {
            "dao_id": dao_id,
            "dao_label": self._dao.label_of(dao_id),
            "entrant_count": len(entrant_ids),
            "champion_character_id": champion_id,
            "lord_match_id": lord_match_id,
            "lord_result": lord_result,
            "lordship_transferred": transferred,
            "match_ids": match_ids,
        }

    async def _resolve_challenger_pair(
        self,
        a_id: int,
        b_id: int,
        *,
        entry_rank: dict[int, int],
        presence_check: bool = False,
        contest: DaoContest | None = None,
    ) -> tuple[int | None, str, str, dict[str, Any]]:
        """两名挑战者对决。"""
        if presence_check and contest is not None:
            a_on = await self._is_entrant_present(contest, a_id)
            b_on = await self._is_entrant_present(contest, b_id)
        else:
            a_on = self._is_online(a_id)
            b_on = self._is_online(b_id)
        if a_on and not b_on:
            return (
                a_id,
                "offline_forfeit",
                "对手离线，判负晋级",
                {"summary": "对手离线判负", "events": [], "offline": b_id},
            )
        if b_on and not a_on:
            return (
                b_id,
                "offline_forfeit",
                "对手离线，判负晋级",
                {"summary": "对手离线判负", "events": [], "offline": a_id},
            )
        if not a_on and not b_on:
            policy = self._contest_cfg().both_offline_policy
            if policy == "double_eliminate":
                return (
                    None,
                    "double_offline",
                    "双方离线，双淘汰",
                    {"summary": "双方离线双淘汰", "events": []},
                )
            winner = a_id if entry_rank.get(a_id, 0) <= entry_rank.get(b_id, 0) else b_id
            return (
                winner,
                "double_offline",
                "双方离线，报名靠前者晋级",
                {"summary": "双方离线，按报名序号晋级", "events": [], "winner": winner},
            )

        report, winner = await self._duel_characters(attacker_id=a_id, defender_id=b_id)
        if winner is None:
            report2, winner2 = await self._duel_characters(attacker_id=b_id, defender_id=a_id)
            if winner2 is not None:
                return winner2, "battle", "对战结算", report2
            winner = a_id if entry_rank.get(a_id, 0) <= entry_rank.get(b_id, 0) else b_id
            report = {
                "summary": "战斗无法演算，按报名序号晋级",
                "events": [],
                "fallback": True,
            }
            return winner, "battle", "系统裁决晋级", report
        return winner, "battle", "对战结算", report

    async def _is_entrant_present(self, contest: DaoContest, character_id: int) -> bool:
        """报名者是否视为在席（RSVP 接受 + in_arena；DEV 假定仅 development）。"""
        cfg = self._contest_cfg()
        settings = get_settings()
        assume_online = (
            bool(cfg.dev_assume_online) and settings.app_env == "development"
        )
        entry = (
            await self._session.execute(
                select(DaoContestEntry).where(
                    DaoContestEntry.contest_id == contest.id,
                    DaoContestEntry.character_id == character_id,
                ),
            )
        ).scalar_one_or_none()
        if entry is not None:
            if entry.rsvp_status in ("declined", "timeout"):
                return False
            if entry.in_arena and entry.rsvp_status == "accepted":
                return True
            if assume_online and entry.rsvp_status == "accepted":
                return True
        if assume_online:
            return True
        return self._is_online(character_id)

    async def _duel_characters(
        self,
        *,
        attacker_id: int,
        defender_id: int,
        defender_mode: str = "live_attack",
    ) -> tuple[dict[str, Any], int | None]:
        """
        无体力扣减的赛会对决。

        默认双方开打瞬间现场读取进攻预设（对称）；
        ``defender_mode=frozen_defense_snapshot`` 时乙方用库内防守快照
        （道主离线 / 强制快照卫冕）。
        """
        from app.domain.autochess import simulate_battle
        from app.services.autochess_service import AutochessService
        from app.services.formation_service import FormationService
        from app.services.snapshot_service import SnapshotService

        auto = AutochessService(self._session)
        snapshots = SnapshotService(self._session)
        attacker = await self._session.get(Character, attacker_id)
        defender = await self._session.get(Character, defender_id)
        if attacker is None or defender is None:
            return {"summary": "角色缺失", "events": []}, None

        mode = (defender_mode or "live_attack").strip()
        if mode not in ("live_attack", "frozen_defense_snapshot"):
            mode = "live_attack"

        try:
            board = get_game_config().board
            captured_at = _iso(datetime.now(timezone.utc))

            attacker_units, attacker_formation, side_a_audit = (
                await auto.load_contest_live_attack_setup(attacker)
            )

            if mode == "frozen_defense_snapshot":
                await snapshots.ensure_snapshot(defender)
                payload = await snapshots.load_payload_for_battle(defender_id)
                defender_formation = None
                formation_id = str(payload.get("formation_id") or "none")
                if formation_id != "none":
                    formations = get_game_config().formations.formations
                    formation = formations.get(formation_id)
                    if formation is not None:
                        defender_formation = FormationService.formation_to_plain(formation)
                defender_units = auto._snapshot_defender_units(payload, board)
                side_b_audit = {
                    "character_id": defender_id,
                    "formation_id": formation_id,
                    "unit_count": len(defender_units),
                    "source": "defense_snapshot",
                }
            else:
                # 乙方与甲方同一口径：现场进攻编成，再 x 镜像到 side=1
                live_b_units, defender_formation, side_b_audit = (
                    await auto.load_contest_live_attack_setup(defender)
                )
                defender_units = auto.mirror_attack_units_to_defender_side(
                    live_b_units,
                    board,
                )

            atk_unit = attacker_units[0] if attacker_units else {}
            def_unit = defender_units[0] if defender_units else {}
            setup: dict[str, Any] = {
                "board": auto._board_plain(board),
                "units": attacker_units + defender_units,
                "attacker_formation": attacker_formation,
                "defender_formation": defender_formation,
                "counters": auto._counters_plain(),
                "layer_catalogs": auto._layer_catalogs_plain(),
                "formation_dice": {
                    "attacker_lo": int(atk_unit.get("dice_lo", 1)),
                    "attacker_hi": int(atk_unit.get("dice_hi", board.dice_sides)),
                    "defender_lo": int(def_unit.get("dice_lo", 1)),
                    "defender_hi": int(def_unit.get("dice_hi", board.dice_sides)),
                },
            }
            seed = auto._resolve_seed()
            outcome = simulate_battle(setup, seed)
            result_flag = outcome.get("result")
            # 与日常开战同源战报包，供前端棋盘回放
            full_report = AutochessService._render_report(outcome)
            summary_obj = full_report.get("summary")
            if isinstance(summary_obj, dict):
                summary_text = str(
                    summary_obj.get("winner")
                    or summary_obj.get("label")
                    or "挑战者对决结束",
                )
            else:
                summary_text = str(summary_obj or "挑战者对决结束")
            report = {
                "summary": summary_text,
                "events": list(full_report.get("events") or []),
                "detailed_log": list(full_report.get("detailed_log") or []),
                "board_text": full_report.get("board_text"),
                "schema_version": full_report.get("schema_version"),
                "winner": full_report.get("winner"),
                "rounds": full_report.get("rounds"),
                "seed": seed,
                "pvp_result": result_flag,
                "attacker_id": attacker_id,
                "defender_id": defender_id,
                "defender_mode": mode,
                # 开打瞬间编成审计（对拍锁阵前改阵是否进战）
                "live_loadouts": {
                    "captured_at": captured_at,
                    "side_a": side_a_audit,
                    "side_b": side_b_audit,
                },
                # 前端 BattleReportPlayer 直接消费
                "autochess": {
                    "mode": "pvp",
                    "result": "win" if result_flag == "win" else "lose",
                    "seed": seed,
                    "report": full_report,
                    "rewards": {"cultivation_points": 0, "spirit_stones": 0},
                    "stamina": {
                        "left": 0,
                        "cap": 0,
                        "next_point_in_seconds": 0,
                        "regen_per_minute": 0,
                    },
                },
            }
            if result_flag == "win":
                return report, attacker_id
            return report, defender_id
        except AppError as exc:
            logger.warning(
                "contest duel AppError a=%s b=%s: %s",
                attacker_id,
                defender_id,
                exc.message,
            )
            return {"summary": f"对决失败：{exc.message}", "events": []}, None
        except Exception as exc:  # noqa: BLE001
            logger.exception("contest duel error a=%s b=%s", attacker_id, defender_id)
            return {"summary": f"对决异常：{exc}", "events": []}, None

    async def _resolve_lord_match(
        self,
        contest: DaoContest,
        *,
        dao_id: str,
        champion_id: int,
        force_snapshot: bool = False,
    ) -> tuple[DaoContestMatch | None, bool, str | None]:
        """冠军 vs 现任道主（P3）。"""
        lord_row = (
            await self._session.execute(
                select(DaoLordship).where(DaoLordship.dao_id == dao_id),
            )
        ).scalar_one_or_none()
        if lord_row is None:
            match = await self._create_finished_match(
                contest=contest,
                dao_id=dao_id,
                round_kind="lord",
                round_index=0,
                bracket_slot=0,
                side_a=champion_id,
                side_b=None,
                winner=champion_id,
                resolve_reason="void",
                label_zh="无现任道主，流局（席位虚位）",
                report={"summary": "道主席位已空，本场不更替", "events": []},
                lord_defense_mode="void",
                transferred=False,
            )
            return match, False, "void_no_lord"

        lord_id = int(lord_row.character_id)
        if lord_id == champion_id:
            match = await self._create_finished_match(
                contest=contest,
                dao_id=dao_id,
                round_kind="lord",
                round_index=0,
                bracket_slot=0,
                side_a=champion_id,
                side_b=lord_id,
                winner=lord_id,
                resolve_reason="void",
                label_zh="冠军即现任道主，卫冕",
                report={"summary": "无需决战", "events": []},
                lord_defense_mode="void",
                transferred=False,
            )
            return match, False, "lord_win"

        champ_on = self._is_online(champion_id)
        lord_on = self._is_online(lord_id) and not force_snapshot
        if not champ_on:
            match = await self._create_finished_match(
                contest=contest,
                dao_id=dao_id,
                round_kind="lord",
                round_index=0,
                bracket_slot=0,
                side_a=champion_id,
                side_b=lord_id,
                winner=lord_id,
                resolve_reason="offline_forfeit",
                label_zh="挑战者离线，道主卫冕",
                report={"summary": "挑战者离线判负", "events": []},
                lord_defense_mode="snapshot" if not lord_on else "realtime",
                transferred=False,
            )
            await self._apply_challenger_cooldown(champion_id, win=False)
            return match, False, "lord_win"

        defense_mode = "snapshot" if force_snapshot or not lord_on else "realtime"
        report, winner = await self._duel_characters(
            attacker_id=champion_id,
            defender_id=lord_id,
            defender_mode=(
                "frozen_defense_snapshot"
                if defense_mode == "snapshot"
                else "live_attack"
            ),
        )
        if winner is None:
            policy = get_game_config().dao_lord.missing_snapshot_policy
            if policy == "reject":
                match = await self._create_finished_match(
                    contest=contest,
                    dao_id=dao_id,
                    round_kind="lord",
                    round_index=0,
                    bracket_slot=0,
                    side_a=champion_id,
                    side_b=lord_id,
                    winner=lord_id,
                    resolve_reason="void",
                    label_zh="无有效防守快照，本场流局，道主保留",
                    report=report or {"summary": "无快照流局", "events": []},
                    lord_defense_mode=defense_mode,
                    transferred=False,
                )
                return match, False, "void_no_snapshot"
            winner = lord_id

        transferred = winner == champion_id
        if transferred:
            await self._transfer_lordship(dao_id=dao_id, new_lord_id=champion_id)
            label = "挑战者胜，道主更替"
            result_key = "challenger_win"
        else:
            label = "道主卫冕"
            result_key = "lord_win"
        await self._apply_challenger_cooldown(champion_id, win=transferred)

        match = await self._create_finished_match(
            contest=contest,
            dao_id=dao_id,
            round_kind="lord",
            round_index=0,
            bracket_slot=0,
            side_a=champion_id,
            side_b=lord_id,
            winner=winner,
            resolve_reason="lord_realtime" if defense_mode == "realtime" else "lord_snapshot",
            label_zh=label,
            report=report,
            lord_defense_mode=defense_mode,
            transferred=transferred,
        )
        return match, transferred, result_key

    async def _resolve_lord_match_into(
        self,
        contest: DaoContest,
        match: DaoContestMatch,
        *,
        force_snapshot: bool = False,
    ) -> tuple[DaoContestMatch, bool, str | None]:
        """将 pending 道主战落成 finished + 直播窗。"""
        champion_id = match.side_a_character_id
        if champion_id is None:
            match.status = "void"
            match.resolve_reason = "void"
            match.result_label_zh = "无挑战者"
            match.finished_at = datetime.now(timezone.utc)
            return match, False, "void"
        created, transferred, result = await self._resolve_lord_match(
            contest,
            dao_id=match.dao_id,
            champion_id=int(champion_id),
            force_snapshot=force_snapshot
            or (match.lord_defense_mode == "snapshot"),
        )
        # _resolve_lord_match 会新建一行；把结果合并回 pending 行并删除新建行
        if created is not None and created.id != match.id:
            match.winner_character_id = created.winner_character_id
            match.resolve_reason = created.resolve_reason
            match.result_label_zh = created.result_label_zh
            match.report_json = created.report_json
            match.is_live_round = created.is_live_round
            match.live_started_at = created.live_started_at
            match.live_ends_at = created.live_ends_at
            match.lord_defense_mode = created.lord_defense_mode
            match.lordship_transferred = created.lordship_transferred
            match.status = "playing" if created.is_live_round else "finished"
            match.finished_at = created.finished_at
            match.loadout_locked_at = match.loadout_locked_at or datetime.now(timezone.utc)
            await self._session.delete(created)
            await self._session.flush()
            if match.is_live_round:
                await self._broadcast_match_finished(match)
            return match, transferred, result
        if created is not None:
            return created, transferred, result
        match.status = "finished"
        return match, False, result

    async def _transfer_lordship(self, *, dao_id: str, new_lord_id: int) -> None:
        """赛会更替道主席位。"""
        from app.services.dao_lord_service import DaoLordService

        lord_svc = DaoLordService(self._session)
        lord = await lord_svc._lordship(dao_id)
        if lord is None:
            return
        priv = dict(get_game_config().dao_lord.privileges_default)
        snap_id = await lord_svc._latest_snapshot_id(new_lord_id)
        lord.character_id = new_lord_id
        lord.snapshot_id = snap_id
        lord.privileges_json = json.dumps(priv, ensure_ascii=False)
        lord.claimed_at = datetime.now(timezone.utc)
        await self._session.flush()
        logger.info(
            "contest lordship transferred dao=%s new_lord=%s",
            dao_id,
            new_lord_id,
        )

    async def _apply_challenger_cooldown(self, character_id: int, *, win: bool) -> None:
        """给挑战者写冷却。"""
        row = await self._dao._get_or_create_row(character_id)
        cd = get_game_config().dao_lord.cooldown
        if win:
            sec = int(cd.get("win_seconds") or 300)
        else:
            sec = int(cd.get("lose_seconds") or 600)
        row.challenge_cooldown_until = datetime.now(timezone.utc) + timedelta(seconds=sec)
        await self._session.flush()

    def _is_dramatic_event(self, event: Any) -> bool:
        """关键节点：阵亡 / 结束 / 暴击类，直播多停顿。"""
        if not isinstance(event, dict):
            return False
        et = str(event.get("type") or event.get("event_type") or "").lower()
        if et in {"death", "battle_end", "critical", "crit", "finisher"}:
            return True
        label = str(event.get("battle_text") or event.get("label") or "")
        return any(k in label for k in ("阵亡", "击败", "暴击", "绝杀", "胜负", "结束"))

    async def _formation_lock_payload(
        self,
        *,
        side_a: int | None,
        side_b: int | None,
        side_b_snapshot: bool = False,
    ) -> dict[str, Any]:
        """选手可见的布阵锁定摘要（不含观众）。"""

        async def _name(cid: int | None) -> str | None:
            if not cid:
                return None
            ch = await self._session.get(Character, cid)
            return ch.name if ch else f"#{cid}"

        side_b_label = (
            "防守快照已锁定" if side_b_snapshot else "现场编成已锁定"
        )
        return {
            "side_a": {
                "character_id": side_a,
                "name": await _name(side_a),
                "label_zh": "现场编成已锁定",
            },
            "side_b": {
                "character_id": side_b,
                "name": await _name(side_b),
                "label_zh": side_b_label if side_b else "轮空",
            },
            "hint_zh": "布阵已锁定，开战倒计时中",
        }

    async def _build_live_pipeline(
        self,
        *,
        report: dict[str, Any],
        side_a: int | None,
        side_b: int | None,
        started_at: datetime,
    ) -> dict[str, Any]:
        """半决起直播时间轴：准备倒计时 → 对战节拍。"""
        cfg = self._contest_cfg()
        prep_s = max(3, int(cfg.live_prep_seconds))
        playback_s = max(5, int(cfg.live_playback_seconds))
        base_ms = max(100, int(cfg.live_tick_base_ms))
        dramatic_ms = max(base_ms, int(cfg.live_dramatic_pause_ms))
        prep_ends = started_at + timedelta(seconds=prep_s)
        battle_ends = prep_ends + timedelta(seconds=playback_s)

        ticks: list[dict[str, Any]] = []
        for t in range(prep_s + 1):
            rem = prep_s - t
            ticks.append(
                {
                    "seq": len(ticks),
                    "at_offset_ms": t * 1000,
                    "phase": "prep",
                    "kind": "countdown",
                    "audience": "all",
                    "remaining_seconds": rem,
                    "label_zh": (
                        "准备结束，开战！" if rem <= 0 else f"准备中 {rem} 秒"
                    ),
                },
            )
        formation = await self._formation_lock_payload(
            side_a=side_a,
            side_b=side_b,
            side_b_snapshot=str(report.get("defender_mode") or "")
            == "frozen_defense_snapshot"
            or str(
                ((report.get("live_loadouts") or {}).get("side_b") or {}).get("source")
                or "",
            )
            == "defense_snapshot",
        )
        ticks.append(
            {
                "seq": len(ticks),
                "at_offset_ms": 400,
                "phase": "prep",
                "kind": "formation_lock",
                "audience": "participants",
                "label_zh": "布阵已锁定",
                "formation": formation,
            },
        )

        raw_events = list(report.get("events") or [])
        cursor_ms = prep_s * 1000
        if not raw_events:
            ticks.append(
                {
                    "seq": len(ticks),
                    "at_offset_ms": cursor_ms + base_ms,
                    "phase": "battle",
                    "kind": "battle_event",
                    "audience": "all",
                    "label_zh": str(report.get("summary") or "对战结算"),
                    "dramatic": True,
                    "event": {"type": "summary", "battle_text": report.get("summary")},
                },
            )
        else:
            for ev in raw_events:
                dramatic = self._is_dramatic_event(ev)
                cursor_ms += dramatic_ms if dramatic else base_ms
                if isinstance(ev, dict):
                    label = str(
                        ev.get("battle_text")
                        or ev.get("label")
                        or ev.get("type")
                        or "战况",
                    )
                else:
                    label = str(ev)
                ticks.append(
                    {
                        "seq": len(ticks),
                        "at_offset_ms": cursor_ms,
                        "phase": "battle",
                        "kind": "battle_event",
                        "audience": "all",
                        "label_zh": label,
                        "dramatic": dramatic,
                        "event": ev if isinstance(ev, dict) else {"battle_text": str(ev)},
                    },
                )

        ticks.append(
            {
                "seq": len(ticks),
                "at_offset_ms": prep_s * 1000 + playback_s * 1000,
                "phase": "ended",
                "kind": "live_ended",
                "audience": "all",
                "label_zh": "直播结束",
            },
        )
        ticks.sort(key=lambda x: (int(x["at_offset_ms"]), int(x["seq"])))
        for i, tick in enumerate(ticks):
            tick["seq"] = i

        return {
            "prep_seconds": prep_s,
            "playback_seconds": playback_s,
            "started_at": _iso(started_at),
            "prep_ends_at": _iso(prep_ends),
            "battle_ends_at": _iso(battle_ends),
            "formation": formation,
            "ticks": ticks,
        }

    async def _create_pending_match(
        self,
        *,
        contest: DaoContest,
        dao_id: str,
        round_kind: str,
        round_index: int,
        bracket_slot: int,
        side_a: int | None,
        side_b: int | None,
        status: str = "pending",
        lord_defense_mode: str | None = None,
    ) -> DaoContestMatch:
        """创建未结算对阵（整备/待开打）。"""
        cfg = self._contest_cfg()
        is_live = round_kind in set(cfg.live_round_kinds)
        match = DaoContestMatch(
            contest_id=contest.id,
            dao_id=dao_id,
            round_kind=round_kind,
            round_index=round_index,
            bracket_slot=bracket_slot,
            side_a_character_id=side_a,
            side_b_character_id=side_b,
            winner_character_id=None,
            status=status,
            resolve_reason="battle",
            result_label_zh=None,
            report_json=None,
            is_live_round=is_live,
            live_started_at=None,
            live_ends_at=None,
            lord_defense_mode=lord_defense_mode,
            lordship_transferred=False,
            finished_at=None,
        )
        self._session.add(match)
        await self._session.flush()
        return match

    async def _finalize_pending_match(
        self,
        match: DaoContestMatch,
        *,
        winner: int | None,
        resolve_reason: str,
        label_zh: str,
        report: dict[str, Any],
        start_live: bool = True,
    ) -> DaoContestMatch:
        """将 pending/adjusting 对阵写入结果并可选打开直播。"""
        cfg = self._contest_cfg()
        now = datetime.now(timezone.utc)
        is_live = bool(match.is_live_round) and start_live
        report_out = dict(report)
        if is_live:
            pipeline = await self._build_live_pipeline(
                report=report_out,
                side_a=match.side_a_character_id,
                side_b=match.side_b_character_id,
                started_at=now,
            )
            report_out["live_pipeline"] = pipeline
            live_end = now + timedelta(
                seconds=int(pipeline["prep_seconds"]) + int(pipeline["playback_seconds"]),
            )
            match.live_started_at = now
            match.live_ends_at = live_end
            match.status = "playing"
        else:
            match.status = "finished"
            match.live_started_at = None
            match.live_ends_at = None
        match.winner_character_id = winner
        match.resolve_reason = resolve_reason
        match.result_label_zh = label_zh
        match.report_json = json.dumps(report_out, ensure_ascii=False)
        match.finished_at = now
        match.loadout_locked_at = match.loadout_locked_at or now
        await self._session.flush()
        await self._broadcast_match_finished(match)
        return match

    async def _create_finished_match(
        self,
        *,
        contest: DaoContest,
        dao_id: str,
        round_kind: str,
        round_index: int,
        bracket_slot: int,
        side_a: int | None,
        side_b: int | None,
        winner: int | None,
        resolve_reason: str,
        label_zh: str,
        report: dict[str, Any],
        lord_defense_mode: str | None = None,
        transferred: bool = False,
        start_live: bool | None = None,
    ) -> DaoContestMatch:
        """落库一场已结算对阵，并按需打直播窗（含准备倒计时）。"""
        cfg = self._contest_cfg()
        now = datetime.now(timezone.utc)
        is_live = round_kind in set(cfg.live_round_kinds)
        do_live = is_live if start_live is None else bool(start_live and is_live)
        live_start = now if do_live else None
        report_out = dict(report)
        if do_live:
            pipeline = await self._build_live_pipeline(
                report=report_out,
                side_a=side_a,
                side_b=side_b,
                started_at=now,
            )
            report_out["live_pipeline"] = pipeline
            live_end = now + timedelta(
                seconds=int(pipeline["prep_seconds"]) + int(pipeline["playback_seconds"]),
            )
        else:
            live_end = None
        match = DaoContestMatch(
            contest_id=contest.id,
            dao_id=dao_id,
            round_kind=round_kind,
            round_index=round_index,
            bracket_slot=bracket_slot,
            side_a_character_id=side_a,
            side_b_character_id=side_b,
            winner_character_id=winner,
            status="playing" if do_live else "finished",
            resolve_reason=resolve_reason,
            result_label_zh=label_zh,
            report_json=json.dumps(report_out, ensure_ascii=False),
            is_live_round=is_live,
            live_started_at=live_start,
            live_ends_at=live_end,
            lord_defense_mode=lord_defense_mode,
            lordship_transferred=transferred,
            finished_at=now,
        )
        self._session.add(match)
        await self._session.flush()
        await self._broadcast_match_finished(match)
        return match

    async def _broadcast_match_finished(self, match: DaoContestMatch) -> None:
        """权威结果推送。"""
        try:
            from app.domain.ws_protocol import (
                TYPE_DAO_LORD_LIVE_TICK,
                TYPE_DAO_LORD_MATCH_FINISHED,
            )
            from app.services.ws_hub_service import get_ws_hub

            hub = get_ws_hub()
            public = await self._match_public(match, include_report=False)
            room_id = f"dao_lord:match:{match.id}"
            await hub.broadcast_room(room_id, TYPE_DAO_LORD_MATCH_FINISHED, public)
            if match.is_live_round:
                await hub.broadcast_room(
                    room_id,
                    TYPE_DAO_LORD_LIVE_TICK,
                    {
                        "match_id": match.id,
                        "seq": 0,
                        "live_ends_at": _iso(match.live_ends_at),
                        "hint_zh": "直播进行中，不可跳过",
                    },
                )
        except Exception:  # noqa: BLE001
            logger.debug("match finished broadcast skipped", exc_info=True)

    async def _entry_counts(self, contest_id: int) -> dict[str, int]:
        result = await self._session.execute(
            select(DaoContestEntry.dao_id, func.count())
            .where(DaoContestEntry.contest_id == contest_id)
            .group_by(DaoContestEntry.dao_id),
        )
        return {str(dao_id): int(n) for dao_id, n in result.all()}

    async def ensure_current(self, *, now: datetime | None = None) -> DaoContest:
        """惰性确保当前周期赛会存在；到点自动收口。"""
        now = now or datetime.now(timezone.utc)
        cycle = self._cycle_date_for(now)
        contest = await self._get_by_cycle(cycle)
        if contest is None:
            open_at, close_at, fight_at = self._schedule_bounds(cycle)
            if now >= fight_at:
                latest = await self._session.execute(
                    select(DaoContest).order_by(DaoContest.id.desc()).limit(1),
                )
                existing = latest.scalar_one_or_none()
                if existing:
                    return await self._advance_if_due(existing, now=now)
            contest = DaoContest(
                cycle_date=cycle,
                status="registration",
                opened_at=max(open_at, now) if now < fight_at else open_at,
                registration_closes_at=close_at,
                fight_at=fight_at,
                force_started=False,
            )
            self._session.add(contest)
            await self._session.flush()
            await self._purge_previous_contest_logs(keep_contest_id=contest.id)
            logger.info("dao contest opened id=%s cycle=%s", contest.id, cycle)
        return await self._advance_if_due(contest, now=now)

    async def force_start(self, *, note: str | None = None) -> dict[str, Any]:
        """立刻开赛：关闭报名并进入 RSVP/擂台（或旧路径瞬间结算）。"""
        self._require_enabled()
        now = datetime.now(timezone.utc)
        contest = await self.ensure_current(now=now)
        if contest.status == "registration":
            contest.force_started = True
            await self._session.flush()
            contest = await self._close_registration(contest, force=True)
        elif contest.status in ("settled", "cancelled"):
            raise AppError(
                code=40098,
                message="本场已收口/取消。测试请先「重新开放报名」，或等下一业务日自动新开",
                http_status=400,
            )
        elif contest.status in ("rsvp", "arena", "matching"):
            raise AppError(
                code=40098,
                message=f"本场已在进行中（{contest.status}），无需再次开赛",
                http_status=400,
            )
        logger.info("dao contest force start id=%s note=%s", contest.id, note)
        return await self._public_payload(contest, character=None)

    async def reopen_for_ops(self, *, note: str | None = None) -> dict[str, Any]:
        """
        运营测试：将当前赛会重置为报名中，便于反复开赛。

        清除本场报名与对阵；延长报名/开打时刻；不改道主席位。
        仅建议在 DEV / 联调使用。
        """
        self._require_enabled()
        now = datetime.now(timezone.utc)
        contest = await self.ensure_current(now=now)
        if contest.status == "registration" and not contest.force_started:
            # 仍在报名：只刷新窗口时刻，方便继续报
            open_at, close_at, fight_at = self._schedule_bounds(contest.cycle_date)
            # 若日程已过 fight，强制把窗拉到未来 2h
            if now >= fight_at:
                close_at = now + timedelta(hours=1, minutes=50)
                fight_at = now + timedelta(hours=2)
                contest.registration_closes_at = close_at
                contest.fight_at = fight_at
                await self._session.flush()
            return await self._public_payload(
                contest,
                character=None,
                message="本场仍在报名中；已按需刷新开打时刻",
            )

        # 清报名
        entries = list(
            (
                await self._session.execute(
                    select(DaoContestEntry).where(DaoContestEntry.contest_id == contest.id),
                )
            ).scalars().all(),
        )
        for entry in entries:
            await self._session.delete(entry)

        # 清对阵
        matches = list(
            (
                await self._session.execute(
                    select(DaoContestMatch).where(DaoContestMatch.contest_id == contest.id),
                )
            ).scalars().all(),
        )
        for match in matches:
            await self._session.delete(match)

        # 清观战槽
        for cid, mid in list(_SPECTATE_SLOTS.items()):
            row = await self._session.get(DaoContestMatch, mid) if mid else None
            if row is None or row.contest_id == contest.id:
                _SPECTATE_SLOTS.pop(cid, None)

        close_at = now + timedelta(hours=1, minutes=50)
        fight_at = now + timedelta(hours=2)
        contest.status = "registration"
        contest.force_started = False
        contest.summary_json = None
        contest.settled_at = None
        contest.phase = None
        contest.phase_ends_at = None
        contest.current_round_index = 0
        contest.arena_state_json = None
        contest.registration_closes_at = close_at
        contest.fight_at = fight_at
        contest.opened_at = now
        await self._session.flush()
        await self._session.commit()
        logger.info(
            "dao contest reopened for ops id=%s note=%s",
            contest.id,
            note,
        )
        await self._broadcast_contest_state(
            contest,
            extra={
                "action": "reopened",
                "message_zh": "赛会已重新开放报名（运营重置）",
            },
        )
        return await self._public_payload(
            contest,
            character=None,
            message="已重新开放报名：可再次报名并「立刻开赛」",
        )

    async def advance_arena_for_ops(
        self,
        *,
        note: str | None = None,
        until_playing: bool = True,
    ) -> dict[str, Any]:
        """
        运营跳过等待并推进擂台：RSVP / 开赛倒计时 / 整备 / 轮间 / 直播演出。

        Args:
            note: 审计备注。
            until_playing: True 时连续跳过直到进入 ``playing``（开战演出）或收口；
                False 时只推进一个阶段。

        Returns:
            公开赛会载荷（含 ops_hints）。
        """
        self._require_enabled()
        from app.services.dao_contest_arena import (
            _as_utc,
            _iso,
            _utc_now,
            load_arena_state,
            save_arena_state,
        )

        contest = await self.ensure_current()
        if contest.status not in ("rsvp", "arena"):
            raise AppError(
                code=40098,
                message=f"当前状态 {contest.status} 不可跳过等待（须 RSVP/擂台进行中）",
                http_status=400,
            )

        steps: list[dict[str, Any]] = []
        max_steps = 24 if until_playing else 1

        for _ in range(max_steps):
            await self._session.refresh(contest)
            if contest.status in ("settled", "cancelled"):
                break
            if contest.status not in ("rsvp", "arena"):
                break

            state = load_arena_state(contest)
            phase_before = str(state.get("phase") or contest.phase or "")
            now = _utc_now()
            past = now - timedelta(seconds=1)

            # 强制到期：等待类阶段 + 演出直播窗
            contest.phase_ends_at = past
            state["phase_ends_at"] = _iso(past)
            state["action"] = "ops_skip_wait"
            state["message_zh"] = "运营已跳过等待并推进赛程"
            if phase_before == "playing":
                for mid in list(state.get("active_match_ids") or []):
                    match = await self._session.get(DaoContestMatch, int(mid))
                    if match is None:
                        continue
                    if match.live_ends_at is not None and _as_utc(match.live_ends_at) > past:
                        match.live_ends_at = past
            save_arena_state(contest, state)
            await self._session.flush()

            await self.tick_arena(contest.id)
            await self._session.refresh(contest)
            state_after = load_arena_state(contest)
            phase_after = str(state_after.get("phase") or contest.phase or "")
            steps.append(
                {
                    "from": phase_before,
                    "to": phase_after,
                    "status": contest.status,
                },
            )

            if contest.status in ("settled", "cancelled"):
                break
            if until_playing and phase_after == "playing" and phase_before != "playing":
                break
            if not until_playing:
                break
            # 已在 playing 且 until_playing：再跳一次会离开演出；停在开战即可
            if until_playing and phase_after == "playing":
                break

        logger.info(
            "dao contest ops advance id=%s note=%s steps=%s",
            contest.id,
            note,
            steps,
        )
        await self._broadcast_contest_state(
            contest,
            extra={
                "action": "ops_skip_wait",
                "message_zh": "运营已跳过等待并推进赛程",
            },
        )
        phase_now = contest.phase or (load_arena_state(contest).get("phase"))
        if contest.status == "settled":
            msg = "已跳过等待并收口本场"
        elif phase_now == "playing":
            msg = "已跳过等待，进入对战演出"
        else:
            msg = f"已跳过等待，当前阶段：{phase_now or contest.status}"
        payload = await self._public_payload(contest, character=None, message=msg)
        payload["ops_advance"] = {"steps": steps, "until_playing": until_playing}
        return payload

    async def get_current(self, user: User) -> dict[str, Any]:
        """玩家拉取本场状态。"""
        self._require_enabled()
        character = await self._gate.require_character(user)
        contest = await self.ensure_current()
        return await self._public_payload(contest, character=character)

    async def register(self, user: User) -> dict[str, Any]:
        """报名（本命道）。"""
        self._require_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        if character.status != "normal":
            raise AppError(code=40060, message="当前状态不可报名道主之争", http_status=409)
        now = datetime.now(timezone.utc)
        contest = await self.ensure_current(now=now)
        if contest.status != "registration":
            raise AppError(code=40098, message="报名已截止或不在报名期", http_status=400)
        if not self._in_registration_window(now, contest.cycle_date) and not contest.force_started:
            if now < self._schedule_bounds(contest.cycle_date)[0]:
                raise AppError(code=40098, message="报名尚未开始", http_status=400)
            if now >= _as_utc(contest.registration_closes_at):
                raise AppError(code=40098, message="报名已截止", http_status=400)

        dao_row = await self._dao._get_or_create_row(character.id)
        fate = dao_row.fate_dao_id
        if not fate:
            raise AppError(code=40088, message="须先开辟本命大道", http_status=400)
        min_lv = int(get_game_config().dao_lord.challenge_min_level)
        if int(dao_row.dao_level) < min_lv:
            raise AppError(
                code=40088,
                message=f"道等级须达到 {min_lv} 方可报名",
                http_status=400,
            )
        # SQLite 读出的 datetime 可能无 tzinfo，须与 aware now 统一后再比
        if (
            dao_row.challenge_cooldown_until
            and _as_utc(dao_row.challenge_cooldown_until) > _as_utc(now)
        ):
            raise AppError(code=40087, message="挑战冷却中，暂不可报名", http_status=400)

        lord = await self._session.execute(
            select(DaoLordship).where(DaoLordship.dao_id == fate),
        )
        lord_row = lord.scalar_one_or_none()
        if lord_row is None:
            raise AppError(
                code=40088,
                message="该道虚位以待，达标者自动就任，无需报名夺位",
                http_status=400,
            )
        if lord_row.character_id == character.id:
            raise AppError(code=40088, message="现任道主不可报名挑战本道", http_status=400)

        existing = await self._session.execute(
            select(DaoContestEntry).where(
                DaoContestEntry.contest_id == contest.id,
                DaoContestEntry.character_id == character.id,
            ),
        )
        if existing.scalar_one_or_none():
            return await self._public_payload(contest, character=character, message="已报名")

        self._session.add(
            DaoContestEntry(
                contest_id=contest.id,
                character_id=character.id,
                dao_id=fate,
            ),
        )
        await self._session.flush()
        logger.info(
            "dao contest register contest=%s character=%s dao=%s",
            contest.id,
            character.id,
            fate,
        )
        return await self._public_payload(
            contest,
            character=character,
            message=f"报名成功：{self._dao.label_of(fate)}道主之争",
        )

    async def unregister(self, user: User) -> dict[str, Any]:
        """取消报名（仅 registration）。"""
        self._require_enabled()
        character = await self._gate.require_character(user)
        contest = await self.ensure_current()
        if contest.status != "registration":
            raise AppError(code=40098, message="报名已截止，不可取消", http_status=400)
        result = await self._session.execute(
            select(DaoContestEntry).where(
                DaoContestEntry.contest_id == contest.id,
                DaoContestEntry.character_id == character.id,
            ),
        )
        row = result.scalar_one_or_none()
        if row is None:
            return await self._public_payload(contest, character=character, message="未报名")
        await self._session.delete(row)
        await self._session.flush()
        return await self._public_payload(contest, character=character, message="已取消报名")

    async def submit_rsvp(self, user: User, *, accept: bool) -> dict[str, Any]:
        """开赛 RSVP：报名者接受进擂台 / 拒绝弃权；道主拒绝→快照应战。"""
        self._require_enabled()
        character = await self._gate.require_character(user)
        # 勿走 ensure_current 的 tick：rsvp_seconds=0 时会在应答前收口
        now = datetime.now(timezone.utc)
        contest = await self._get_by_cycle(self._cycle_date_for(now))
        if contest is None:
            contest = await self.ensure_current(now=now)
        if contest.status not in ("rsvp",):
            raise AppError(code=40098, message="当前不在入席确认阶段", http_status=400)
        from app.services.dao_contest_arena import load_arena_state, save_arena_state

        state = load_arena_state(contest)
        entry = (
            await self._session.execute(
                select(DaoContestEntry).where(
                    DaoContestEntry.contest_id == contest.id,
                    DaoContestEntry.character_id == character.id,
                ),
            )
        ).scalar_one_or_none()

        # 道主 RSVP（非报名者）
        lord_rows = list(
            (
                await self._session.execute(select(DaoLordship))
            ).scalars().all(),
        )
        lord_dao_ids = [
            row.dao_id for row in lord_rows if int(row.character_id) == character.id
        ]
        message = ""
        if entry is not None:
            if entry.rsvp_status in ("accepted", "declined", "timeout"):
                return await self._public_payload(
                    contest,
                    character=character,
                    message="已确认过入席意向",
                )
            if accept:
                entry.rsvp_status = "accepted"
                entry.in_arena = True
                entry.rsvp_at = now
                message = "已确认前往擂台"
            else:
                entry.rsvp_status = "declined"
                entry.in_arena = False
                entry.rsvp_at = now
                message = "已弃权，本场不再参赛"
                tracks = dict(state.get("tracks") or {})
                track = dict(tracks.get(entry.dao_id) or {})
                alive = [int(x) for x in list(track.get("alive") or [])]
                track["alive"] = [x for x in alive if x != character.id]
                tracks[entry.dao_id] = track
                state["tracks"] = tracks
        elif lord_dao_ids:
            lord_rsvp = dict(state.get("lord_rsvp") or {})
            tracks = dict(state.get("tracks") or {})
            touched = False
            already_done = False
            for dao_id in lord_dao_ids:
                if dao_id not in lord_rsvp and dao_id not in tracks:
                    continue
                prev = lord_rsvp.get(dao_id)
                # 道主 RSVP 一次性：已应答不可再改（防反复刷快照标记）
                if prev in ("accepted", "declined", "timeout"):
                    already_done = True
                    continue
                lord_rsvp[dao_id] = "accepted" if accept else "declined"
                track = dict(tracks.get(dao_id) or {})
                if accept:
                    track.pop("lord_force_snapshot", None)
                else:
                    track["lord_force_snapshot"] = True
                tracks[dao_id] = track
                touched = True
            state["lord_rsvp"] = lord_rsvp
            state["tracks"] = tracks
            if not touched and already_done:
                message = "已确认过入席意向"
            elif accept:
                message = "已确认亲自应战"
            else:
                message = "已选择快照应战（不弃道主之位）"
        else:
            raise AppError(code=40098, message="你不是本场报名者或相关道主", http_status=400)

        save_arena_state(contest, state)
        await self._session.flush()
        # 个人确认文案只回 API；全服广播不含 message_zh，避免人人弹「已确认」
        await self._broadcast_contest_state(
            contest,
            extra={
                "action": "rsvp_update",
                "character_id": character.id,
                "rsvp_accept": bool(accept),
            },
        )
        return await self._public_payload(contest, character=character, message=message)

    async def arena_enter(self, user: User) -> dict[str, Any]:
        """进入擂台页面标记在席。"""
        self._require_enabled()
        character = await self._gate.require_character(user)
        contest = await self.ensure_current()
        entry = (
            await self._session.execute(
                select(DaoContestEntry).where(
                    DaoContestEntry.contest_id == contest.id,
                    DaoContestEntry.character_id == character.id,
                ),
            )
        ).scalar_one_or_none()
        if entry is not None and entry.rsvp_status == "accepted":
            entry.in_arena = True
            await self._session.flush()
        return await self.get_arena(user)

    async def arena_leave(self, user: User) -> dict[str, Any]:
        """
        离开擂台。

        判负完全由服务端决定：arena 进行中且本人场次为 playing/adjusting
        且配置开启时强制 leave_forfeit；客户端不可关闭判负。
        """
        self._require_enabled()
        character = await self._gate.require_character(user)
        contest = await self.ensure_current()
        may_forfeit = (
            self._contest_cfg().leave_during_playback_forfeit
            and contest.status == "arena"
            and (contest.phase or "") in ("playing", "adjust", "round_gap", "round_countdown")
        )
        if may_forfeit:
            await self._forfeit_playing_matches_for(contest, character.id)
        entry = (
            await self._session.execute(
                select(DaoContestEntry).where(
                    DaoContestEntry.contest_id == contest.id,
                    DaoContestEntry.character_id == character.id,
                ),
            )
        ).scalar_one_or_none()
        if entry is not None:
            entry.in_arena = False
            await self._session.flush()
        return await self.get_arena(user)

    async def get_arena(self, user: User) -> dict[str, Any]:
        """擂台页载荷：阶段倒计时 + 本道对阵。"""
        self._require_enabled()
        character = await self._gate.require_character(user)
        contest = await self.ensure_current()
        from app.services.dao_contest_arena import load_arena_state

        state = load_arena_state(contest)
        my_dao = None
        entry = (
            await self._session.execute(
                select(DaoContestEntry).where(
                    DaoContestEntry.contest_id == contest.id,
                    DaoContestEntry.character_id == character.id,
                ),
            )
        ).scalar_one_or_none()
        if entry:
            my_dao = entry.dao_id
        else:
            lord = (
                await self._session.execute(
                    select(DaoLordship).where(DaoLordship.character_id == character.id),
                )
            ).scalar_one_or_none()
            if lord:
                my_dao = lord.dao_id
        bracket = await self.get_bracket(user, dao_id=my_dao)
        phase = contest.phase or state.get("phase")
        # 入席确认 / 开赛倒计时 / 轮间 / 半决起整备：允许改阵装道具
        can_adjust = phase in (
            "rsvp",
            "round_countdown",
            "round_gap",
            "adjust",
        )
        active_ids = [int(x) for x in list(state.get("active_match_ids") or [])]
        my_active = None
        my_dao_active_ids: list[int] = []
        for mid in active_ids:
            m = await self._session.get(DaoContestMatch, mid)
            if m is None:
                continue
            if my_dao and m.dao_id != my_dao:
                continue
            my_dao_active_ids.append(mid)
            if character.id in {m.side_a_character_id, m.side_b_character_id}:
                if my_active is None:
                    my_active = await self._match_public(m, include_report=False)
        now = datetime.now(timezone.utc)
        ends = contest.phase_ends_at
        countdown = 0
        if ends is not None:
            countdown = max(0, int((_as_utc(ends) - now).total_seconds()))
        return {
            "contest_id": contest.id,
            "status": contest.status,
            "phase": phase,
            "phase_ends_at": _iso(ends),
            "countdown_seconds": countdown,
            # 客户端用 phase_ends_at + server_now 本地滴答，避免轮询导致双端差 1s
            "server_now": _iso(now),
            "message_zh": state.get("message_zh"),
            "action": state.get("action"),
            "dao_id": my_dao,
            "can_adjust_loadout": can_adjust,
            "in_arena": bool(entry.in_arena) if entry else False,
            "rsvp_status": entry.rsvp_status if entry else None,
            "my_active_match": my_active,
            "active_match_ids": active_ids,
            "my_dao_active_match_ids": my_dao_active_ids,
            "bracket": bracket,
            "me_character_id": character.id,
        }

    async def _forfeit_playing_matches_for(
        self,
        contest: DaoContest,
        character_id: int,
    ) -> None:
        """演出中离场：覆盖推演胜者为对手。"""
        rows = list(
            (
                await self._session.execute(
                    select(DaoContestMatch).where(
                        DaoContestMatch.contest_id == contest.id,
                        DaoContestMatch.status.in_(("playing", "adjusting")),
                    ),
                )
            ).scalars().all(),
        )
        for match in rows:
            if character_id not in {
                match.side_a_character_id,
                match.side_b_character_id,
            }:
                continue
            await self.apply_leave_forfeit(match.id, character_id)

    async def apply_leave_forfeit(self, match_id: int, character_id: int) -> dict[str, Any]:
        """
        选手离开/断线：即便推演其胜也改判负（模型 A）。

        同步写回 arena tracks.alive / champion，避免晋级树与场次胜者不一致。
        整备中若本阶段场次均已结束，立刻跳过剩余整备倒计时并推进赛程。
        """
        from app.services.dao_contest_arena import (
            load_arena_state,
            maybe_skip_adjust_after_forfeit,
            save_arena_state,
        )

        match = await self._session.get(DaoContestMatch, match_id)
        if match is None:
            raise AppError(code=40093, message="对阵不存在", http_status=404)
        if match.status not in ("playing", "adjusting", "pending"):
            return {"match_id": match_id, "changed": False}
        if not self._contest_cfg().leave_during_playback_forfeit:
            return {"match_id": match_id, "changed": False}

        if character_id == match.side_a_character_id:
            match.side_a_forfeit = True
            winner = match.side_b_character_id
        elif character_id == match.side_b_character_id:
            match.side_b_forfeit = True
            winner = match.side_a_character_id
        else:
            return {"match_id": match_id, "changed": False}

        # 双方都弃 → 双淘汰
        if match.side_a_forfeit and match.side_b_forfeit:
            winner = None
            label = "双方离场，双淘汰"
        else:
            label = "选手离场，判负"

        match.presence_override = True
        match.winner_character_id = winner
        match.resolve_reason = "leave_forfeit"
        match.result_label_zh = label
        match.status = "finished"
        match.finished_at = datetime.now(timezone.utc)
        # 缩短直播窗，便于调度继续
        match.live_ends_at = datetime.now(timezone.utc)
        report = self._parse_report(match)
        report["presence_override"] = True
        report["leave_forfeit_character_id"] = character_id
        report["summary"] = label
        match.report_json = json.dumps(report, ensure_ascii=False)

        # 权威晋级态：与场次胜者对齐（整备中离场 / 演出中离场均须写回）
        contest = await self._session.get(DaoContest, match.contest_id)
        if contest is not None:
            state = load_arena_state(contest)
            tracks = dict(state.get("tracks") or {})
            track = dict(tracks.get(match.dao_id) or {})
            if match.round_kind == "lord":
                track["lord_done"] = True
                track["done"] = True
                track["lord_result"] = "leave_forfeit"
                # 挑战者离场 → 道主保住；道主离场 → 挑战者夺位语义由 winner 表示
                transferred = bool(
                    winner
                    and match.side_a_character_id
                    and int(winner) == int(match.side_a_character_id)
                )
                track["lordship_transferred"] = transferred
                if winner:
                    track["champion_id"] = int(winner)
                # 道主战离场：若挑战者胜，需真正更替席位
                if transferred and match.side_a_character_id:
                    await self._apply_lordship_from_leave_forfeit(match)
            else:
                alive = [int(x) for x in list(track.get("alive") or [])]
                # 移除双方，推入胜者（双淘汰则双方都消失）
                sides = {
                    int(x)
                    for x in (match.side_a_character_id, match.side_b_character_id)
                    if x
                }
                alive = [x for x in alive if x not in sides]
                if winner:
                    alive.append(int(winner))
                track["alive"] = alive
                if len(alive) <= 1:
                    track["champion_id"] = alive[0] if alive else None
                # 本场已收口，勿阻塞后续轮/道主战安排
                track["pending_next"] = False
            tracks[match.dao_id] = track
            state["tracks"] = tracks
            save_arena_state(contest, state)

        await self._session.flush()
        await self._broadcast_match_finished(match)
        await self._broadcast_contest_state(
            await self._session.get(DaoContest, match.contest_id),  # type: ignore[arg-type]
            extra={"action": "forfeit", "message_zh": label},
        )

        # 整备中：若本阶段场次均已因离场结束，立刻跳过剩余整备倒计时
        if contest is not None:
            await maybe_skip_adjust_after_forfeit(self, contest)

        return {
            "match_id": match_id,
            "changed": True,
            "winner_character_id": winner,
            "message": label,
        }

    async def _apply_lordship_from_leave_forfeit(self, match: DaoContestMatch) -> None:
        """道主战离场导致挑战者胜时，服务端写席位（不信前端）。"""
        if not match.side_a_character_id or not match.dao_id:
            return
        if match.winner_character_id != match.side_a_character_id:
            return
        lord = (
            await self._session.execute(
                select(DaoLordship).where(DaoLordship.dao_id == match.dao_id),
            )
        ).scalar_one_or_none()
        if lord is None:
            lord = DaoLordship(dao_id=match.dao_id, character_id=match.side_a_character_id)
            self._session.add(lord)
        else:
            lord.character_id = match.side_a_character_id
        lord.claimed_at = datetime.now(timezone.utc)
        match.lordship_transferred = True

    async def get_bracket(
        self,
        user: User,
        *,
        dao_id: str | None = None,
    ) -> dict[str, Any]:
        """对阵树（可按道过滤）。"""
        self._require_enabled()
        character = await self._gate.require_character(user)
        contest = await self.ensure_current()
        query = select(DaoContestMatch).where(DaoContestMatch.contest_id == contest.id)
        if dao_id:
            query = query.where(DaoContestMatch.dao_id == dao_id)
        query = query.order_by(
            DaoContestMatch.dao_id,
            DaoContestMatch.round_index,
            DaoContestMatch.bracket_slot,
            DaoContestMatch.id,
        )
        rows = list((await self._session.execute(query)).scalars().all())
        matches = [await self._match_public(m, include_report=False) for m in rows]
        return {
            "contest_id": contest.id,
            "status": contest.status,
            "dao_id": dao_id,
            "matches": matches,
            "me_character_id": character.id,
        }

    async def get_match(self, user: User, match_id: int) -> dict[str, Any]:
        """单场摘要。"""
        self._require_enabled()
        await self._gate.require_character(user)
        match = await self._session.get(DaoContestMatch, match_id)
        if match is None:
            raise AppError(code=40093, message="对阵不存在", http_status=404)
        return {"match": await self._match_public(match, include_report=False)}

    async def get_match_report(self, user: User, match_id: int) -> dict[str, Any]:
        """战报日志；直播中建议改拉 /live（本接口对观众脱敏布阵）。"""
        self._require_enabled()
        character = await self._gate.require_character(user)
        match = await self._session.get(DaoContestMatch, match_id)
        if match is None:
            raise AppError(code=40093, message="对阵不存在", http_status=404)
        report = self._parse_report(match)
        role = self._viewer_role(match, character.id)
        # 观众永远不拿到 live_pipeline.formation
        pipeline = report.get("live_pipeline")
        if isinstance(pipeline, dict) and role != "participant":
            pipeline = dict(pipeline)
            pipeline.pop("formation", None)
            ticks = []
            for tick in list(pipeline.get("ticks") or []):
                if tick.get("kind") == "formation_lock":
                    continue
                item = dict(tick)
                item.pop("formation", None)
                ticks.append(item)
            pipeline["ticks"] = ticks
            report = dict(report)
            report["live_pipeline"] = pipeline
        public = await self._match_public(match, include_report=False)
        live_active = self._live_active(match)
        presentation = BattlePlaybackPolicy.for_dao_contest(live_active=live_active)
        return {
            "match": public,
            "report": report,
            "viewer_role": role,
            # 兼容旧前端字段；权威以 playback_policy.allow_skip 为准
            "can_skip_playback": bool(presentation["playback_policy"]["allow_skip"]),
            "live_active": live_active,
            **presentation,
        }

    async def spectate_match(self, user: User, match_id: int) -> dict[str, Any]:
        """占用单直播槽（P4）。"""
        self._require_enabled()
        character = await self._gate.require_character(user)
        match = await self._session.get(DaoContestMatch, match_id)
        if match is None:
            raise AppError(code=40093, message="对阵不存在", http_status=404)
        if not match.is_live_round:
            raise AppError(code=40098, message="该场次无直播（可看战报回放）", http_status=400)
        if not self._live_active(match):
            return {
                "match": await self._match_public(match, include_report=False),
                "spectating": False,
                "live_active": False,
                "message": "直播已结束，可回放战报",
            }
        current = _SPECTATE_SLOTS.get(character.id)
        if current is not None and current != match_id:
            other = await self._session.get(DaoContestMatch, current)
            if other is not None and self._live_active(other):
                raise AppError(
                    code=40097,
                    message="同时只能观看一场直播，请先看完当前场次",
                    http_status=409,
                )
            _SPECTATE_SLOTS.pop(character.id, None)
        _SPECTATE_SLOTS[character.id] = match_id
        return {
            "match": await self._match_public(match, include_report=False),
            "spectating": True,
            "live_active": True,
            "room_id": f"dao_lord:match:{match.id}",
            "message": "已进入直播观战（不可跳过）",
            "active_spectate_match_id": match_id,
        }

    def _parse_report(self, match: DaoContestMatch) -> dict[str, Any]:
        """解析 match.report_json。"""
        if not match.report_json:
            return {}
        try:
            data = json.loads(match.report_json)
            return data if isinstance(data, dict) else {"summary": str(data)}
        except json.JSONDecodeError:
            return {"summary": match.report_json, "events": []}

    def _viewer_role(self, match: DaoContestMatch, character_id: int) -> str:
        """participant | spectator。"""
        if character_id in {
            match.side_a_character_id,
            match.side_b_character_id,
        }:
            return "participant"
        return "spectator"

    def _filter_ticks_for_viewer(
        self,
        ticks: list[dict[str, Any]],
        *,
        role: str,
        elapsed_ms: int,
    ) -> list[dict[str, Any]]:
        """按角色与时钟裁剪可见 ticks；观众去掉布阵。"""
        visible: list[dict[str, Any]] = []
        for tick in ticks:
            if int(tick.get("at_offset_ms") or 0) > elapsed_ms:
                break
            audience = str(tick.get("audience") or "all")
            if audience == "participants" and role != "participant":
                continue
            item = dict(tick)
            if role != "participant":
                item.pop("formation", None)
                if item.get("kind") == "formation_lock":
                    continue
            visible.append(item)
        return visible

    async def get_live_state(self, user: User, match_id: int) -> dict[str, Any]:
        """
        直播时钟快照：准备倒计时 / 对战节拍 / 结束。

        观众准备阶段仅见「准备中」倒计时，不见布阵。
        """
        self._require_enabled()
        character = await self._gate.require_character(user)
        match = await self._session.get(DaoContestMatch, match_id)
        if match is None:
            raise AppError(code=40093, message="对阵不存在", http_status=404)
        public = await self._match_public(match, include_report=False)
        role = self._viewer_role(match, character.id)
        report = self._parse_report(match)
        pipeline = (
            report.get("live_pipeline")
            if isinstance(report.get("live_pipeline"), dict)
            else None
        )

        if not match.is_live_round or pipeline is None:
            presentation = BattlePlaybackPolicy.for_dao_contest(live_active=False)
            return {
                "match": public,
                "viewer_role": role,
                "phase": "replay",
                "live_active": False,
                "can_skip": True,
                "countdown_seconds": 0,
                "formation_visible": False,
                "formation": None,
                "visible_ticks": [],
                "message": "非直播场次或直播已结束，可回放战报",
                **presentation,
            }

        started = match.live_started_at or datetime.now(timezone.utc)
        started = _as_utc(started)
        now = datetime.now(timezone.utc)
        elapsed_ms = max(0, int((now - started).total_seconds() * 1000))
        prep_s = int(pipeline.get("prep_seconds") or self._contest_cfg().live_prep_seconds)
        playback_s = int(
            pipeline.get("playback_seconds") or self._contest_cfg().live_playback_seconds,
        )
        prep_ms = prep_s * 1000
        total_ms = (prep_s + playback_s) * 1000

        if elapsed_ms < prep_ms:
            phase = "prep"
            countdown = max(0, prep_s - elapsed_ms // 1000)
            phase_label = f"准备中 {countdown} 秒"
        elif elapsed_ms < total_ms and self._live_active(match):
            phase = "battle"
            countdown = max(0, (total_ms - elapsed_ms) // 1000)
            phase_label = "对战直播中"
        else:
            phase = "ended"
            countdown = 0
            phase_label = "直播结束"

        live_active = phase in ("prep", "battle")
        ticks = list(pipeline.get("ticks") or [])
        visible = self._filter_ticks_for_viewer(ticks, role=role, elapsed_ms=elapsed_ms)

        # 对战事件游标：中途观战按服务端时钟对齐，勿从头播
        battle_event_cursor = 0
        for tick in visible:
            if tick.get("phase") == "battle" and tick.get("kind") == "battle_event":
                battle_event_cursor += 1

        formation = None
        formation_visible = False
        if role == "participant" and phase == "prep":
            formation_visible = True
            formation = pipeline.get("formation")

        presentation = BattlePlaybackPolicy.for_dao_contest(live_active=live_active)
        return {
            "match": public,
            "viewer_role": role,
            "phase": phase,
            "phase_label_zh": phase_label,
            "live_active": live_active,
            # 兼容旧字段；权威以 playback_policy.allow_skip 为准
            "can_skip": bool(presentation["playback_policy"]["allow_skip"]),
            "countdown_seconds": int(countdown),
            "elapsed_ms": elapsed_ms,
            "prep_seconds": prep_s,
            "playback_seconds": playback_s,
            "prep_ends_at": pipeline.get("prep_ends_at")
            or _iso(started + timedelta(seconds=prep_s)),
            "battle_ends_at": pipeline.get("battle_ends_at") or _iso(match.live_ends_at),
            "battle_event_cursor": battle_event_cursor,
            "server_now": _iso(now),
            "formation_visible": formation_visible,
            "formation": formation if formation_visible else None,
            "spectator_prep_hint_zh": (
                "双方准备中…" if role == "spectator" and phase == "prep" else None
            ),
            "visible_ticks": visible,
            "room_id": f"dao_lord:match:{match.id}",
            "message": phase_label,
            **presentation,
        }

    def _live_active(self, match: DaoContestMatch) -> bool:
        if not match.is_live_round or match.live_ends_at is None:
            return False
        return datetime.now(timezone.utc) < _as_utc(match.live_ends_at)

    async def _match_public(
        self,
        match: DaoContestMatch,
        *,
        include_report: bool,
    ) -> dict[str, Any]:
        """对阵公开态。"""
        names: dict[int, str] = {}
        for cid in (
            match.side_a_character_id,
            match.side_b_character_id,
            match.winner_character_id,
        ):
            if cid and cid not in names:
                ch = await self._session.get(Character, cid)
                names[cid] = ch.name if ch else f"#{cid}"

        live_active = self._live_active(match)
        payload: dict[str, Any] = {
            "id": match.id,
            "contest_id": match.contest_id,
            "dao_id": match.dao_id,
            "dao_label": self._dao.label_of(match.dao_id),
            "round_kind": match.round_kind,
            "round_kind_label": {
                "early": "淘汰赛",
                "semi": "半决赛",
                "final": "决赛",
                "lord": "道主决战",
            }.get(match.round_kind, match.round_kind),
            "round_index": match.round_index,
            "bracket_slot": match.bracket_slot,
            "side_a": {
                "character_id": match.side_a_character_id,
                "name": names.get(match.side_a_character_id or -1),
            }
            if match.side_a_character_id
            else None,
            "side_b": {
                "character_id": match.side_b_character_id,
                "name": names.get(match.side_b_character_id or -1),
            }
            if match.side_b_character_id
            else None,
            "winner_character_id": match.winner_character_id,
            "winner_name": names.get(match.winner_character_id or -1)
            if match.winner_character_id
            else None,
            "status": match.status,
            "resolve_reason": match.resolve_reason,
            "result_label_zh": match.result_label_zh,
            "is_live_round": bool(match.is_live_round),
            "live_active": live_active,
            "live_started_at": _iso(match.live_started_at),
            "live_ends_at": _iso(match.live_ends_at),
            "can_replay": bool(match.report_json) and not live_active,
            "can_spectate_live": live_active,
            "lord_defense_mode": match.lord_defense_mode,
            "lordship_transferred": bool(match.lordship_transferred),
            "finished_at": _iso(match.finished_at),
            "room_id": f"dao_lord:match:{match.id}",
            "presence_override": bool(match.presence_override),
            "side_a_forfeit": bool(match.side_a_forfeit),
            "side_b_forfeit": bool(match.side_b_forfeit),
            "loadout_locked_at": _iso(match.loadout_locked_at),
        }
        if include_report and match.report_json:
            try:
                payload["report"] = json.loads(match.report_json)
            except json.JSONDecodeError:
                payload["report"] = {"summary": match.report_json, "events": []}
        return payload

    async def _public_payload(
        self,
        contest: DaoContest,
        *,
        character: Character | None,
        message: str | None = None,
    ) -> dict[str, Any]:
        counts = await self._entry_counts(contest.id)
        cfg = self._contest_cfg()
        open_at, _close_at, _fight_at = self._schedule_bounds(contest.cycle_date)
        now = datetime.now(timezone.utc)
        registered = False
        my_dao = None
        if character is not None:
            ent = await self._session.execute(
                select(DaoContestEntry).where(
                    DaoContestEntry.contest_id == contest.id,
                    DaoContestEntry.character_id == character.id,
                ),
            )
            entry = ent.scalar_one_or_none()
            if entry:
                registered = True
                my_dao = entry.dao_id
        summary = None
        if contest.summary_json:
            try:
                summary = json.loads(contest.summary_json)
            except json.JSONDecodeError:
                summary = {"raw": contest.summary_json}
        by_dao_labels = [
            {
                "dao_id": dao_id,
                "dao_label": self._dao.label_of(dao_id),
                "count": counts.get(dao_id, 0),
            }
            for dao_id in sorted(counts.keys())
        ]
        for dao_id in get_game_config().dao.entries:
            if dao_id not in counts:
                by_dao_labels.append(
                    {
                        "dao_id": dao_id,
                        "dao_label": self._dao.label_of(dao_id),
                        "count": 0,
                    },
                )
        status_label = {
            "registration": "报名中",
            "matching": "匹配/演算中",
            "rsvp": "入席确认",
            "arena": "擂台进行中",
            "settled": "已收口",
            "cancelled": "已取消",
        }.get(contest.status, contest.status)
        window_open = (
            contest.status == "registration"
            and self._in_registration_window(now, contest.cycle_date)
        )
        # 个人报名资格（与 register() 门槛对齐；不含「已报名」）
        eligible = False
        eligible_block: str | None = None
        entry_row: DaoContestEntry | None = None
        if character is not None:
            eligible, eligible_block = await self._register_eligibility(
                character,
                now=now,
            )
            ent2 = await self._session.execute(
                select(DaoContestEntry).where(
                    DaoContestEntry.contest_id == contest.id,
                    DaoContestEntry.character_id == character.id,
                ),
            )
            entry_row = ent2.scalar_one_or_none()
        # 可点「报名」：窗内 + 资格 + 尚未报名
        can_register = bool(window_open and eligible and not registered)
        match_count = (
            await self._session.execute(
                select(func.count()).select_from(DaoContestMatch).where(
                    DaoContestMatch.contest_id == contest.id,
                ),
            )
        ).scalar_one()
        # 是否需要 RSVP 弹框
        needs_rsvp = False
        is_lord_for_contest = False
        if character is not None and contest.status == "rsvp":
            if entry_row is not None and entry_row.rsvp_status == "pending":
                needs_rsvp = True
            else:
                from app.services.dao_contest_arena import load_arena_state

                st = load_arena_state(contest)
                lord_rsvp = dict(st.get("lord_rsvp") or {})
                for dao_id, st_rsvp in lord_rsvp.items():
                    lord = (
                        await self._session.execute(
                            select(DaoLordship).where(DaoLordship.dao_id == dao_id),
                        )
                    ).scalar_one_or_none()
                    if lord and int(lord.character_id) == character.id and st_rsvp == "pending":
                        needs_rsvp = True
                        is_lord_for_contest = True
                        break
        payload: dict[str, Any] = {
            "contest": {
                "id": contest.id,
                "cycle_date": contest.cycle_date,
                "status": contest.status,
                "status_label": status_label,
                "phase": contest.phase,
                "phase_ends_at": _iso(contest.phase_ends_at),
                "force_started": bool(contest.force_started),
                "opened_at": _iso(contest.opened_at),
                "registration_opens_at": _iso(open_at),
                "registration_closes_at": _iso(contest.registration_closes_at),
                "fight_at": _iso(contest.fight_at),
                "tz": cfg.tz,
                "registration_window_open": window_open,
                "can_register": can_register,
                "eta_label": self._eta_label(contest, now=now),
                "counts_by_dao": by_dao_labels,
                "total_entrants": sum(counts.values()),
                "match_count": int(match_count or 0),
                "summary": summary,
                "p1_note": None,
                "bracket_ready": contest.status
                in ("settled", "matching", "rsvp", "arena")
                and int(match_count or 0) > 0,
                "staging_enabled": bool(cfg.staging_enabled),
                "rsvp_seconds": int(cfg.rsvp_seconds),
                "arena_first_round_countdown_seconds": int(
                    cfg.arena_first_round_countdown_seconds,
                ),
            },
            "me": {
                "registered": registered,
                "dao_id": my_dao,
                "dao_label": self._dao.label_of(my_dao) if my_dao else None,
                "eligible": eligible,
                "eligible_block_reason": None if eligible else eligible_block,
                "can_register": can_register,
                "active_spectate_match_id": _SPECTATE_SLOTS.get(character.id)
                if character
                else None,
                "rsvp_status": entry_row.rsvp_status if entry_row else None,
                "in_arena": bool(entry_row.in_arena) if entry_row else False,
                "needs_rsvp": needs_rsvp,
                "is_lord_rsvp": is_lord_for_contest,
            },
        }
        if message:
            payload["message"] = message
        # 运营/联调提示（收口与再开赛条件）
        payload["ops_hints"] = {
            "settle_when_zh": (
                "收口条件：①无人报名关闭报名→cancelled；"
                "②有人报名则经 RSVP→擂台各轮结束后 status=settled（含各道道主战收口）。"
                "到点 fight_at 或后台「立刻开赛」都会关闭报名并进入上述流程。"
            ),
            "reopen_when_zh": (
                "再次开赛条件：须先回到 status=registration。"
                "自然路径：下一业务日（cycle_date）自动新开一场；"
                "联调路径：后台「重新开放报名」清空本场报名/对阵并拉长报名窗，再点「立刻开赛」。"
                "已在 rsvp/arena 中不可重复开赛。"
            ),
            "force_start_requires": "registration",
            "reopen_allowed_statuses": [
                "settled",
                "cancelled",
                "rsvp",
                "arena",
                "matching",
                "registration",
            ],
            "can_force_start": contest.status == "registration",
            "can_reopen": contest.status
            in ("settled", "cancelled", "rsvp", "arena", "matching", "registration"),
            "can_advance_arena": contest.status in ("rsvp", "arena"),
            "advance_arena_zh": (
                "跳过入席确认/开赛倒计时/整备/轮间/直播等待，推进至下一场对战演出；"
                "已收口则不可用。可连点跳过本场演出进入再下一轮。"
            ),
            "current_phase": contest.phase,
        }
        return payload

    async def _register_eligibility(
        self,
        character: Character,
        *,
        now: datetime,
    ) -> tuple[bool, str | None]:
        """
        个人是否具备道主之争报名资格（不含报名窗/是否已报）。

        Returns:
            (ok, block_reason_zh)。
        """
        if character.status != "normal":
            return False, "当前状态不可报名道主之争"
        dao_row = await self._dao._get_or_create_row(character.id)
        fate = dao_row.fate_dao_id
        if not fate:
            return False, "须先开辟本命大道"
        min_lv = int(get_game_config().dao_lord.challenge_min_level)
        if int(dao_row.dao_level) < min_lv:
            return False, f"道等级须达到 {min_lv} 方可报名"
        if dao_row.challenge_cooldown_until and _as_utc(dao_row.challenge_cooldown_until) > _as_utc(now):
            return False, "挑战冷却中，暂不可报名"
        lord = (
            await self._session.execute(
                select(DaoLordship).where(DaoLordship.dao_id == fate),
            )
        ).scalar_one_or_none()
        if lord is None:
            return False, "该道虚位以待，达标者自动就任，无需报名"
        if lord.character_id == character.id:
            return False, "现任道主不可报名挑战本道"
        return True, None

    def _eta_label(self, contest: DaoContest, *, now: datetime) -> str:
        if contest.status == "registration":
            if now < self._schedule_bounds(contest.cycle_date)[0]:
                return "报名尚未开始"
            delta = _as_utc(contest.fight_at) - now
            secs = int(delta.total_seconds())
            if secs <= 0:
                return "即将开打"
            hours, rem = divmod(secs, 3600)
            minutes = rem // 60
            if hours > 0:
                return f"距开打约 {hours} 小时 {minutes} 分"
            return f"距开打约 {minutes} 分"
        if contest.status == "rsvp":
            return "入席确认中（等待玩家 RSVP）"
        if contest.status == "arena":
            phase = contest.phase or "进行中"
            return f"擂台进行中（{phase}）"
        if contest.status == "matching":
            return "匹配/建池中"
        if contest.status == "cancelled":
            return "本场已取消（无人报名）。测试可「重新开放报名」"
        if contest.status == "settled":
            return "本场已收口，可查看对阵与战报。测试可「重新开放报名」"
        return "报名已截止"

    def window_compat_payload(self, contest_payload: dict[str, Any]) -> dict[str, Any]:
        """将赛会日程映射为旧 windows 结构。"""
        c = contest_payload.get("contest") or {}
        # 开窗只看日程，不含个人资格（个人资格见 me.can_register）
        open_reg = bool(
            c.get("registration_window_open")
            if "registration_window_open" in c
            else (
                c.get("status") == "registration"
                and bool(c.get("can_register"))
            ),
        )
        return {
            "open": open_reg,
            "label": c.get("eta_label") or c.get("status_label") or "道主之争",
            "next_open_at": c.get("registration_opens_at"),
            "closes_at": c.get("registration_closes_at"),
            "contest_id": c.get("id"),
            "contest_status": c.get("status"),
        }
