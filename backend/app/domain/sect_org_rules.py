"""
宗门组织纯规则（M7-V+ · 无 IO）。

含：职位链、任命权、唯一性、当日任命锁、贡献自升、
设施/宗门等级门槛、藏宝阁页权限、议事厅动作、buff 上限。
"""

from __future__ import annotations

from typing import Any

# 旧 role → 新 rank（兼容展示与回填）
LEGACY_ROLE_TO_RANK: dict[str, str] = {
    "founder": "founder",
    "leader": "leader",
    "elder": "outer_elder",
    "member": "outer_disciple",
}

# 新 rank → 旧 role（双写兼容）
RANK_TO_LEGACY_ROLE: dict[str, str] = {
    "founder": "founder",
    "leader": "leader",
    "supreme_elder": "elder",
    "grand_elder": "elder",
    "inner_elder": "elder",
    "outer_elder": "elder",
    "inner_deacon": "member",
    "outer_deacon": "member",
    "core_disciple": "member",
    "inner_disciple": "member",
    "outer_disciple": "member",
    "laborer": "member",
}


def normalize_member_rank(rank: str | None, role: str | None = None) -> str:
    """
    规范化成员职位键。

    Args:
        rank: 新职位字段。
        role: 旧兼容字段。

    Returns:
        str: 有效职位键；缺省 laborer。
    """
    if rank and str(rank) not in ("", "member"):
        # 若仍是旧四档写在 rank 上，映射之
        if rank in LEGACY_ROLE_TO_RANK and rank in ("founder", "leader", "elder", "member"):
            return LEGACY_ROLE_TO_RANK[rank]
        return str(rank)
    if role:
        return LEGACY_ROLE_TO_RANK.get(str(role), "laborer")
    return "laborer"


def rank_label_zh(rank: str, disciple_ranks: dict[str, dict[str, Any]]) -> str:
    """
    职位中文名。

    Args:
        rank: 职位键。
        disciple_ranks: YAML disciple_ranks。

    Returns:
        str: 中文名。
    """
    body = disciple_ranks.get(rank) or {}
    return str(body.get("label_zh") or rank)


def grade_label_zh(grade: str, sect_grades: dict[str, dict[str, Any]]) -> str:
    """宗门等级中文名。"""
    body = sect_grades.get(grade) or {}
    return str(body.get("label_zh") or grade)


def specialty_label_zh(specialty: str | None, specialties: dict[str, dict[str, Any]]) -> str:
    """专精中文名。"""
    if not specialty:
        return "未定"
    body = specialties.get(specialty) or {}
    return str(body.get("label_zh") or specialty)


def ordered_grade_ids(sect_grades: dict[str, dict[str, Any]]) -> list[str]:
    """按 order 升序返回等级键。"""
    return sorted(
        sect_grades.keys(),
        key=lambda k: int((sect_grades.get(k) or {}).get("order") or 0),
    )


def ordered_rank_ids(disciple_ranks: dict[str, dict[str, Any]]) -> list[str]:
    """按 order 升序返回职位键。"""
    return sorted(
        disciple_ranks.keys(),
        key=lambda k: int((disciple_ranks.get(k) or {}).get("order") or 0),
    )


def next_grade_id(
    current: str,
    sect_grades: dict[str, dict[str, Any]],
) -> str | None:
    """
    下一宗门等级键；已达最高返回 None。

    Args:
        current: 当前等级。
        sect_grades: 等级表。

    Returns:
        str | None: 下一档键。
    """
    chain = ordered_grade_ids(sect_grades)
    if current not in chain:
        return chain[0] if chain else None
    idx = chain.index(current)
    if idx + 1 >= len(chain):
        return None
    return chain[idx + 1]


def can_self_apply_rank(
    *,
    current_rank: str,
    target_rank: str,
    contribution: int,
    disciple_ranks: dict[str, dict[str, Any]],
) -> tuple[bool, str | None]:
    """
    校验贡献自升 / 自荐是否可申请。

    外门长老及之前：self_apply 且贡献达标且目标高于当前。
    需任命职位：self_apply=true 但 appoint_by 非空 → 仅毛遂自荐（不自动过到职）。

    Args:
        current_rank: 当前职位。
        target_rank: 目标职位。
        contribution: 个人贡献。
        disciple_ranks: 职位表。

    Returns:
        tuple: (是否可申, 拒绝原因)。
    """
    target = disciple_ranks.get(target_rank)
    if not target:
        return False, "未知目标职位"
    if not bool(target.get("self_apply")):
        return False, "该职位不可自荐/自升"
    cur_order = int((disciple_ranks.get(current_rank) or {}).get("order") or 0)
    tgt_order = int(target.get("order") or 0)
    if tgt_order <= cur_order:
        return False, "目标职位不高于当前"
    need = int(target.get("contrib_required") or 0)
    appoint_by = list(target.get("appoint_by") or [])
    # 需任命的职位：允许毛遂自荐（贡献门槛可为 0）
    if appoint_by:
        return True, None
    if contribution < need:
        return False, f"贡献不足：须达 {need}"
    return True, None


