"""
战斗呈现与播控策略（纯规则，无 IO）。

引擎仍共用自走棋演算；本模块只决定「战报信封上的种类 + 前端控件策略」。
前端必须以后端下发的 ``playback_policy`` 为准，禁止按路由猜测。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class BattleKind(StrEnum):
    """战斗呈现种类（可扩展；玩法未接通的 kind 仍有策略行）。"""

    # 日常 /battle 探索遭遇（PVE / 攻打快照）
    EXPLORATION = "exploration"
    # 道主之争：直播演出窗
    DAO_CONTEST_LIVE = "dao_contest_live"
    # 道主之争：可回放（直播结束或非直播轮）
    DAO_CONTEST_REPLAY = "dao_contest_replay"
    # 预留：决斗 / 多人 Boss（未接通玩法前策略同探索）
    DUEL = "duel"
    RAID_BOSS = "raid_boss"


@dataclass(frozen=True)
class PlaybackPolicy:
    """
    战报播放器播控策略（权威字段）。

    前端 ``BattleReportPlayer`` 只读这些布尔位，不自行拼 live/allowSkip。
    """

    # 是否显示简易/详细开关
    allow_simple_mode: bool
    # 进入时是否默认详细棋盘
    default_detail: bool
    # 播放 / 暂停 / 重播
    allow_play_pause: bool
    # 单步
    allow_step: bool
    # 跳过动画
    allow_skip: bool
    # 游标是否强制对齐服务端（直播）
    cursor_locked_to_server: bool
    # 同战报重拉时是否保持终局游标（赛会直播结束重拉）
    hold_final_on_reload: bool

    def to_dict(self) -> dict[str, Any]:
        """序列化为 API 字典。"""
        return asdict(self)


class BattlePlaybackPolicy:
    """种类 → 播控策略的唯一工厂（第一期矩阵写死；后续可迁 yaml）。"""

    @staticmethod
    def from_kind(
        kind: BattleKind | str,
        *,
        live_active: bool = False,
    ) -> PlaybackPolicy:
        """
        按战斗种类生成播控策略。

        参数:
            kind: ``BattleKind`` 或等价字符串。
            live_active: 仅对赛会信封有意义；为 True 时强制走直播策略
                （即使传入 replay kind，也升格为 live，防止调用方漏改 kind）。

        返回:
            PlaybackPolicy: 冻结策略对象。

        异常:
            ValueError: 未知 kind 字符串。
        """
        resolved = BattleKind(str(kind))
        # 直播窗优先：调用方若仍传 replay 但 live_active=True，以直播为准
        if live_active and resolved in {
            BattleKind.DAO_CONTEST_LIVE,
            BattleKind.DAO_CONTEST_REPLAY,
        }:
            resolved = BattleKind.DAO_CONTEST_LIVE

        if resolved == BattleKind.DAO_CONTEST_LIVE:
            return PlaybackPolicy(
                allow_simple_mode=False,
                default_detail=True,
                allow_play_pause=False,
                allow_step=False,
                allow_skip=False,
                cursor_locked_to_server=True,
                hold_final_on_reload=False,
            )
        if resolved == BattleKind.DAO_CONTEST_REPLAY:
            return PlaybackPolicy(
                allow_simple_mode=True,
                default_detail=True,
                allow_play_pause=True,
                allow_step=True,
                allow_skip=True,
                cursor_locked_to_server=False,
                hold_final_on_reload=True,
            )
        # exploration / duel / raid_boss：自由回放
        return PlaybackPolicy(
            allow_simple_mode=True,
            default_detail=False,
            allow_play_pause=True,
            allow_step=True,
            allow_skip=True,
            cursor_locked_to_server=False,
            hold_final_on_reload=False,
        )

    @staticmethod
    def envelope(
        kind: BattleKind | str,
        *,
        live_active: bool = False,
    ) -> dict[str, Any]:
        """
        生成挂到开战/战报响应上的 ``battle_kind`` + ``playback_policy`` 片段。

        参数:
            kind: 战斗种类。
            live_active: 是否处于直播演出（影响赛会 kind 升格）。

        返回:
            dict: ``{battle_kind, playback_policy}``。
        """
        resolved = BattleKind(str(kind))
        if live_active and resolved in {
            BattleKind.DAO_CONTEST_LIVE,
            BattleKind.DAO_CONTEST_REPLAY,
        }:
            resolved = BattleKind.DAO_CONTEST_LIVE
        policy = BattlePlaybackPolicy.from_kind(resolved, live_active=live_active)
        return {
            "battle_kind": str(resolved),
            "playback_policy": policy.to_dict(),
        }

    @staticmethod
    def for_dao_contest(*, live_active: bool) -> dict[str, Any]:
        """
        道主之争快捷信封：直播中 → live；否则 → replay。

        参数:
            live_active: 当前是否直播演出窗。

        返回:
            dict: ``battle_kind`` + ``playback_policy``。
        """
        kind = (
            BattleKind.DAO_CONTEST_LIVE
            if live_active
            else BattleKind.DAO_CONTEST_REPLAY
        )
        return BattlePlaybackPolicy.envelope(kind, live_active=live_active)
