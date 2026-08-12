"""
M4 神识读数服务（薄包装 + domain 纯函数；M4-D03 阶梯/反噬）。
"""

from __future__ import annotations

import logging
from typing import Any

from app.db.models.character import Character
from app.domain.divine_sense import (
    BacklashEntry,
    OverloadBand,
    compute_capacity,
    compute_load,
    overload_multiplier,
    resolve_backlash_entry,
    resolve_overload_band,
    should_trigger_backlash,
    soft_hard_caps,
)
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)


class DivineSenseService:
    """神识容量、占用、阶梯超载与反噬表。"""

    @staticmethod
    def snapshot_for_character(
        character: Character,
        *,
        avatar_deploy_count: int = 0,
        pet_deploy_count: int = 0,
        pet_costs: list[int] | None = None,
    ) -> dict[str, Any]:
        """
        计算角色神识读数（不上阵时 load=0）。

        参数:
            character: 角色 ORM。
            avatar_deploy_count: 当前编成的化身数。
            pet_deploy_count: 当前编成的灵宠数（无 pet_costs 时）。
            pet_costs: 可选各宠占用（含物种覆盖）。

        返回:
            capacity / load / soft_cap / hard_cap / backlash / overload_mult /
            zone / backlash_tier / idle_mult。
        """
        cfg = get_game_config().divine_sense
        capacity = compute_capacity(
            base_capacity=cfg.base_capacity,
            per_realm_bonus=cfg.per_realm_bonus,
            character_major=character.major_realm,
            bonus_from_gm=int(character.divine_sense_capacity_bonus),
        )
        load = compute_load(
            avatar_count=avatar_deploy_count,
            pet_count=pet_deploy_count,
            cost_avatar=cfg.cost_avatar,
            cost_pet=cfg.cost_pet,
            pet_costs=pet_costs,
        )
        soft, hard = soft_hard_caps(
            capacity,
            soft_ratio=cfg.soft_ratio,
            hard_ratio=cfg.hard_ratio,
        )
        bands = [
            OverloadBand(
                max_load_ratio=b.max_load_ratio,
                combat_stat_mult=b.combat_stat_mult,
                zone=b.zone,
            )
            for b in cfg.overload_bands
        ]
        band = resolve_overload_band(
            load,
            capacity,
            soft_cap=soft,
            bands=bands,
            fallback_stat_mult=cfg.overload_stat_mult,
        )
        mult = float(band.combat_stat_mult)
        over_hard = should_trigger_backlash(load, hard)
        table = [
            BacklashEntry(
                id=t.id,
                when=t.when,
                idle_mult=t.idle_mult,
                set_flag=t.set_flag,
                summary=t.summary,
            )
            for t in cfg.backlash_table
        ]
        entry = resolve_backlash_entry(
            over_hard=over_hard,
            table=table,
            fallback_idle_mult=cfg.backlash_idle_mult,
        )
        backlash = bool(character.divine_sense_backlash) or over_hard
        if over_hard and not character.divine_sense_backlash:
            logger.info(
                "divine sense backlash triggered character_id=%s load=%s hard=%s tier=%s",
                character.id,
                load,
                hard,
                entry.id if entry else None,
            )
        idle_mult = (
            float(entry.idle_mult)
            if backlash and entry is not None
            else (cfg.backlash_idle_mult if backlash else 1.0)
        )
        return {
            "capacity": capacity,
            "load": load,
            "soft_cap": soft,
            "hard_cap": hard,
            "backlash": backlash,
            "overload_mult": mult,
            "zone": band.zone,
            "backlash_tier": entry.id if (backlash and entry) else None,
            "idle_mult": idle_mult if backlash else 1.0,
            "backlash_summary": entry.summary if (backlash and entry) else None,
        }

    @staticmethod
    def count_deployed_from_units(
        units: list[dict[str, Any]],
    ) -> tuple[int, int, list[int]]:
        """
        从编成统计上阵化身数、灵宠数与各宠神识占用。

        Returns:
            (avatar_count, pet_count, pet_costs)。
        """
        cfg = get_game_config()
        ds = cfg.divine_sense
        pets_cfg = cfg.pets
        avatars = 0
        pet_costs: list[int] = []
        for u in units:
            kind = str(u.get("unit_kind") or "")
            if kind == "avatar":
                avatars += 1
            elif kind == "pet":
                cost = ds.cost_pet
                ref_id = u.get("ref_id")
                species_id = u.get("species_id")
                if species_id and species_id in pets_cfg.species:
                    override = pets_cfg.species[str(species_id)].divine_sense_cost
                    if override is not None:
                        cost = int(override)
                elif ref_id is not None:
                    # 开战/快照单元可能只有 ref_id；成本覆盖在有 species 时生效
                    pass
                pet_costs.append(cost)
        return avatars, len(pet_costs), pet_costs
