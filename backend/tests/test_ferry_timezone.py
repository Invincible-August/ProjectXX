"""待引渡时间戳 naive/aware 兼容。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.domain.ferry_rules import can_self_rescue, is_ferry_timed_out
from app.services.ferry_service import FerryService


def test_is_ferry_timed_out_naive_deadline() -> None:
    now = datetime.now(timezone.utc)
    naive_deadline = (now - timedelta(seconds=10)).replace(tzinfo=None)
    assert is_ferry_timed_out(now, naive_deadline) is True


def test_can_self_rescue_naive_last_rescue() -> None:
    now = datetime.now(timezone.utc)
    last = (now - timedelta(seconds=5)).replace(tzinfo=None)
    ok, reason, remaining = can_self_rescue(
        status="awaiting_ferry",
        spirit_stones=9999,
        cost=100,
        last_rescue_at=last,
        now=now,
        cooldown_seconds=60,
    )
    assert ok is False
    assert "冷却" in reason
    assert remaining > 0


def test_can_self_rescue_insufficient_stones_message() -> None:
    ok, reason, remaining = can_self_rescue(
        status="awaiting_ferry",
        spirit_stones=100,
        cost=500,
        last_rescue_at=None,
        now=datetime.now(timezone.utc),
        cooldown_seconds=300,
    )
    assert ok is False
    assert "灵石不足" in reason
    assert "500" in reason
    assert "100" in reason
    assert remaining == 0


def test_ferry_public_naive_deadline_no_crash() -> None:
    """SQLite 常返回 naive deadline，不得在 remaining 计算时 TypeError。"""

    class _FakeChar:
        status = "awaiting_ferry"
        spirit_stones = 1000
        last_self_rescue_at = None
        ferry_deadline_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
            seconds=120,
        )

    svc = FerryService.__new__(FerryService)
    payload = FerryService._ferry_public(svc, _FakeChar())  # type: ignore[arg-type]
    assert payload["deadline_at"]
    assert isinstance(payload["remaining_seconds"], int)
    assert payload["remaining_seconds"] >= 0
