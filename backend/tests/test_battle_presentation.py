"""
战斗呈现种类与播控策略矩阵（domain.battle_presentation）。
"""

from __future__ import annotations

import pytest

from app.domain.battle_presentation import (
    BattleKind,
    BattlePlaybackPolicy,
    PlaybackPolicy,
)


def test_exploration_policy_allows_all_controls() -> None:
    """日常探索：简易可切、播/单步/跳过全开、不锁游标。"""
    policy = BattlePlaybackPolicy.from_kind(BattleKind.EXPLORATION)
    assert policy.allow_simple_mode is True
    assert policy.default_detail is False
    assert policy.allow_play_pause is True
    assert policy.allow_step is True
    assert policy.allow_skip is True
    assert policy.cursor_locked_to_server is False
    assert policy.hold_final_on_reload is False


def test_dao_contest_live_locks_cursor_and_blocks_controls() -> None:
    """道主之争直播：强制详细、禁控件、锁游标。"""
    policy = BattlePlaybackPolicy.from_kind(BattleKind.DAO_CONTEST_LIVE)
    assert policy.allow_simple_mode is False
    assert policy.default_detail is True
    assert policy.allow_play_pause is False
    assert policy.allow_step is False
    assert policy.allow_skip is False
    assert policy.cursor_locked_to_server is True
    assert policy.hold_final_on_reload is False


def test_dao_contest_replay_allows_controls_and_hold_final() -> None:
    """道主之争回放：可播控；同战报重拉可保持终局。"""
    policy = BattlePlaybackPolicy.from_kind(BattleKind.DAO_CONTEST_REPLAY)
    assert policy.allow_simple_mode is True
    assert policy.default_detail is True
    assert policy.allow_play_pause is True
    assert policy.allow_step is True
    assert policy.allow_skip is True
    assert policy.cursor_locked_to_server is False
    assert policy.hold_final_on_reload is True


def test_live_active_promotes_replay_kind_to_live() -> None:
    """调用方误传 replay + live_active=True 时升格为直播策略。"""
    policy = BattlePlaybackPolicy.from_kind(
        BattleKind.DAO_CONTEST_REPLAY,
        live_active=True,
    )
    assert policy.cursor_locked_to_server is True
    assert policy.allow_skip is False


@pytest.mark.parametrize(
    "kind",
    [BattleKind.DUEL, BattleKind.RAID_BOSS, "duel", "raid_boss"],
)
def test_reserved_kinds_follow_exploration(kind: BattleKind | str) -> None:
    """决斗 / Boss 占位种类：策略同探索自由回放。"""
    policy = BattlePlaybackPolicy.from_kind(kind)
    exploration = BattlePlaybackPolicy.from_kind(BattleKind.EXPLORATION)
    assert policy == exploration


def test_envelope_and_for_dao_contest() -> None:
    """信封字段齐全；for_dao_contest 按 live_active 切换 kind。"""
    env = BattlePlaybackPolicy.envelope(BattleKind.EXPLORATION)
    assert env["battle_kind"] == "exploration"
    assert isinstance(env["playback_policy"], dict)
    assert env["playback_policy"]["allow_skip"] is True

    live = BattlePlaybackPolicy.for_dao_contest(live_active=True)
    assert live["battle_kind"] == "dao_contest_live"
    assert live["playback_policy"]["cursor_locked_to_server"] is True

    replay = BattlePlaybackPolicy.for_dao_contest(live_active=False)
    assert replay["battle_kind"] == "dao_contest_replay"
    assert replay["playback_policy"]["allow_skip"] is True


def test_playback_policy_to_dict() -> None:
    """策略可序列化为 API 字典。"""
    policy = PlaybackPolicy(
        allow_simple_mode=True,
        default_detail=False,
        allow_play_pause=True,
        allow_step=True,
        allow_skip=True,
        cursor_locked_to_server=False,
        hold_final_on_reload=False,
    )
    data = policy.to_dict()
    assert set(data.keys()) == {
        "allow_simple_mode",
        "default_detail",
        "allow_play_pause",
        "allow_step",
        "allow_skip",
        "cursor_locked_to_server",
        "hold_final_on_reload",
    }


def test_unknown_kind_raises() -> None:
    """未知 kind 字符串抛 ValueError。"""
    with pytest.raises(ValueError):
        BattlePlaybackPolicy.from_kind("not_a_real_kind")
