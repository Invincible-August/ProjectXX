"""
道主之争擂台分阶段调度（RSVP → 倒计时 → 早轮/半决起 → 收口）。

与 DaoContestService 配合：本模块只编排阶段；战斗推演仍走 service 既有方法。
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.db.models import DaoContest, DaoContestEntry, DaoContestMatch, DaoLordship
from app.db.session import AsyncSessionLocal
from app.schemas.common import AppError

if TYPE_CHECKING:
    from app.services.dao_contest_service import DaoContestService

logger = logging.getLogger(__name__)

_RUNNING: set[int] = set()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        raw = value.replace("Z", "+00:00")
        return _as_utc(datetime.fromisoformat(raw))
    except ValueError:
        return None


def schedule_arena_runner(contest_id: int) -> None:
    """在当前事件循环挂后台 tick（幂等）。pytest 下不挂，避免打到正式库/竞态。"""
    import os

    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    if contest_id in _RUNNING:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _RUNNING.add(contest_id)
    loop.create_task(_arena_background_loop(contest_id))


async def _arena_background_loop(contest_id: int) -> None:
    """独立 session 循环推进擂台，直至 settled/cancelled。"""
    try:
        while True:
            async with AsyncSessionLocal() as session:
                from app.services.dao_contest_service import DaoContestService

                svc = DaoContestService(session)
                try:
                    done = await svc.tick_arena(contest_id)
                    await session.commit()
                except Exception:  # noqa: BLE001
                    await session.rollback()
                    logger.exception("arena runner tick failed contest=%s", contest_id)
                    return
            if done:
                return
            await asyncio.sleep(0.5)
    finally:
        _RUNNING.discard(contest_id)


async def begin_staging(svc: DaoContestService, contest: DaoContest) -> DaoContest:
    """
    关闭报名后进入 RSVP：初始化各道 alive 池与道主应答槽。

    Args:
        svc: 赛会服务。
        contest: 已切 matching 的赛会行。
    """
    cfg = svc._contest_cfg()
    now = _utc_now()
    entries = list(
        (
            await svc._session.execute(
                select(DaoContestEntry).where(DaoContestEntry.contest_id == contest.id),
            )
        ).scalars().all(),
    )
    by_dao: dict[str, list[DaoContestEntry]] = {}
    for entry in entries:
        entry.rsvp_status = "pending"
        entry.rsvp_at = None
        entry.in_arena = False
        by_dao.setdefault(entry.dao_id, []).append(entry)

    tracks: dict[str, Any] = {}
    lord_rsvp: dict[str, str] = {}
    for dao_id, rows in by_dao.items():
        ordered = sorted(rows, key=lambda e: (_as_utc(e.registered_at), e.id))
        alive = [e.character_id for e in ordered]
        entry_rank = {str(e.character_id): idx for idx, e in enumerate(ordered)}
        tracks[dao_id] = {
            "alive": alive,
            "entry_rank": entry_rank,
            "round_index": 0,
            "champion_id": None,
            "done": False,
            "lord_force_snapshot": False,
            "match_ids": [],
        }
        lord = (
            await svc._session.execute(
                select(DaoLordship).where(DaoLordship.dao_id == dao_id),
            )
        ).scalar_one_or_none()
        if lord is not None and int(lord.character_id) not in alive:
            lord_rsvp[dao_id] = "pending"

    rsvp_s = int(cfg.rsvp_seconds)
    contest.status = "rsvp"
    contest.phase = "rsvp"
    contest.phase_ends_at = now + timedelta(seconds=rsvp_s)
    contest.current_round_index = 0
    state = {
        "phase": "rsvp",
        "phase_ends_at": _iso(contest.phase_ends_at),
        "action": "rsvp_open",
        "message_zh": f"道主之争已开始：请在 {rsvp_s} 秒内确认是否前往擂台（超时视为弃权）",
        "tracks": tracks,
        "lord_rsvp": lord_rsvp,
        "active_match_ids": [],
        "tracks_summary": [],
        "rsvp_seconds": rsvp_s,
    }
    contest.arena_state_json = json.dumps(state, ensure_ascii=False)
    await svc._session.flush()
    await svc._session.commit()
    await svc._broadcast_contest_state(
        contest,
        extra={
            "action": "rsvp_open",
            "message_zh": state["message_zh"],
            "rsvp_seconds": rsvp_s,
        },
    )
    schedule_arena_runner(contest.id)
    return contest


def load_arena_state(contest: DaoContest) -> dict[str, Any]:
    """解析 arena_state_json。"""
    if not contest.arena_state_json:
        return {}
    try:
        data = json.loads(contest.arena_state_json)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def save_arena_state(contest: DaoContest, state: dict[str, Any]) -> None:
    """写回 arena_state_json 并同步 phase 列。"""
    contest.phase = str(state.get("phase") or contest.phase or "")
    ends = _parse_iso(str(state.get("phase_ends_at") or "") or None)
    contest.phase_ends_at = ends
    contest.arena_state_json = json.dumps(state, ensure_ascii=False)


async def tick_arena(svc: DaoContestService, contest_id: int) -> bool:
    """
    若阶段计时已到则推进一步。

    Returns:
        True: 已 settled/cancelled，后台可停。
    """
    contest = await svc._session.get(DaoContest, contest_id)
    if contest is None:
        return True
    if contest.status in ("settled", "cancelled", "registration"):
        return contest.status in ("settled", "cancelled")
    if contest.status not in ("rsvp", "arena", "matching"):
        return False

    state = load_arena_state(contest)
    if not state:
        return False
    now = _utc_now()
    ends = contest.phase_ends_at or _parse_iso(str(state.get("phase_ends_at") or "") or None)
    if ends is not None and _as_utc(ends) > now:
        # playing 阶段额外检查直播是否结束
        if str(state.get("phase")) == "playing":
            if await _all_active_lives_ended(svc, contest, state):
                await _on_playing_done(svc, contest, state)
                await svc._session.flush()
                await svc._broadcast_contest_state(
                    contest,
                    extra={"action": str(state.get("action") or "arena_phase")},
                )
            return contest.status in ("settled", "cancelled")
        return False

    phase = str(state.get("phase") or contest.phase or "")
    if phase == "rsvp":
        await _finalize_rsvp(svc, contest, state)
    elif phase == "round_countdown":
        await _open_and_resolve_round(svc, contest, state)
    elif phase == "round_gap":
        await _after_gap(svc, contest, state)
    elif phase == "adjust":
        await _finish_adjust_and_play(svc, contest, state)
    elif phase == "playing":
        await _on_playing_done(svc, contest, state)
    else:
        logger.warning("unknown arena phase=%s contest=%s", phase, contest_id)
        return False

    await svc._session.flush()
    await svc._broadcast_contest_state(
        contest,
        extra={"action": str(state.get("action") or "arena_phase")},
    )
    return contest.status in ("settled", "cancelled")


async def drain_arena(svc: DaoContestService, contest_id: int, *, max_steps: int = 200) -> DaoContest:
    """测试/联调：连续 tick 直至收口（依赖配置秒数为 0 或已过期）。"""
    for _ in range(max_steps):
        done = await tick_arena(svc, contest_id)
        await svc._session.flush()
        if done:
            row = await svc._session.get(DaoContest, contest_id)
            if row is None:
                raise AppError(code=50010, message="赛会丢失", http_status=500)
            return row
        # 强制把 phase_ends_at 置为过去以跳过等待（仅 drain）
        row = await svc._session.get(DaoContest, contest_id)
        if row is None:
            break
        state = load_arena_state(row)
        state["phase_ends_at"] = _iso(_utc_now() - timedelta(seconds=1))
        row.phase_ends_at = _utc_now() - timedelta(seconds=1)
        save_arena_state(row, state)
        await svc._session.flush()
    row = await svc._session.get(DaoContest, contest_id)
    if row is None:
        raise AppError(code=50010, message="赛会丢失", http_status=500)
    return row


async def _finalize_rsvp(
    svc: DaoContestService,
    contest: DaoContest,
    state: dict[str, Any],
) -> None:
    """RSVP 超时：报名未应答→弃权；道主未应答→快照。"""
    now = _utc_now()
    entries = list(
        (
            await svc._session.execute(
                select(DaoContestEntry).where(DaoContestEntry.contest_id == contest.id),
            )
        ).scalars().all(),
    )
    tracks: dict[str, Any] = dict(state.get("tracks") or {})
    for entry in entries:
        if entry.rsvp_status == "pending":
            entry.rsvp_status = "timeout"
            entry.rsvp_at = now
            entry.in_arena = False
        if entry.rsvp_status in ("declined", "timeout"):
            track = tracks.get(entry.dao_id) or {}
            alive = [int(x) for x in list(track.get("alive") or [])]
            if entry.character_id in alive:
                alive = [x for x in alive if x != entry.character_id]
                track["alive"] = alive
                tracks[entry.dao_id] = track

    lord_rsvp = dict(state.get("lord_rsvp") or {})
    for dao_id, status in list(lord_rsvp.items()):
        if status == "pending":
            lord_rsvp[dao_id] = "timeout"
            track = tracks.get(dao_id) or {}
            track["lord_force_snapshot"] = True
            tracks[dao_id] = track
        elif status == "declined":
            track = tracks.get(dao_id) or {}
            track["lord_force_snapshot"] = True
            tracks[dao_id] = track

    cfg = svc._contest_cfg()
    countdown = int(cfg.arena_first_round_countdown_seconds)
    contest.status = "arena"
    contest.phase = "round_countdown"
    contest.phase_ends_at = now + timedelta(seconds=countdown)
    contest.current_round_index = 0
    state.update(
        {
            "phase": "round_countdown",
            "phase_ends_at": _iso(contest.phase_ends_at),
            "action": "round_countdown",
            "message_zh": f"擂台已开启，{countdown} 秒后开始第一轮",
            "tracks": tracks,
            "lord_rsvp": lord_rsvp,
            "active_match_ids": [],
        },
    )
    save_arena_state(contest, state)


async def _open_and_resolve_round(
    svc: DaoContestService,
    contest: DaoContest,
    state: dict[str, Any],
) -> None:
    """开一轮：早轮当场推演；半决起进入 adjust。"""
    from app.services.dao_contest_service import _round_kind_for_alive

    cfg = svc._contest_cfg()
    live_kinds = set(cfg.live_round_kinds)
    tracks: dict[str, Any] = dict(state.get("tracks") or {})
    pending_live: list[int] = []
    any_early = False

    for dao_id, track in list(tracks.items()):
        if track.get("done"):
            continue
        alive = [int(x) for x in list(track.get("alive") or [])]
        if len(alive) <= 1:
            # 无人或一人：直接准备道主战
            if not alive:
                track["done"] = True
                track["champion_id"] = None
                tracks[dao_id] = track
                continue
            track["champion_id"] = alive[0]
            tracks[dao_id] = track
            mid = await _schedule_lord_match(svc, contest, dao_id, track, live_kinds)
            if mid is not None:
                pending_live.append(mid)
            continue

        round_index = int(track.get("round_index") or 0) + 1
        track["round_index"] = round_index
        contest.current_round_index = max(contest.current_round_index, round_index)
        kind = _round_kind_for_alive(len(alive))
        entry_rank = {int(k): int(v) for k, v in dict(track.get("entry_rank") or {}).items()}
        rng = random.Random(f"{contest.id}:{dao_id}:{round_index}")
        pool = list(alive)
        rng.shuffle(pool)
        next_alive: list[int] = []
        slot = 0
        i = 0
        match_ids = list(track.get("match_ids") or [])
        while i < len(pool):
            if i + 1 >= len(pool):
                bye_id = pool[i]
                match = await svc._create_finished_match(
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
                    start_live=False,
                )
                match_ids.append(match.id)
                next_alive.append(bye_id)
                i += 1
                slot += 1
                continue
            a_id, b_id = pool[i], pool[i + 1]
            if kind in live_kinds:
                match = await svc._create_pending_match(
                    contest=contest,
                    dao_id=dao_id,
                    round_kind=kind,
                    round_index=round_index,
                    bracket_slot=slot,
                    side_a=a_id,
                    side_b=b_id,
                    status="adjusting",
                )
                match_ids.append(match.id)
                pending_live.append(match.id)
            else:
                winner, reason, label, report = await svc._resolve_challenger_pair(
                    a_id,
                    b_id,
                    entry_rank=entry_rank,
                    presence_check=True,
                    contest=contest,
                )
                match = await svc._create_finished_match(
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
                    start_live=False,
                )
                match_ids.append(match.id)
                if winner is not None:
                    next_alive.append(winner)
                any_early = True
            i += 2
            slot += 1
        track["match_ids"] = match_ids
        if kind in live_kinds:
            # 直播轮：alive 暂不更新，等场次结束
            track["pending_next"] = True
        else:
            track["alive"] = next_alive
            if len(next_alive) <= 1:
                track["champion_id"] = next_alive[0] if next_alive else None
        tracks[dao_id] = track

    state["tracks"] = tracks
    now = _utc_now()
    if pending_live:
        adjust_s = int(cfg.live_adjust_seconds)
        contest.phase = "adjust"
        contest.phase_ends_at = now + timedelta(seconds=adjust_s)
        state.update(
            {
                "phase": "adjust",
                "phase_ends_at": _iso(contest.phase_ends_at),
                "action": "adjust_start",
                "message_zh": f"半决起整备：{adjust_s} 秒内可调整上阵/阵法/功法装备",
                "active_match_ids": pending_live,
            },
        )
        # 标记 adjusting
        for mid in pending_live:
            row = await svc._session.get(DaoContestMatch, mid)
            if row is not None and row.status in ("pending", "adjusting"):
                row.status = "adjusting"
    elif any_early or _tracks_need_more(tracks):
        gap = int(cfg.round_gap_seconds)
        contest.phase = "round_gap"
        contest.phase_ends_at = now + timedelta(seconds=gap)
        state.update(
            {
                "phase": "round_gap",
                "phase_ends_at": _iso(contest.phase_ends_at),
                "action": "round_gap",
                "message_zh": f"本轮结束，{gap} 秒后进入下一轮",
                "active_match_ids": [],
            },
        )
    else:
        await _settle_contest(svc, contest, state)
        return
    save_arena_state(contest, state)


def _tracks_need_more(tracks: dict[str, Any]) -> bool:
    for track in tracks.values():
        if track.get("done"):
            continue
        alive = list(track.get("alive") or [])
        if len(alive) > 1:
            return True
        if track.get("champion_id") and not track.get("lord_done"):
            return True
        if len(alive) == 1 and not track.get("lord_done"):
            return True
    return False


async def _schedule_lord_match(
    svc: DaoContestService,
    contest: DaoContest,
    dao_id: str,
    track: dict[str, Any],
    live_kinds: set[str],
) -> int | None:
    """安排道主战：直播轮进 adjust；否则当场结算。"""
    if track.get("lord_done"):
        return None
    champion_id = track.get("champion_id")
    if champion_id is None:
        alive = [int(x) for x in list(track.get("alive") or [])]
        if len(alive) == 1:
            champion_id = alive[0]
            track["champion_id"] = champion_id
        else:
            track["done"] = True
            track["lord_done"] = True
            return None
    if "lord" in live_kinds:
        lord_row = (
            await svc._session.execute(
                select(DaoLordship).where(DaoLordship.dao_id == dao_id),
            )
        ).scalar_one_or_none()
        lord_id = int(lord_row.character_id) if lord_row else None
        match = await svc._create_pending_match(
            contest=contest,
            dao_id=dao_id,
            round_kind="lord",
            round_index=0,
            bracket_slot=0,
            side_a=int(champion_id),
            side_b=lord_id,
            status="adjusting",
            lord_defense_mode=(
                "snapshot" if track.get("lord_force_snapshot") else None
            ),
        )
        track.setdefault("match_ids", []).append(match.id)
        return match.id
    # 非直播：当场决战
    match, transferred, result = await svc._resolve_lord_match(
        contest,
        dao_id=dao_id,
        champion_id=int(champion_id),
        force_snapshot=bool(track.get("lord_force_snapshot")),
    )
    if match is not None:
        track.setdefault("match_ids", []).append(match.id)
    track["lord_done"] = True
    track["done"] = True
    track["lord_result"] = result
    track["lordship_transferred"] = transferred
    return None


async def _after_gap(
    svc: DaoContestService,
    contest: DaoContest,
    state: dict[str, Any],
) -> None:
    """轮间结束：若还有淘汰/道主战则再开一轮，否则收口。"""
    tracks = dict(state.get("tracks") or {})
    # 补跑仅剩冠军等待道主战的道
    live_kinds = set(svc._contest_cfg().live_round_kinds)
    pending_live: list[int] = []
    for dao_id, track in list(tracks.items()):
        if track.get("done") or track.get("lord_done"):
            continue
        alive = [int(x) for x in list(track.get("alive") or [])]
        if len(alive) <= 1 and not track.get("pending_next"):
            if alive:
                track["champion_id"] = alive[0]
            mid = await _schedule_lord_match(svc, contest, dao_id, track, live_kinds)
            tracks[dao_id] = track
            if mid is not None:
                pending_live.append(mid)

    state["tracks"] = tracks
    if pending_live:
        cfg = svc._contest_cfg()
        now = _utc_now()
        adjust_s = int(cfg.live_adjust_seconds)
        contest.phase = "adjust"
        contest.phase_ends_at = now + timedelta(seconds=adjust_s)
        state.update(
            {
                "phase": "adjust",
                "phase_ends_at": _iso(contest.phase_ends_at),
                "action": "adjust_start",
                "message_zh": f"道主决战整备：{adjust_s} 秒",
                "active_match_ids": pending_live,
            },
        )
        save_arena_state(contest, state)
        return

    if _tracks_need_more(tracks):
        # 立即再开一轮（countdown=0 也可）
        cfg = svc._contest_cfg()
        now = _utc_now()
        contest.phase = "round_countdown"
        contest.phase_ends_at = now  # 立即
        state.update(
            {
                "phase": "round_countdown",
                "phase_ends_at": _iso(contest.phase_ends_at),
                "action": "round_start",
                "message_zh": "下一轮即将开始",
                "active_match_ids": [],
            },
        )
        save_arena_state(contest, state)
        # 同一次 tick 继续推进
        await _open_and_resolve_round(svc, contest, state)
        return

    await _settle_contest(svc, contest, state)


async def _finish_adjust_and_play(
    svc: DaoContestService,
    contest: DaoContest,
    state: dict[str, Any],
) -> None:
    """整备结束：锁阵、推演、打开强制直播窗。"""
    now = _utc_now()
    active_ids = [int(x) for x in list(state.get("active_match_ids") or [])]
    tracks: dict[str, Any] = dict(state.get("tracks") or {})
    playing_ids: list[int] = []
    max_live_end = now

    for mid in active_ids:
        match = await svc._session.get(DaoContestMatch, mid)
        if match is None or match.status == "finished":
            continue
        match.loadout_locked_at = now
        if match.round_kind == "lord":
            track = tracks.get(match.dao_id) or {}
            force_snap = bool(track.get("lord_force_snapshot"))
            m2, transferred, result = await svc._resolve_lord_match_into(
                contest,
                match,
                force_snapshot=force_snap,
            )
            track["lord_done"] = True
            track["done"] = True
            track["lord_result"] = result
            track["lordship_transferred"] = transferred
            if m2.winner_character_id:
                track["champion_id"] = (
                    match.side_a_character_id
                    if transferred
                    else match.side_b_character_id
                )
            tracks[match.dao_id] = track
            playing_ids.append(m2.id)
            if m2.live_ends_at:
                max_live_end = max(max_live_end, _as_utc(m2.live_ends_at))
            continue

        a_id = match.side_a_character_id
        b_id = match.side_b_character_id
        track = tracks.get(match.dao_id) or {}
        entry_rank = {int(k): int(v) for k, v in dict(track.get("entry_rank") or {}).items()}
        if a_id is None or b_id is None:
            winner = a_id or b_id
            await svc._finalize_pending_match(
                match,
                winner=winner,
                resolve_reason="bye",
                label_zh="轮空",
                report={"summary": "缺席轮空", "events": []},
                start_live=True,
            )
        else:
            winner, reason, label, report = await svc._resolve_challenger_pair(
                a_id,
                b_id,
                entry_rank=entry_rank,
                presence_check=True,
                contest=contest,
            )
            await svc._finalize_pending_match(
                match,
                winner=winner,
                resolve_reason=reason,
                label_zh=label,
                report=report,
                start_live=True,
            )
        playing_ids.append(match.id)
        if match.live_ends_at:
            max_live_end = max(max_live_end, _as_utc(match.live_ends_at))
        # 更新 alive
        next_alive = [int(x) for x in list(track.get("alive") or [])]
        # 本轮参与者替换为胜者
        participants = {a_id, b_id}
        next_alive = [x for x in next_alive if x not in participants]
        if winner is not None:
            next_alive.append(int(winner))
        track["alive"] = next_alive
        if len(next_alive) <= 1:
            track["champion_id"] = next_alive[0] if next_alive else None
        track["pending_next"] = False
        tracks[match.dao_id] = track

    state["tracks"] = tracks
    contest.phase = "playing"
    contest.phase_ends_at = max_live_end
    state.update(
        {
            "phase": "playing",
            "phase_ends_at": _iso(contest.phase_ends_at),
            "action": "playback_start",
            "message_zh": "对战演出进行中，不可跳过；选手离场判负",
            "active_match_ids": playing_ids,
        },
    )
    save_arena_state(contest, state)


async def maybe_skip_adjust_after_forfeit(
    svc: DaoContestService,
    contest: DaoContest,
) -> bool:
    """
    整备中离场判负后：若本阶段 active 场次均已结束，立刻跳过剩余整备倒计时并推进。

    仍有其它场次在 adjusting/pending 时不跳过（并行半决需保留整备窗）。

    Returns:
        True 若已跳过整备并推进赛程。
    """
    state = load_arena_state(contest)
    phase = str(state.get("phase") or contest.phase or "")
    if phase != "adjust":
        return False

    active_ids = [int(x) for x in list(state.get("active_match_ids") or [])]
    if not active_ids:
        return False

    for mid in active_ids:
        match = await svc._session.get(DaoContestMatch, mid)
        if match is None:
            continue
        if match.status in ("adjusting", "pending", "playing"):
            return False

    # 全部已因离场等收口 → 立刻结束整备，避免空等倒计时
    now = _utc_now()
    contest.phase_ends_at = now
    state["phase_ends_at"] = _iso(now)
    state["action"] = "adjust_skip_forfeit"
    state["message_zh"] = "整备因离场判负提前结束，正在结算"
    save_arena_state(contest, state)

    await _finish_adjust_and_play(svc, contest, state)
    state = load_arena_state(contest)
    if str(state.get("phase") or "") == "playing":
        if await _all_active_lives_ended(svc, contest, state):
            await _on_playing_done(svc, contest, state)

    await svc._session.flush()
    await svc._broadcast_contest_state(
        contest,
        extra={
            "action": "adjust_skip_forfeit",
            "message_zh": "整备因离场判负提前结束",
        },
    )
    return True


async def _all_active_lives_ended(
    svc: DaoContestService,
    contest: DaoContest,
    state: dict[str, Any],
) -> bool:
    now = _utc_now()
    for mid in list(state.get("active_match_ids") or []):
        match = await svc._session.get(DaoContestMatch, int(mid))
        if match is None:
            continue
        if match.live_ends_at and _as_utc(match.live_ends_at) > now:
            return False
        if match.status == "playing":
            return False
    return True


async def _on_playing_done(
    svc: DaoContestService,
    contest: DaoContest,
    state: dict[str, Any],
) -> None:
    """直播窗结束：轮间或继续道主战或收口。"""
    # 标记 playing → finished（若仍 playing）
    for mid in list(state.get("active_match_ids") or []):
        match = await svc._session.get(DaoContestMatch, int(mid))
        if match is not None and match.status == "playing":
            match.status = "finished"
            if match.finished_at is None:
                match.finished_at = _utc_now()

    tracks = dict(state.get("tracks") or {})
    if _tracks_need_more(tracks):
        cfg = svc._contest_cfg()
        gap = int(cfg.round_gap_seconds)
        now = _utc_now()
        contest.phase = "round_gap"
        contest.phase_ends_at = now + timedelta(seconds=gap)
        state.update(
            {
                "phase": "round_gap",
                "phase_ends_at": _iso(contest.phase_ends_at),
                "action": "round_gap",
                "message_zh": f"演出结束，{gap} 秒后继续",
                "active_match_ids": [],
            },
        )
        save_arena_state(contest, state)
        return
    await _settle_contest(svc, contest, state)


async def _settle_contest(
    svc: DaoContestService,
    contest: DaoContest,
    state: dict[str, Any],
) -> None:
    """写 summary 并 settled。"""
    counts = await svc._entry_counts(contest.id)
    tracks_out: list[dict[str, Any]] = []
    for dao_id, track in dict(state.get("tracks") or {}).items():
        tracks_out.append(
            {
                "dao_id": dao_id,
                "dao_label": svc._dao.label_of(dao_id),
                "entrant_count": len(dict(track.get("entry_rank") or {})),
                "champion_character_id": track.get("champion_id"),
                "lord_result": track.get("lord_result"),
                "lordship_transferred": bool(track.get("lordship_transferred")),
                "match_ids": list(track.get("match_ids") or []),
            },
        )
    summary = {
        "phase": "settled",
        "message_zh": "本场道主之争已收口",
        "by_dao": counts,
        "total_entrants": sum(counts.values()),
        "force_started": bool(contest.force_started),
        "tracks": tracks_out,
    }
    contest.summary_json = json.dumps(summary, ensure_ascii=False)
    contest.status = "settled"
    contest.settled_at = _utc_now()
    contest.phase = "idle"
    contest.phase_ends_at = None
    state.update(
        {
            "phase": "idle",
            "phase_ends_at": None,
            "action": "settled",
            "message_zh": "道主之争已收口",
            "tracks_summary": tracks_out,
            "active_match_ids": [],
        },
    )
    save_arena_state(contest, state)
    await svc._session.flush()
    await svc._session.commit()
