"""道主之争擂台分阶段：RSVP / 快进收口辅助。"""

from __future__ import annotations

from dataclasses import replace

from app.db.models import User
from app.services.dao_contest_service import DaoContestService


def patch_fast_staging(svc: DaoContestService) -> None:
    """将 RSVP/倒计时/整备秒数置 0，便于单测 drain。"""
    original = svc._contest_cfg

    def _fast():
        cfg = original()
        return replace(
            cfg,
            staging_enabled=True,
            rsvp_seconds=0,
            arena_first_round_countdown_seconds=0,
            round_gap_seconds=0,
            live_adjust_seconds=0,
            live_prep_seconds=8,
            live_playback_seconds=20,
            dev_assume_online=True,
            leave_during_playback_forfeit=True,
        )

    svc._contest_cfg = _fast  # type: ignore[method-assign]


async def force_start_and_settle(
    svc: DaoContestService,
    *users: User,
) -> dict:
    """
    立刻开赛 → 全员 RSVP 接受 → drain 至 settled。

    Returns:
        force_start 后的 public payload（drain 后需再 get_current）。
    """
    patch_fast_staging(svc)
    payload = await svc.force_start(note="test")
    contest_id = int(payload["contest"]["id"])
    for user in users:
        try:
            await svc.submit_rsvp(user, accept=True)
        except Exception:  # noqa: BLE001 — 非报名者/非道主跳过
            pass
    await svc.drain_arena(contest_id)
    return await svc.get_current(users[0]) if users else payload
