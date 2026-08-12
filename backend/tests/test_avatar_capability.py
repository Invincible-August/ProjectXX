"""
化身 OOP / 性能优化单测：能力索引与体力脏写。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.domain.avatar_capability import AvatarCapabilityIndex
from app.domain.avatar_stamina import AvatarStaminaLedger
from app.domain.m4_constants import AvatarFeature
from app.services.realm_config import clear_game_config_cache, get_game_config


def test_capability_index_injected_on_load() -> None:
    """Bundle 加载后 avatar.capability 已预计算。"""
    clear_game_config_cache()
    cfg = get_game_config().avatar
    assert cfg.capability is not None
    assert isinstance(cfg.capability, AvatarCapabilityIndex)
    assert cfg.capability.is_unlocked("jindan", AvatarFeature.IDLE_SPIRIT)
    assert not cfg.capability.is_unlocked("jindan", AvatarFeature.IDLE_CRAFTING)
    assert cfg.capability.is_unlocked("yuanying", AvatarFeature.IDLE_CRAFTING)


def test_list_feature_states_uses_index() -> None:
    """功能看板与下一档预告由索引一次产出。"""
    clear_game_config_cache()
    cap = get_game_config().avatar.capability
    assert cap is not None
    features, preview = cap.list_feature_states("jindan")
    assert any(f["feature_id"] == "idle_spirit" and f["unlocked"] for f in features)
    assert preview is not None
    assert preview["next_major"] == "yuanying"


def test_stamina_tick_not_dirty_when_unchanged() -> None:
    """无恢复增量时 dirty=False，避免无意义 ORM flush。"""
    clear_game_config_cache()
    cap = get_game_config().avatar.capability
    assert cap is not None
    ledger = AvatarStaminaLedger(cap)
    now = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
    first = ledger.tick(
        character_major="yuanying",
        stamina=50,
        daily_actions_used=1,
        daily_actions_day="2026-08-07",
        stamina_recovered_at=now,
        now=now,
        bootstrap_if_empty=False,
    )
    assert first.dirty is False
    # 同一时刻再 tick → 仍不脏
    second = ledger.tick(
        character_major="yuanying",
        stamina=50,
        daily_actions_used=1,
        daily_actions_day="2026-08-07",
        stamina_recovered_at=now,
        now=now,
        bootstrap_if_empty=False,
    )
    assert second.dirty is False
    assert second.stamina == 50
    # 不足产生整数点时（如 1 分钟、每小时 5 点）也不脏
    tiny = ledger.tick(
        character_major="yuanying",
        stamina=50,
        daily_actions_used=1,
        daily_actions_day="2026-08-07",
        stamina_recovered_at=now,
        now=now + timedelta(minutes=1),
        bootstrap_if_empty=False,
    )
    assert tiny.dirty is False