def application_is_auto_passable(target_rank: str, disciple_ranks: dict[str, dict[str, Any]]) -> bool:
    """
    申请是否可在次日自动通过（仅无 appoint_by 的贡献自升档）。

    Args:
        target_rank: 目标职位。
        disciple_ranks: 职位表。

    Returns:
        bool: True 则可 auto_pass。
    """
    target = disciple_ranks.get(target_rank) or {}
    if list(target.get("appoint_by") or []):
        return False
    return bool(target.get("self_apply"))


def can_appoint(
    *,
    actor_rank: str,
    target_rank: str,
    disciple_ranks: dict[str, dict[str, Any]],
) -> tuple[bool, str | None]:
    """
    校验任命权。

    Args:
        actor_rank: 任命者职位。
        target_rank: 被任命目标职位。
        disciple_ranks: 职位表。

    Returns:
        tuple: (是否可任命, 原因)。
    """
    target = disciple_ranks.get(target_rank)
    if not target:
        return False, "未知目标职位"
    appoint_by = [str(x) for x in (target.get("appoint_by") or [])]
    if not appoint_by:
        return False, "该职位不可任命（须贡献自升）"
    if actor_rank not in appoint_by:
        return False, "无权任命该职位"
    return True, None


def unique_rank_occupied(
    *,
    target_rank: str,
    existing_ranks: list[str],
    disciple_ranks: dict[str, dict[str, Any]],
    exclude_character_rank: str | None = None,
) -> bool:
    """
    唯一职位是否已被占用。

    Args:
        target_rank: 目标。
        existing_ranks: 宗内现有职位列表。
        disciple_ranks: 配置。
        exclude_character_rank: 被任命者当前职位（换职时排除自身）。

    Returns:
        bool: True 表示已被占。
    """
    body = disciple_ranks.get(target_rank) or {}
    if not bool(body.get("unique")):
        return False
    count = sum(1 for r in existing_ranks if r == target_rank)
    if exclude_character_rank == target_rank and count <= 1:
        return False
    return count >= 1


def appoint_locked_same_day(
    *,
    last_appoint_game_day: int | None,
    current_game_day: int,
) -> bool:
    """任命后当日不可再改。"""
    if last_appoint_game_day is None:
        return False
    return int(last_appoint_game_day) == int(current_game_day)


def can_upgrade_facility(
    *,
    facility_id: str,
    current_level: int,
    sect_grade: str,
    facility_defs: dict[str, dict[str, Any]],
    sect_grades: dict[str, dict[str, Any]],
) -> tuple[bool, str | None, int]:
    """
    校验设施升级。

    Returns:
        tuple: (可否, 原因, 下一等级)。
    """
    fdef = facility_defs.get(facility_id)
    if not fdef:
        return False, "未知设施", current_level
    next_level = int(current_level) + 1
    hard_cap = int(fdef.get("max_level") or 10)
    grade_cap = int((sect_grades.get(sect_grade) or {}).get("facility_level_cap") or hard_cap)
    cap = min(hard_cap, grade_cap)
    if next_level > cap:
        return False, f"已达本宗门等级设施上限（{cap}）", current_level
    return True, None, next_level


def can_upgrade_sect_grade(
    *,
    current_grade: str,
    facility_levels: dict[str, int],
    sect_grades: dict[str, dict[str, Any]],
    is_npc: bool,
) -> tuple[bool, str | None, str | None]:
    """
    校验升宗门等级。

    Returns:
        tuple: (可否, 原因, 下一等级键)。
    """
    if is_npc:
        return False, "NPC 宗门不可升级宗门等级", None
    nxt = next_grade_id(current_grade, sect_grades)
    if not nxt:
        return False, "已达最高宗门等级", None
    reqs = dict((sect_grades.get(nxt) or {}).get("upgrade_require_facilities") or {})
    for fid, need_lv in reqs.items():
        have = int(facility_levels.get(str(fid)) or 0)
        if have < int(need_lv):
            return (
                False,
                f"设施不足：{fid} 须达 {need_lv} 级（当前 {have}）",
                nxt,
            )
    return True, None, nxt


def treasury_page_allowed(
    *,
    rank: str,
    page: int,
    disciple_ranks: dict[str, dict[str, Any]],
) -> bool:
    """藏宝阁页是否在职位分配权限内（page>=1）。"""
    if page <= 0:
        return False
    max_page = int((disciple_ranks.get(rank) or {}).get("treasury_page_max") or 0)
    return page <= max_page


def deposit_type_forbidden(item_type: str, forbidden: list[str]) -> bool:
    """图纸类是否禁止入藏宝阁。"""
    return str(item_type) in {str(x) for x in forbidden}


def council_action_allowed(
    *,
    rank: str,
    action: str,
    disciple_ranks: dict[str, dict[str, Any]],
) -> bool:
    """议事厅动作是否允许。"""
    actions = (disciple_ranks.get(rank) or {}).get("council_actions") or []
    return str(action) in {str(a) for a in actions}


