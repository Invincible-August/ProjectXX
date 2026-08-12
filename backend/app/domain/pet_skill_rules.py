"""
PET-D02 灵宠技能领域：装备栏校验、技能书 scope、互斥标签。
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def normalize_equipped_slots(
    equipped: Sequence[str | None],
    *,
    equip_slots: int = 4,
) -> list[str | None]:
    """
    规范装备栏长度为 equip_slots；多余截断，不足补 None。

    参数:
        equipped: 技能 id 或空槽。
        equip_slots: 栏位数（1～4）。
    """
    slots = max(1, min(4, int(equip_slots)))
    out: list[str | None] = []
    for i in range(slots):
        if i < len(equipped):
            raw = equipped[i]
            out.append(str(raw).strip() if raw else None)
        else:
            out.append(None)
    return out


def validate_equip_loadout(
    equipped: Sequence[str | None],
    *,
    learned: Sequence[str],
    skills: Mapping[str, Any],
    equip_slots: int = 4,
) -> list[str | None]:
    """
    校验并返回规范化装备栏。

    Raises:
        ValueError: 未学、未知技能、重复、互斥冲突。
    """
    slots = normalize_equipped_slots(equipped, equip_slots=equip_slots)
    learned_set = {str(x) for x in learned}
    seen: set[str] = set()
    used_mutex: dict[str, str] = {}
    for skill_id in slots:
        if not skill_id:
            continue
        if skill_id not in skills:
            raise ValueError(f"未知技能：{skill_id}")
        if skill_id not in learned_set:
            raise ValueError(f"尚未学会技能：{skill_id}")
        if skill_id in seen:
            raise ValueError(f"不可重复装备：{skill_id}")
        seen.add(skill_id)
        cfg = skills[skill_id]
        tags = getattr(cfg, "mutex_tags", ()) or ()
        for tag in tags:
            tag_s = str(tag)
            if not tag_s:
                continue
            if tag_s in used_mutex:
                raise ValueError(
                    f"互斥标签冲突：{tag_s}（{used_mutex[tag_s]} vs {skill_id}）",
                )
            used_mutex[tag_s] = skill_id
    return slots


def can_learn_from_pool(skill_id: str, pool_skill_ids: Sequence[str]) -> bool:
    """技能是否在物种池内。"""
    return str(skill_id) in {str(x) for x in pool_skill_ids}


def book_eligible_for_pet(
    book: Any,
    *,
    race_id: str,
    species_id: str,
) -> bool:
    """
    技能书 scope 是否允许该宠学习。

    参数:
        book: 含 scope / race_id / species_id 的配置对象。
    """
    scope = str(getattr(book, "scope", "universal"))
    if scope == "universal":
        return True
    if scope == "race":
        return str(getattr(book, "race_id", "") or "") == str(race_id)
    if scope == "species":
        return str(getattr(book, "species_id", "") or "") == str(species_id)
    return False


def default_skills_for_pool(
    pool: Any,
    *,
    equip_slots: int = 4,
) -> tuple[list[str], list[str | None]]:
    """
    捕获时从池取默认已学与装备栏。

    返回:
        (learned, equipped)。
    """
    learned = [str(x) for x in (getattr(pool, "default_learned", ()) or ()) if x]
    equipped_raw = [str(x) if x else None for x in (getattr(pool, "default_equipped", ()) or ())]
    for sid in equipped_raw:
        if sid and sid not in learned:
            learned.append(sid)
    equipped = normalize_equipped_slots(equipped_raw, equip_slots=equip_slots)
    return learned, equipped
