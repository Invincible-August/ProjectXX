"""
化身领域规则：凝练门槛、功能解锁、互传保留率、体力/日行动、初始属性。

纯函数，无数据库 / IO；配置来自 avatar.yaml 与 realms 顺序。
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping

from app.domain.m4_constants import (
    IDLE_DIRECTION_FEATURE,
    AvatarFeature,
    IdleDirection,
)

# 业务错误码（化身系统设计 §10）
ERR_FEATURE_LOCKED = 40090
ERR_STAMINA_INSUFFICIENT = 40091
ERR_DAILY_ACTIONS_EXHAUSTED = 40092
ERR_SOLO_FORMATION_INVALID = 40093


def major_realm_order(realms: dict[str, Any]) -> list[str]:
    """
    按 next_major 链推导大境界顺序。

    实现委托 ``AvatarCapabilityIndex.build_realm_order``，避免双份扫链逻辑。
    """
    from app.domain.avatar_capability import AvatarCapabilityIndex

    return list(AvatarCapabilityIndex.build_realm_order(realms))


def realm_meets_unlock(
    character_major: str,
    unlock_major: str,
    realms: dict[str, Any],
) -> bool:
    """
    判断角色大境界是否达到门槛。

    参数:
        character_major: 角色当前大境界。
        unlock_major: 要求的最低大境界。
        realms: 境界配置字典。

    返回:
        True 表示已达或超过门槛。
    """
    order = major_realm_order(realms)
    if character_major not in order or unlock_major not in order:
        return character_major == unlock_major
    return order.index(character_major) >= order.index(unlock_major)


def can_condense(
    *,
    character_major: str,
    has_avatar: bool,
    unlock_major: str,
    max_avatars: int,
    realms: dict[str, Any],
) -> tuple[bool, int | None]:
    """
    凝练前置校验（境界 / 已有化身 / 配置上限；不含灵石）。

    返回:
        (是否允许, 错误码或 None)。
    """
    if has_avatar:
        return False, 40051
    if not realm_meets_unlock(character_major, unlock_major, realms):
        return False, 40050
    if max_avatars < 1:
        return False, 40050
    return True, None


def build_condense_eligibility(
    *,
    character_major: str,
    spirit_stones: int,
    has_avatar: bool,
    unlock_major: str,
    max_avatars: int,
    spirit_stone_cost: int,
    realms: dict[str, Any],
) -> dict[str, Any]:
    """
    构建凝练权威闸（供 GET /avatar/features 下发；前端勿再抄境界序）。

    参数:
        character_major: 本体大境界。
        spirit_stones: 当前灵石。
        has_avatar: 是否已有化身行。
        unlock_major: avatar.yaml 凝练门槛。
        max_avatars: 化身上限（定案为 1）。
        spirit_stone_cost: 凝练费用。
        realms: 境界配置。

    返回:
        含 can_condense / realm_ok / stones_ok / block_* 的字典。
    """
    # 境界序比较与 POST /condense 同源（含真仙等更高境）
    realm_ok = realm_meets_unlock(character_major, unlock_major, realms)
    stones_ok = int(spirit_stones) >= int(spirit_stone_cost)
    can_do = (
        realm_ok
        and (not has_avatar)
        and stones_ok
        and max_avatars >= 1
    )

    block_code: int | None = None
    block_message: str | None = None
    if has_avatar:
        block_code = 40051
        block_message = "已凝练化身"
    elif not realm_ok or max_avatars < 1:
        block_code = 40050
        block_message = (
            "化身系统未开放凝练"
            if max_avatars < 1
            else f"未达凝练境界（需 {unlock_major} 及以上）"
        )
    elif not stones_ok:
        block_code = 40000
        block_message = f"灵石不足（需 {spirit_stone_cost}）"

    return {
        "can_condense": can_do,
        "realm_ok": realm_ok,
        "has_avatar": has_avatar,
        "stones_ok": stones_ok,
        "unlock_major_realm": unlock_major,
        "spirit_stone_cost": int(spirit_stone_cost),
        "block_code": block_code,
        "block_message": block_message,
    }


def build_initial_stats(
    main_atk: int,
    main_hp: int,
    *,
    initial_stat_ratio: float,
    material_mod: float,
    default_speed: int = 8,
) -> dict[str, int]:
    """
    根据本体战斗属性计算化身初始面板（向下取整，至少 1）。

    参数:
        main_atk: 本体最终攻击。
        main_hp: 本体最终生命。
        initial_stat_ratio: avatar.yaml 初始属性比例。
        material_mod: 材料修正占位。
        default_speed: 默认速度。

    返回:
        ``{atk, hp, speed}`` 快照字典。
    """
    mult = initial_stat_ratio * material_mod
    atk = max(1, math.floor(main_atk * mult))
    hp = max(1, math.floor(main_hp * mult))
    return {"atk": atk, "hp": hp, "speed": max(1, default_speed)}


def validate_transfer_resource(
    resource: str,
    *,
    allow: tuple[str, ...],
    deny: tuple[str, ...],
) -> tuple[bool, int | None]:
    """
    校验互传资源是否合法。

    返回:
        (是否合法, 错误码或 None)。
    """
    if resource in deny:
        return False, 40052
    if resource not in allow:
        return False, 40052
    return True, None


def is_allowed_avatar_idle_direction(direction: str) -> bool:
    """化身挂机方向是否在允许集合内（语法层；功能解锁另检）。"""
    return direction in {
        IdleDirection.NONE,
        IdleDirection.SPIRIT,
        IdleDirection.BODY,
        IdleDirection.CRAFTING,
    }


def feature_required_for_idle(direction: str) -> str | None:
    """
    挂机方向对应的功能 id；``none`` 无需功能。

    参数:
        direction: 挂机方向。

    返回:
        feature_id 或 None。
    """
    if direction == IdleDirection.NONE:
        return None
    return IDLE_DIRECTION_FEATURE.get(direction)


def is_feature_unlocked(
    character_major: str,
    feature_id: str,
    *,
    feature_unlocks: Mapping[str, Any],
    realms: dict[str, Any],
) -> bool:
    """
    本体大境界是否已解锁指定化身功能。

    参数:
        character_major: 本体当前大境界。
        feature_id: 功能 id（见 AvatarFeature）。
        feature_unlocks: 配置表 feature_id → {min_major, ...} 或对象。
        realms: 境界配置。

    返回:
        True 表示已解锁。
    """
    entry = feature_unlocks.get(feature_id)
    if entry is None:
        return False
    min_major = getattr(entry, "min_major", None)
    if min_major is None and isinstance(entry, dict):
        min_major = entry.get("min_major")
    if not min_major:
        return False
    return realm_meets_unlock(character_major, str(min_major), realms)


def check_feature_or_error(
    character_major: str,
    feature_id: str,
    *,
    feature_unlocks: Mapping[str, Any],
    realms: dict[str, Any],
) -> tuple[bool, int | None, str]:
    """
    功能闸：未解锁返回 (False, 40090, 文案)。

    返回:
        (ok, error_code, message)。
    """
    if is_feature_unlocked(
        character_major,
        feature_id,
        feature_unlocks=feature_unlocks,
        realms=realms,
    ):
        return True, None, ""
    entry = feature_unlocks.get(feature_id)
    label = feature_id
    min_major = ""
    if entry is not None:
        raw_label = getattr(entry, "label_zh", None)
        if raw_label is None and isinstance(entry, dict):
            raw_label = entry.get("label_zh")
        label = str(raw_label or feature_id)
        raw_min = getattr(entry, "min_major", None)
        if raw_min is None and isinstance(entry, dict):
            raw_min = entry.get("min_major")
        min_major = str(raw_min or "")
    reason = f"化身功能未解锁：{feature_id}（{label}）"
    if min_major:
        reason += f"；需本体达 {min_major}"
    return False, ERR_FEATURE_LOCKED, reason


def list_feature_states(
    character_major: str,
    *,
    feature_unlocks: Mapping[str, Any],
    realms: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """
    组装显性功能看板：已解锁 / 未解锁列表 + 下一档预告。

    返回:
        (features[], unlock_preview | None)。
    """
    order = major_realm_order(realms)
    current_idx = order.index(character_major) if character_major in order else -1
    features: list[dict[str, Any]] = []
    next_by_major: dict[str, list[dict[str, Any]]] = {}

    for feature_id, entry in feature_unlocks.items():
        min_major = str(
            getattr(entry, "min_major", None)
            or (entry.get("min_major") if isinstance(entry, dict) else "")
            or "",
        )
        label_zh = str(
            getattr(entry, "label_zh", None)
            or (entry.get("label_zh") if isinstance(entry, dict) else None)
            or feature_id,
        )
        summary = str(
            getattr(entry, "summary", None)
            or (entry.get("summary") if isinstance(entry, dict) else None)
            or "",
        )
        unlocked = is_feature_unlocked(
            character_major,
            str(feature_id),
            feature_unlocks=feature_unlocks,
            realms=realms,
        )
        features.append(
            {
                "feature_id": str(feature_id),
                "min_major": min_major,
                "label_zh": label_zh,
                "summary": summary,
                "unlocked": unlocked,
            },
        )
        if not unlocked and min_major in order:
            next_by_major.setdefault(min_major, []).append(
                {
                    "feature_id": str(feature_id),
                    "label_zh": label_zh,
                    "summary": summary,
                    "min_major": min_major,
                },
            )

    unlock_preview: dict[str, Any] | None = None
    if current_idx >= 0:
        for major in order[current_idx + 1 :]:
            pending = next_by_major.get(major)
            if pending:
                unlock_preview = {"next_major": major, "features": pending}
                break

    def _sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
        maj = str(item.get("min_major") or "")
        maj_idx = order.index(maj) if maj in order else 999
        return (0 if item.get("unlocked") else 1, maj_idx, str(item.get("feature_id")))

    features.sort(key=_sort_key)
    return features, unlock_preview


def resolve_retention_ratio(
    character_major: str,
    *,
    retention_ratio: float,
    retention_by_major: Mapping[str, float] | None,
) -> float:
    """
    解析互传保留率（境界覆盖优先于全局）。

    返回:
        (0, 1] 区间内的保留率。
    """
    ratio = float(retention_ratio)
    if retention_by_major and character_major in retention_by_major:
        ratio = float(retention_by_major[character_major])
    return max(0.0, min(1.0, ratio))


def compute_transfer_preview(
    amount: int,
    *,
    retention_ratio: float,
    min_amount: int = 1,
) -> dict[str, Any]:
    """
    互传预览：gross / net / fee。

    公式: net = floor(gross × retention_ratio)；扣发送方 gross，接收方 +net。
    """
    if amount < min_amount:
        return {
            "ok": False,
            "gross": 0,
            "net": 0,
            "fee": 0,
            "retention_ratio": retention_ratio,
            "message": f"互传数量须 ≥ {min_amount}",
        }
    gross = int(math.floor(amount))
    if gross <= 0:
        return {
            "ok": False,
            "gross": 0,
            "net": 0,
            "fee": 0,
            "retention_ratio": retention_ratio,
            "message": "转移数量须大于 0",
        }
    net = max(0, int(math.floor(gross * retention_ratio)))
    fee = gross - net
    return {
        "ok": True,
        "gross": gross,
        "net": net,
        "fee": fee,
        "retention_ratio": retention_ratio,
        "message": "",
    }


def stamina_cap_for_major(
    character_major: str,
    *,
    base_cap: int,
    cap_by_major: Mapping[str, int] | None,
) -> int:
    """按本体境界解析化身体力上限。"""
    if cap_by_major and character_major in cap_by_major:
        return max(0, int(cap_by_major[character_major]))
    return max(0, int(base_cap))


def apply_stamina_recovery(
    current: int,
    *,
    cap: int,
    last_recovery_at: datetime | None,
    now: datetime,
    per_hour: float,
) -> tuple[int, datetime]:
    """
    按现实小时恢复体力（向下取整点数）。

    返回:
        (新体力, 新锚点)。
    """
    if per_hour <= 0 or cap <= 0:
        return min(current, cap), now if last_recovery_at is None else last_recovery_at
    if last_recovery_at is None:
        return min(max(0, current), cap), now

    def _as_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    elapsed_seconds = max(0.0, (_as_utc(now) - _as_utc(last_recovery_at)).total_seconds())
    gained = int(math.floor(elapsed_seconds / 3600.0 * per_hour))
    if gained <= 0:
        return min(max(0, current), cap), last_recovery_at
    new_val = min(cap, max(0, current) + gained)
    hours_consumed = gained / per_hour if per_hour else 0
    new_anchor = _as_utc(last_recovery_at) + timedelta(hours=hours_consumed)
    return new_val, new_anchor


def utc_day_key(now: datetime) -> str:
    """服务器日键（UTC YYYY-MM-DD），用于日行动重置。"""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    d: date = now.date()
    return d.isoformat()


def sync_daily_actions(
    *,
    used: int,
    day_key: str | None,
    now: datetime,
    daily_cap: int,
) -> tuple[int, str, int]:
    """
    日切后重置已用行动次数。

    返回:
        (used, day_key, remaining)。
    """
    today = utc_day_key(now)
    if day_key != today:
        used = 0
        day_key = today
    remaining = max(0, int(daily_cap) - int(used))
    return int(used), str(day_key), remaining


def check_action_cost(
    *,
    stamina: int,
    daily_remaining: int,
    cost: int,
) -> tuple[bool, int | None, str]:
    """
    校验一次行动的体力与日行动。

    返回:
        (ok, error_code, message)。
    """
    cost = max(0, int(cost))
    if cost <= 0:
        return True, None, ""
    if daily_remaining <= 0:
        return False, ERR_DAILY_ACTIONS_EXHAUSTED, "化身今日行动次数已用尽"
    if stamina < cost:
        return False, ERR_STAMINA_INSUFFICIENT, f"化身体力不足（需要 {cost}）"
    return True, None, ""


__all__ = [
    "ERR_FEATURE_LOCKED",
    "ERR_STAMINA_INSUFFICIENT",
    "ERR_DAILY_ACTIONS_EXHAUSTED",
    "ERR_SOLO_FORMATION_INVALID",
    "AvatarFeature",
    "major_realm_order",
    "realm_meets_unlock",
    "can_condense",
    "build_condense_eligibility",
    "build_initial_stats",
    "validate_transfer_resource",
    "is_allowed_avatar_idle_direction",
    "feature_required_for_idle",
    "is_feature_unlocked",
    "check_feature_or_error",
    "list_feature_states",
    "resolve_retention_ratio",
    "compute_transfer_preview",
    "stamina_cap_for_major",
    "apply_stamina_recovery",
    "utc_day_key",
    "sync_daily_actions",
    "check_action_cost",
]
