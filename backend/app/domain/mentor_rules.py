"""师徒领域纯规则（M7 L6 · 无 IO）。"""

from __future__ import annotations

from typing import Any


def realm_index(major_realm: str, realm_order: list[str]) -> int:
    """
    大境界在链上的下标；未知视为 -1。

    Args:
        major_realm: 境界键。
        realm_order: 有序大境界键。

    Returns:
        int: 下标。
    """
    key = str(major_realm or "")
    try:
        return realm_order.index(key)
    except ValueError:
        return -1


def master_realm_ok(
    *,
    master_major: str,
    apprentice_major: str,
    realm_order: list[str],
    min_gap: int,
) -> tuple[bool, str | None]:
    """
    校验师傅境界是否高于徒弟足够档位。

    Args:
        master_major: 师傅大境界。
        apprentice_major: 徒弟大境界。
        realm_order: 境界链。
        min_gap: 最小档差。

    Returns:
        tuple: (允许, 中文原因)。
    """
    if int(min_gap) <= 0:
        return True, None
    mi = realm_index(master_major, realm_order)
    ai = realm_index(apprentice_major, realm_order)
    if mi < 0 or ai < 0:
        return False, "境界配置异常"
    if mi - ai < int(min_gap):
        return False, f"师傅须至少高出徒弟 {min_gap} 个大境界"
    return True, None


def should_auto_graduate(
    *,
    master_major: str,
    apprentice_major: str,
    realm_order: list[str],
    max_gap: int = 0,
) -> bool:
    """
    弟子追上师傅大境界（差 ≤ max_gap）时应自动出师。

    Args:
        master_major: 师傅大境界。
        apprentice_major: 徒弟大境界。
        realm_order: 境界链。
        max_gap: 允许的最大档差（默认 0=同境界）。

    Returns:
        bool: 是否应出师。
    """
    mi = realm_index(master_major, realm_order)
    ai = realm_index(apprentice_major, realm_order)
    if mi < 0 or ai < 0:
        return False
    return mi - ai <= int(max_gap)


def lesson_transfer_amount(
    *,
    apprentice_need: int,
    master_pool: int,
    need_ratio: float = 1.0,
    pool_ratio: float = 0.1,
) -> int:
    """
    日课转移量：min(弟子需求×比例, 师傅池×比例)。

    Args:
        apprentice_need: 弟子当前档突破总需求（或功法下级消耗）。
        master_pool: 师傅对应资源池。
        need_ratio: 弟子需求占比上限。
        pool_ratio: 师傅池占比上限。

    Returns:
        int: 可转移非负整数。
    """
    need_cap = max(0, int(float(apprentice_need) * float(need_ratio)))
    pool_cap = max(0, int(float(master_pool) * float(pool_ratio)))
    return max(0, min(need_cap, pool_cap))


def teach_sessions_required(
    *,
    item_kind: str,
    item_meta: dict[str, Any] | None,
    teach_cfg: dict[str, Any],
) -> int:
    """
    Resolve required transmission sessions for a technique/recipe.

    Args:
        item_kind: ``technique`` | ``recipe``.
        item_meta: Catalog entry (technique or recipe dict).
        teach_cfg: ``mentor.teach`` config block.

    Returns:
        int: Sessions needed (≥1).
    """
    meta = dict(item_meta or {})
    if meta.get("teach_sessions") is not None:
        return max(1, int(meta["teach_sessions"]))
    tier = str(meta.get("teach_tier") or "").strip().lower()
    sessions_by_tier = dict(teach_cfg.get("sessions_by_tier") or {})
    if not tier and item_kind == "recipe":
        branch = str(meta.get("branch") or "")
        branch_tier = dict(teach_cfg.get("recipe_branch_tier") or {})
        tier = str(branch_tier.get(branch) or "")
    if not tier and item_kind == "technique":
        tier = str(teach_cfg.get("technique_default_tier") or "t1")
    if tier and tier in sessions_by_tier:
        return max(1, int(sessions_by_tier[tier]))
    return max(1, int(teach_cfg.get("default_sessions") or 1))


def disciple_ordinal_title(index: int) -> str:
    """
    按拜师顺序生成弟子称谓（0→大弟子）。

    Args:
        index: 0-based 序位。

    Returns:
        str: 如「大弟子」「二弟子」。
    """
    labels = ("大", "二", "三", "四", "五", "六", "七", "八", "九", "十")
    i = max(0, int(index))
    if i < len(labels):
        return f"{labels[i]}弟子"
    return f"{i + 1}弟子"


def direct_can_clear(
    *,
    set_day_key: str | None,
    today_key: str,
    cooldown_days: int,
) -> bool:
    """
    指定亲传后是否已过冷却、可解除。

    Args:
        set_day_key: 指定日 YYYY-MM-DD。
        today_key: 今日。
        cooldown_days: 冷却天数（1=隔日可解除）。

    Returns:
        bool: 是否可解除。
    """
    if not set_day_key:
        return True
    days = max(0, int(cooldown_days))
    if days <= 0:
        return True
    from datetime import datetime, timedelta

    set_d = datetime.strptime(str(set_day_key)[:10], "%Y-%m-%d").date()
    today = datetime.strptime(str(today_key)[:10], "%Y-%m-%d").date()
    return today >= set_d + timedelta(days=days)


def direct_can_appoint(
    *,
    cleared_day_key: str | None,
    today_key: str,
) -> bool:
    """
    解除亲传后当日是否可再指定同一人。

    Args:
        cleared_day_key: 解除日。
        today_key: 今日。

    Returns:
        bool: 是否可指定。
    """
    if not cleared_day_key:
        return True
    return str(cleared_day_key)[:10] != str(today_key)[:10]


def lesson_kind_daily_cap(
    *,
    kind: str,
    is_direct: bool,
    direct_cfg: dict[str, Any] | None,
) -> int:
    """
    日课各类型每日上限。亲传：授业/解惑 +bonus；传道不变。

    Args:
        kind: ``dao`` | ``craft`` | ``technique``.
        is_direct: 是否亲传弟子。
        direct_cfg: ``mentor.direct_disciple`` 配置。

    Returns:
        int: 该类型每日可做次数（≥1）。
    """
    base = 1
    cfg = dict(direct_cfg or {})
    if not is_direct:
        return base
    kind_l = str(kind or "").strip().lower()
    if kind_l == "craft":
        return base + max(0, int(cfg.get("craft_lesson_bonus") or 1))
    if kind_l == "technique":
        return base + max(0, int(cfg.get("technique_lesson_bonus") or 1))
    return base


def same_region_stub(*, stub_enabled: bool) -> bool:
    """
    M7 同图判定桩：开启则一律视为同区。

    Args:
        stub_enabled: SAME_REGION_STUB / YAML。

    Returns:
        bool: 是否同区。
    """
    return bool(stub_enabled)
