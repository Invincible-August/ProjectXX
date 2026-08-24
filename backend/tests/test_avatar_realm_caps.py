"""化身境界双封顶（相对本体 + 禁道主/轮回）。"""

from __future__ import annotations

from app.constants.avatar import ERR_AVATAR_REALM_CAP
from app.domain.avatar_realm_rules import can_avatar_advance_to, can_avatar_hold_major
from app.services.realm_config import get_game_config


def test_avatar_cannot_hold_dao_lord_or_reincarnation() -> None:
    """化身不可进入道主境 / 轮回境。"""
    cfg = get_game_config()
    ok, code, _msg = can_avatar_hold_major(
        avatar_major="dao_lord",
        host_major="true_immortal",
        avatar_cfg=cfg.avatar,
        realms=cfg.realms,
    )
    assert ok is False
    assert code == ERR_AVATAR_REALM_CAP
    ok2, _, _ = can_avatar_hold_major(
        avatar_major="reincarnation",
        host_major="true_immortal",
        avatar_cfg=cfg.avatar,
        realms=cfg.realms,
    )
    assert ok2 is False


def test_avatar_cannot_outrank_host_major() -> None:
    """默认同大境；化身化神而本体元婴 → 拒绝。"""
    cfg = get_game_config()
    ok, code, _msg = can_avatar_hold_major(
        avatar_major="huashen",
        host_major="yuanying",
        avatar_cfg=cfg.avatar,
        realms=cfg.realms,
    )
    assert ok is False
    assert code == ERR_AVATAR_REALM_CAP


def test_avatar_same_major_ok() -> None:
    """同一大境界合法（小境超前由调用方允许）。"""
    cfg = get_game_config()
    ok, code, _msg = can_avatar_hold_major(
        avatar_major="yuanying",
        host_major="yuanying",
        avatar_cfg=cfg.avatar,
        realms=cfg.realms,
    )
    assert ok is True
    assert code is None


def test_avatar_minor_advance_always_ok() -> None:
    """小境进阶不走大境界封顶。"""
    cfg = get_game_config()
    ok, code, _msg = can_avatar_advance_to(
        next_major="yuanying",
        next_is_major_cross=False,
        host_major="jindan",
        avatar_cfg=cfg.avatar,
        realms=cfg.realms,
    )
    assert ok is True
    assert code is None