def can_toggle_buff(
    *,
    buff_id: str,
    active_buffs: list[str],
    enable: bool,
    sect_grade: str,
    sect_buffs: dict[str, dict[str, Any]],
    sect_grades: dict[str, dict[str, Any]],
) -> tuple[bool, str | None]:
    """
    校验开启/关闭宗门 buff。

    Args:
        buff_id: buff 键。
        active_buffs: 当前已开。
        enable: True=开启。
        sect_grade: 宗门等级。
        sect_buffs: buff 表。
        sect_grades: 等级表。

    Returns:
        tuple: (可否, 原因)。
    """
    body = sect_buffs.get(buff_id)
    if not body:
        return False, "未知增益"
    if not enable:
        return True, None
    if buff_id in active_buffs:
        return False, "该增益已开启"
    grade = sect_grades.get(sect_grade) or {}
    max_active = int(grade.get("max_active_buffs") or 1)
    if len(active_buffs) >= max_active:
        return False, f"同时可开启增益已达上限（{max_active}）"
    tier = int(body.get("tier") or 1)
    tier_cap = int(grade.get("buff_tier_cap") or 1)
    if tier > tier_cap:
        return False, f"宗门等级不足：该增益需档位 ≤{tier_cap}"
    return True, None


def facility_upgrade_cost(
    *,
    current_level: int,
    cost_base: int,
    cost_per_level: int,
) -> int:
    """设施升到下一级所需贡献。"""
    return int(cost_base) + int(current_level) * int(cost_per_level)


def mine_daily_yield(
    *,
    grade_order: int,
    facility_level: int,
    mine_yield: dict[str, Any],
) -> int:
    """
    （兼容）旧矿脉日产估算。

    新逻辑请用 ``mine_pool_rate_per_hour``；保留本函数供旧测试/脚本。
    """
    # 兼容旧键 base；新配置用 base_pool_per_hour
    if "base_pool_per_hour" in mine_yield:
        return int(mine_pool_rate_per_hour(
            grade_order=grade_order,
            facility_level=facility_level,
            miner_count=0,
            mine_yield=mine_yield,
        ))
    base = int(mine_yield.get("base") or 100)
    per_g = int(mine_yield.get("per_grade_order") or 40)
    per_f = int(mine_yield.get("per_facility_level") or 30)
    return base + grade_order * per_g + facility_level * per_f


def mine_pool_rate_per_hour(
    *,
    grade_order: int,
    facility_level: int,
    miner_count: int,
    mine_yield: dict[str, Any],
) -> float:
    """
    矿脉入宗门库的灵石/小时（含采矿加速）。

    Args:
        grade_order: 宗门等级序。
        facility_level: 矿脉设施等级。
        miner_count: 当前采矿席位数。
        mine_yield: ``sects.yaml`` mine_yield 段。

    Returns:
        每小时灵石速率（浮点，结算时再取整）。
    """
    base = float(
        mine_yield["base_pool_per_hour"]
        if mine_yield.get("base_pool_per_hour") is not None
        else mine_yield.get("base", 60),
    )
    per_g = float(
        mine_yield["per_grade_order"]
        if mine_yield.get("per_grade_order") is not None
        else 25,
    )
    per_f = float(
        mine_yield["per_facility_level"]
        if mine_yield.get("per_facility_level") is not None
        else 20,
    )
    raw = base + int(grade_order) * per_g + int(facility_level) * per_f
    bonus_pct = float(
        mine_yield["miner_pool_bonus_pct"]
        if mine_yield.get("miner_pool_bonus_pct") is not None
        else 0.12,
    )
    return raw * (1.0 + max(0, int(miner_count)) * bonus_pct)


def mine_max_miners(
    *,
    grade_order: int,
    facility_level: int,
    mine_yield: dict[str, Any],
) -> int:
    """采矿名额上限（矿脉等级 + 宗门等级）。"""
    base = int(mine_yield.get("max_miners_base") or 2)
    per_f = int(mine_yield.get("max_miners_per_facility_level") or 1)
    per_g = int(mine_yield.get("max_miners_per_grade_order") or 1)
    return max(1, base + int(facility_level) * per_f + int(grade_order) * per_g)


def herb_plot_capacity(
    *,
    rank: str,
    facility_level: int,
    herb_garden: dict[str, Any],
) -> int:
    """灵药园一次可种植地块数。"""
    base = int(herb_garden.get("base_plots") or 1)
    per_f = int(herb_garden.get("per_facility_level") or 1)
    bonus_map = dict(herb_garden.get("rank_plot_bonus") or {})
    bonus = int(bonus_map.get(rank) or 0)
    return max(1, base + facility_level * per_f + bonus)


def cultivation_above(
    *,
    actor_cultivation: int,
    leader_cultivation: int,
) -> bool:
    """大长老须高于掌门修为。"""
    return int(actor_cultivation) > int(leader_cultivation)
