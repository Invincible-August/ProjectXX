"""
队伍 / 团队规则：人数上限与玩法门闸。

队伍（party）最多 5 人；超过须转为团队（team），团队最多 40 人。
团队仅可参与团队秘境 / 团队 Boss / 野外 Boss / 势力争夺；
不可进普通秘境；击杀非团队 Boss 无掉落、不获修为。
"""

from __future__ import annotations

from typing import Any

from app.schemas.common import AppError

KIND_PARTY = "party"
KIND_TEAM = "team"

# 团队允许的活动键（玩法落地后由各服务调用 assert_activity_allowed）
ACTIVITY_TEAM_SECRET_REALM = "team_secret_realm"
ACTIVITY_TEAM_BOSS = "team_boss"
ACTIVITY_WILD_BOSS = "wild_boss"
ACTIVITY_FACTION_WAR = "faction_war"
ACTIVITY_NORMAL_SECRET_REALM = "normal_secret_realm"
ACTIVITY_NORMAL_BOSS = "normal_boss"
ACTIVITY_PVE = "pve"

TEAM_ALLOWED_ACTIVITIES = frozenset(
    {
        ACTIVITY_TEAM_SECRET_REALM,
        ACTIVITY_TEAM_BOSS,
        ACTIVITY_WILD_BOSS,
        ACTIVITY_FACTION_WAR,
    },
)

# 击杀该类目标时，团队成员不获掉落/修为
TEAM_NO_REWARD_BOSS_KINDS = frozenset(
    {
        ACTIVITY_NORMAL_BOSS,
        "raid_boss_solo",  # 占位：非团队 Boss
    },
)


def normalize_party_kind(raw: str | None) -> str:
    """Normalize stored kind to party|team."""
    key = str(raw or KIND_PARTY).strip().lower()
    if key in ("team", "raid", "raid_team", "团队"):
        return KIND_TEAM
    return KIND_PARTY


def party_max_for_kind(kind: str, *, cfg: Any) -> int:
    """
    Member cap for the given kind.

    Args:
        kind: party | team.
        cfg: ChatConfig (party_max_members / team_max_members).

    Returns:
        int: Max members inclusive.
    """
    k = normalize_party_kind(kind)
    if k == KIND_TEAM:
        return max(2, int(getattr(cfg, "team_max_members", 40) or 40))
    return max(2, int(getattr(cfg, "party_max_members", 5) or 5))


def kind_label_zh(kind: str) -> str:
    """Player-facing label."""
    return "团队" if normalize_party_kind(kind) == KIND_TEAM else "队伍"


def leader_label_zh(kind: str) -> str:
    """Leader title."""
    return "团长" if normalize_party_kind(kind) == KIND_TEAM else "队长"


def assert_can_add_member(
    *,
    kind: str,
    current_count: int,
    cfg: Any,
) -> None:
    """
    Raise if accepting/inviting would exceed cap.

    Args:
        kind: party | team.
        current_count: Current member count before add.
        cfg: ChatConfig.

    Raises:
        AppError: Over capacity.
    """
    k = normalize_party_kind(kind)
    cap = party_max_for_kind(k, cfg=cfg)
    if int(current_count) >= cap:
        if k == KIND_PARTY:
            raise AppError(
                code=40000,
                message=f"队伍已满（最多 {cap} 人），请先转换为团队后再邀请",
                http_status=400,
            )
        raise AppError(
            code=40000,
            message=f"团队已满（最多 {cap} 人）",
            http_status=400,
        )


def assert_activity_allowed(*, kind: str, activity: str) -> None:
    """
    Gate content by party kind (call from secret-realm / boss entry points).

    Args:
        kind: Current open party kind (or treat alone as party-compatible).
        activity: Activity key.

    Raises:
        AppError: Team cannot enter the activity.
    """
    k = normalize_party_kind(kind)
    act = str(activity or "").strip()
    if k != KIND_TEAM:
        return
    if act == ACTIVITY_NORMAL_SECRET_REALM:
        raise AppError(
            code=40000,
            message="团队不可进入普通秘境，请解散团队或改用队伍",
            http_status=400,
        )
    if act in TEAM_ALLOWED_ACTIVITIES:
        return
    # 未列出的玩法：团队默认拒绝（避免误进）
    if act in (ACTIVITY_PVE, ACTIVITY_NORMAL_BOSS):
        # PVE / 普通 Boss 可进，但奖励被 suppress_rewards_for_kill 关掉
        return
    if act:
        raise AppError(
            code=40000,
            message="当前为团队模式，仅可挑战团队秘境 / 团队 Boss / 野外 Boss / 势力争夺",
            http_status=400,
        )


def suppress_rewards_for_kill(*, kind: str, boss_kind: str) -> bool:
    """
    Whether drops and cultivation gains should be suppressed.

    Team members killing non-team bosses: no loot, no cultivation.
    """
    if normalize_party_kind(kind) != KIND_TEAM:
        return False
    bk = str(boss_kind or "").strip()
    if bk in (
        ACTIVITY_TEAM_BOSS,
        ACTIVITY_WILD_BOSS,
        "team_boss",
        "wild_boss",
    ):
        return False
    # 非团队 Boss（含普通 Boss / 未标注）一律无收益
    return True
