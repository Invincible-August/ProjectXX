"""
M4/N4/PET-D01～D02/D06 灵宠应用服务：持有、捕获、图鉴、词条、升阶、数值洗炼、灵兽宗改类型。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.character import Character
from app.db.models.pet import Pet
from app.db.models.pet_dex import PetDexEntry
from app.domain.pet_feed_rules import (
    accumulate_feed_effects,
    resolve_total_feed_cap,
    total_feed_used,
    validate_feed_batch,
)
from app.domain.pet_passive_rules import (
    collect_combat_passive_effects,
    resolve_affix_passive_ids,
    roll_independent_passive,
)
from app.domain.pet_rules import (
    append_affix_on_grade_up,
    can_hold_more,
    combat_stats_from_level,
    fill_affix_slots,
    grade_up_spirit_cost,
    pick_capture_test_grade,
    pick_capture_test_species,
    reroll_affix_type,
    reroll_affix_value_only,
    roll_one_affix,
    species_base_dict,
    type_reroll_cost,
    value_reroll_cost,
)
from app.domain.pet_skill_rules import (
    book_eligible_for_pet,
    can_learn_from_pool,
    default_skills_for_pool,
    normalize_equipped_slots,
    validate_equip_loadout,
)
from app.schemas.common import AppError
from app.services.m4_features import require_pets_enabled
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)


def spirit_beast_sect_enabled() -> bool:
    """
    灵兽宗设施闸是否开放（sects.facilities.spirit_beast_sect）。

    Returns:
        True 表示玩家可走改词条类型流程。
    """
    facility = get_game_config().sects.facilities.get("spirit_beast_sect") or {}
    return bool(facility.get("enabled"))


class PetService:
    """
    灵宠用例（N4 + PET-D01 词条 + PET-D02 技能 + PET-D06 改类型）。

    属性:
        _session: 请求级异步会话。
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        参数:
            session: SQLAlchemy 异步会话。
        """
        self._session = session

    def _grade_mult(self, grade: int) -> float:
        """读品阶基础乘区；缺省 1.0。"""
        cfg = get_game_config().pets
        entry = cfg.grades.get(int(grade))
        return float(entry.base_mult) if entry is not None else 1.0

    def _load_affixes(self, pet: Pet) -> list[dict[str, Any]]:
        """解析 pets.affixes_json；坏 JSON 视为空列表。"""
        raw = getattr(pet, "affixes_json", None) or "[]"
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            logger.warning("pet affixes_json corrupt pet_id=%s", getattr(pet, "id", None))
            return []
        if not isinstance(data, list):
            return []
        return [dict(x) for x in data if isinstance(x, dict)]

    def _save_affixes(self, pet: Pet, affixes: list[dict[str, Any]]) -> None:
        """写回词条 JSON。"""
        pet.affixes_json = json.dumps(affixes, ensure_ascii=False)

    def _load_value_reroll_counts(self, pet: Pet) -> dict[str, int]:
        """解析各槽数值洗炼次数。"""
        raw = getattr(pet, "value_reroll_counts_json", None) or "{}"
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(k): int(v) for k, v in data.items()}

    def _save_value_reroll_counts(self, pet: Pet, counts: dict[str, int]) -> None:
        """写回洗炼次数 JSON。"""
        pet.value_reroll_counts_json = json.dumps(counts, ensure_ascii=False)

    def _load_type_reroll_counts(self, pet: Pet) -> dict[str, int]:
        """解析各槽改词条类型次数（PET-D06）。"""
        raw = getattr(pet, "type_reroll_counts_json", None) or "{}"
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(k): int(v) for k, v in data.items()}

    def _save_type_reroll_counts(self, pet: Pet, counts: dict[str, int]) -> None:
        """写回改类型次数 JSON。"""
        pet.type_reroll_counts_json = json.dumps(counts, ensure_ascii=False)

    def _type_reroll_slots_for_grade(self, grade: int) -> int:
        """品阶表 type_reroll_slots；夹在 1～4。"""
        cfg = get_game_config().pets
        entry = cfg.grades.get(int(grade))
        if entry is None:
            return 1
        return max(1, min(4, int(entry.type_reroll_slots)))

    def _next_type_reroll_preview(
        self,
        counts: dict[str, int],
        slot_index: int,
        *,
        type_reroll_slots: int,
    ) -> dict[str, Any]:
        """预览下一次改类型费用与是否可改。"""
        sect = get_game_config().pets.sect_reroll or {}
        already = int(counts.get(str(slot_index), 0))
        eligible = 0 <= int(slot_index) < int(type_reroll_slots)
        cost = type_reroll_cost(
            base_1=float(sect.get("base_1", 100)),
            grow=float(sect.get("grow", 0.1)),
            slot_ordinal_1based=int(slot_index) + 1,
            times_already=already,
        )
        return {
            "slot_index": int(slot_index),
            "slot_ordinal": int(slot_index) + 1,
            "times_already": already,
            "next_cost_spirit_stones": cost,
            "eligible": eligible,
        }

    def _load_skills_learned(self, pet: Pet) -> list[str]:
        """解析已学技能 id 列表。"""
        raw = getattr(pet, "skills_learned_json", None) or "[]"
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        return [str(x) for x in data if x]

    def _load_skills_equipped(self, pet: Pet) -> list[str | None]:
        """解析装备栏（最多 4）。"""
        raw = getattr(pet, "skills_equipped_json", None) or "[]"
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            data = []
        if not isinstance(data, list):
            data = []
        slots = get_game_config().pet_skills.equip_slots
        return normalize_equipped_slots(
            [str(x) if x else None for x in data],
            equip_slots=slots,
        )

    def _save_skills(self, pet: Pet, *, learned: list[str], equipped: list[str | None]) -> None:
        """写回已学与装备栏。"""
        pet.skills_learned_json = json.dumps(learned, ensure_ascii=False)
        pet.skills_equipped_json = json.dumps(equipped, ensure_ascii=False)

    def _load_rolled_passives(self, pet: Pet) -> list[str]:
        """解析独立被动 id 列表（可空）。"""
        raw = getattr(pet, "passives_json", None) or "[]"
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        return [str(x) for x in data if x]

    def _save_passives(
        self,
        pet: Pet,
        *,
        racial_talent_id: str,
        rolled: list[str],
    ) -> None:
        """写回种族天赋与独立被动。"""
        pet.racial_talent_id = str(racial_talent_id or "")
        pet.passives_json = json.dumps(list(rolled), ensure_ascii=False)

    def _passive_public(self, passive_id: str | None) -> dict[str, Any] | None:
        """被动 id → 展示字典。"""
        if not passive_id:
            return None
        cfg = get_game_config().pet_passives.passives.get(passive_id)
        if cfg is None:
            return {"passive_id": passive_id, "name": passive_id, "missing": True}
        return {
            "passive_id": cfg.passive_id,
            "name": cfg.name,
            "kind": cfg.kind,
            "effect_domain": cfg.effect_domain,
            "effects": dict(cfg.effects),
            "summary": cfg.summary,
        }

    def _passives_block_public(self, pet: Pet) -> dict[str, Any]:
        """组装被动公共字段（种族天赋必带；独立可空）。"""
        talent_id = str(getattr(pet, "racial_talent_id", "") or "")
        # 旧宠迁移：列空时回落到种族表
        if not talent_id:
            cfg = get_game_config().pets
            species = cfg.species.get(pet.species_id)
            race = cfg.races.get(species.race) if species else None
            talent_id = race.racial_talent_id if race else ""
        rolled = self._load_rolled_passives(pet)
        return {
            "racial_talent": self._passive_public(talent_id),
            "racial_talent_id": talent_id,
            "rolled": [self._passive_public(pid) for pid in rolled if self._passive_public(pid)],
            "rolled_ids": rolled,
        }

    def _combat_passive_effects_for_pet(self, pet: Pet) -> dict[str, float]:
        """汇总该宠全部 combat 被动效果（天赋+独立+词条引用）。"""
        bundle = get_game_config()
        talent_id = str(getattr(pet, "racial_talent_id", "") or "")
        if not talent_id:
            species = bundle.pets.species.get(pet.species_id)
            race = bundle.pets.races.get(species.race) if species else None
            talent_id = race.racial_talent_id if race else ""
        ids = [talent_id] if talent_id else []
        ids.extend(self._load_rolled_passives(pet))
        ids.extend(
            resolve_affix_passive_ids(
                self._load_affixes(pet),
                affix_types=bundle.pet_affixes.types,
            ),
        )
        return collect_combat_passive_effects(ids, passives=bundle.pet_passives.passives)

    def _load_feed_counts(self, pet: Pet) -> dict[str, int]:
        """解析各兽丹已喂次数。"""
        raw = getattr(pet, "feed_counts_json", None) or "{}"
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(k): int(v) for k, v in data.items()}

    def _save_feed_counts(self, pet: Pet, counts: dict[str, int]) -> None:
        """写回喂养次数。"""
        pet.feed_counts_json = json.dumps(counts, ensure_ascii=False)

    def _feed_total_cap(self, pet: Pet) -> int:
        """当前宠适用的喂养总量上限。"""
        feed_cfg = get_game_config().pet_feed
        return resolve_total_feed_cap(
            grade=int(pet.grade),
            species_id=pet.species_id,
            total_feed_cap=feed_cfg.total_feed_cap,
            by_grade=feed_cfg.total_feed_cap_by_grade,
            by_species=feed_cfg.total_feed_cap_by_species,
        )

    def _feed_effects_for_pet(self, pet: Pet) -> dict[str, float]:
        """按喂养次数汇总属性加成。"""
        feed_cfg = get_game_config().pet_feed
        return accumulate_feed_effects(
            self._load_feed_counts(pet),
            items=feed_cfg.items,
        )

    def _feed_block_public(self, pet: Pet) -> dict[str, Any]:
        """喂养状态与可喂丹药预览。"""
        feed_cfg = get_game_config().pet_feed
        counts = self._load_feed_counts(pet)
        total_cap = self._feed_total_cap(pet)
        used = total_feed_used(counts)
        items_out: list[dict[str, Any]] = []
        for item_id, cfg in feed_cfg.items.items():
            already = int(counts.get(item_id, 0))
            items_out.append(
                {
                    "item_id": item_id,
                    "name": cfg.name,
                    "per_item_cap": cfg.per_item_cap,
                    "times_fed": already,
                    "remaining": (
                        max(0, cfg.per_item_cap - already) if cfg.per_item_cap > 0 else None
                    ),
                    "effects": dict(cfg.effects),
                    "summary": cfg.summary,
                },
            )
        return {
            "total_used": used,
            "total_cap": total_cap,
            "items": items_out,
            "applied_effects": self._feed_effects_for_pet(pet),
        }

    def _skill_public(self, skill_id: str | None) -> dict[str, Any] | None:
        """技能 id → 展示字典；空槽返回 None。"""
        if not skill_id:
            return None
        cfg = get_game_config().pet_skills.skills.get(skill_id)
        if cfg is None:
            return {"skill_id": skill_id, "name": skill_id, "missing": True}
        return {
            "skill_id": cfg.skill_id,
            "name": cfg.name,
            "power": cfg.power,
            "accuracy": cfg.accuracy,
            "category": cfg.category,
            "priority": cfg.priority,
            "pp": cfg.pp,
            "mutex_tags": list(cfg.mutex_tags),
        }

    def _skills_block_public(self, pet: Pet) -> dict[str, Any]:
        """组装技能公共字段。"""
        skills_cfg = get_game_config().pet_skills
        pets_cfg = get_game_config().pets
        species = pets_cfg.species.get(pet.species_id)
        pool_id = species.skill_pool_id if species else ""
        pool = skills_cfg.pools.get(pool_id) if pool_id else None
        learned = self._load_skills_learned(pet)
        equipped = self._load_skills_equipped(pet)
        pool_ids = list(pool.skill_ids) if pool else []
        return {
            "equip_slots": skills_cfg.equip_slots,
            "skill_pool_id": pool_id,
            "pool_skill_ids": pool_ids,
            "learned": [
                self._skill_public(sid) for sid in learned if self._skill_public(sid)
            ],
            "equipped": [self._skill_public(sid) for sid in equipped],
            "learned_ids": learned,
            "equipped_ids": equipped,
        }

    def _affix_public_list(self, affixes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """词条实例 → API 展示（补 name/kind）。"""
        types = get_game_config().pet_affixes.types
        out: list[dict[str, Any]] = []
        for item in sorted(affixes, key=lambda a: int(a.get("slot_index", 0))):
            type_id = str(item.get("affix_type_id") or "")
            type_cfg = types.get(type_id)
            out.append(
                {
                    "slot_index": int(item.get("slot_index", 0)),
                    "affix_type_id": type_id,
                    "affix_type_name": type_cfg.name if type_cfg else type_id,
                    "kind": type_cfg.kind if type_cfg else "",
                    "affix_tier": str(item.get("affix_tier") or "common"),
                    "rolled_value": item.get("rolled_value"),
                    "locked": bool(item.get("locked", False)),
                },
            )
        return out

    def _stats_for_pet(self, pet: Pet) -> dict[str, int]:
        """按物种、品阶、等级与词条计算战斗面板。"""
        bundle = get_game_config()
        cfg = bundle.pets
        species = cfg.species.get(pet.species_id)
        if species is None:
            return {"atk": 1, "hp": 1, "speed": 1}
        # 被动 + 喂养效果一并叠入面板
        effects = self._combat_passive_effects_for_pet(pet)
        for key, val in self._feed_effects_for_pet(pet).items():
            effects[key] = float(effects.get(key, 0)) + float(val)
        return combat_stats_from_level(
            species_base_dict(species),
            int(pet.level),
            level_stat_bonus=cfg.level_stat_bonus,
            grade_base_mult=self._grade_mult(int(pet.grade)),
            affixes=self._load_affixes(pet),
            affix_types=bundle.pet_affixes.types,
            passive_combat_effects=effects,
        )

    def _next_value_reroll_preview(
        self,
        counts: dict[str, int],
        slot_index: int,
    ) -> dict[str, Any]:
        """预览下一次数值洗炼费用。"""
        vr = get_game_config().pet_affixes.value_reroll
        already = int(counts.get(str(slot_index), 0))
        cost = value_reroll_cost(
            base=float(vr.get("spirit_stones_base", 50)),
            grow=float(vr.get("grow", 0.1)),
            times_already=already,
        )
        return {
            "slot_index": slot_index,
            "times_already": already,
            "next_cost_spirit_stones": cost,
        }

    def _pet_to_public(self, pet: Pet) -> dict[str, Any]:
        """灵宠 ORM → 列表/详情公共字典。"""
        cfg = get_game_config().pets
        species = cfg.species.get(pet.species_id)
        race_id = species.race if species else ""
        race = cfg.races.get(race_id) if race_id else None
        grade_num = int(getattr(pet, "grade", 1) or 1)
        grade_cfg = cfg.grades.get(grade_num)
        affixes = self._load_affixes(pet)
        counts = self._load_value_reroll_counts(pet)
        reroll_previews = [
            self._next_value_reroll_preview(counts, int(a.get("slot_index", i)))
            for i, a in enumerate(affixes)
        ]
        type_slots = self._type_reroll_slots_for_grade(grade_num)
        type_counts = self._load_type_reroll_counts(pet)
        type_previews = [
            self._next_type_reroll_preview(
                type_counts,
                int(a.get("slot_index", i)),
                type_reroll_slots=type_slots,
            )
            for i, a in enumerate(affixes)
        ]
        return {
            "id": pet.id,
            "species_id": pet.species_id,
            "species_name": (
                species.name
                if species
                else f"未知({pet.species_id})"
            ),
            "race": race_id,
            "race_name": race.name if race else (f"未知({race_id})" if race_id else "未知"),
            "rarity": species.rarity if species else "common",
            "roles": list(species.roles) if species else [],
            "grade": grade_num,
            "grade_name": grade_cfg.name if grade_cfg else str(grade_num),
            "affix_slot_cap": grade_cfg.affix_slots if grade_cfg else 3,
            "type_reroll_slots": type_slots,
            "type_reroll_enabled": spirit_beast_sect_enabled(),
            "level": int(pet.level),
            "nickname": pet.nickname,
            "is_deploy_preferred": bool(pet.is_deploy_preferred),
            "affixes": self._affix_public_list(affixes),
            "value_reroll_preview": reroll_previews,
            "type_reroll_preview": type_previews,
            "skills": self._skills_block_public(pet),
            "passives": self._passives_block_public(pet),
            "feed": self._feed_block_public(pet),
            "stats": self._stats_for_pet(pet),
        }


    async def count_pets(self, character_id: int) -> int:
        """持有灵宠数量。"""
        result = await self._session.execute(
            select(func.count(Pet.id)).where(Pet.character_id == character_id),
        )
        return int(result.scalar_one())

    async def list_pets(self, character: Character) -> list[dict[str, Any]]:
        """列出全部灵宠及战斗面板预览。"""
        if not get_settings().pets_enabled:
            return []
        result = await self._session.execute(
            select(Pet)
            .where(Pet.character_id == character.id)
            .order_by(Pet.id),
        )
        return [self._pet_to_public(pet) for pet in result.scalars().all()]

    async def catalog(self, character: Character) -> dict[str, Any]:
        """
        图鉴：物种注册表投影 + 玩家 seen/caught。

        热插拔验收：仅加 YAML/覆盖层物种 → 本接口多一条。
        """
        require_pets_enabled()
        cfg = get_game_config().pets
        dex_rows = await self._session.execute(
            select(PetDexEntry).where(PetDexEntry.character_id == character.id),
        )
        dex_map = {row.species_id: row for row in dex_rows.scalars().all()}

        races_out = [
            {
                "race_id": r.race_id,
                "name": r.name,
                "racial_talent_id": r.racial_talent_id,
                "base_capture_rate": r.base_capture_rate,
            }
            for r in cfg.races.values()
        ]
        grades_out = [
            {
                "grade": g.grade,
                "name": g.name,
                "affix_slots": g.affix_slots,
                "type_reroll_slots": g.type_reroll_slots,
                "base_mult": g.base_mult,
            }
            for g in sorted(cfg.grades.values(), key=lambda x: x.grade)
        ]
        species_out: list[dict[str, Any]] = []
        for sp in cfg.species.values():
            race = cfg.races.get(sp.race)
            dex = dex_map.get(sp.species_id)
            species_out.append(
                {
                    "species_id": sp.species_id,
                    "name": sp.name,
                    "race": sp.race,
                    "race_name": race.name if race else sp.race,
                    "rarity": sp.rarity,
                    "roles": list(sp.roles),
                    "acquire_tags": list(sp.acquire_tags),
                    "base_atk": sp.base_atk,
                    "base_hp": sp.base_hp,
                    "base_speed": sp.base_speed,
                    "seen": bool(dex.seen) if dex else False,
                    "caught": bool(dex.caught) if dex else False,
                    "status": (
                        "caught"
                        if dex and dex.caught
                        else ("seen" if dex and dex.seen else "unknown")
                    ),
                },
            )
        return {
            "races": races_out,
            "grades": grades_out,
            "species": species_out,
            "hold_cap": cfg.hold_cap,
        }

    async def _mark_dex(
        self,
        character_id: int,
        species_id: str,
        *,
        caught: bool,
    ) -> None:
        """更新图鉴：遇见；可选标记已捕获。"""
        result = await self._session.execute(
            select(PetDexEntry)
            .where(
                PetDexEntry.character_id == character_id,
                PetDexEntry.species_id == species_id,
            )
            .limit(1),
        )
        row = result.scalar_one_or_none()
        if row is None:
            self._session.add(
                PetDexEntry(
                    character_id=character_id,
                    species_id=species_id,
                    seen=True,
                    caught=caught,
                ),
            )
        else:
            row.seen = True
            if caught:
                row.caught = True
        await self._session.flush()

    def _roll_capture_affixes(self, grade: int) -> list[dict[str, Any]]:
        """按品阶槽上限 roll 满词条。"""
        pets_cfg = get_game_config().pets
        affix_cfg = get_game_config().pet_affixes
        grade_cfg = pets_cfg.grades.get(int(grade))
        slots = int(grade_cfg.affix_slots) if grade_cfg else 3
        return fill_affix_slots(
            slots,
            types=affix_cfg.types,
            type_weights=affix_cfg.type_weights,
            tier_weights=affix_cfg.tier_weights,
        )

    async def capture_test(
        self,
        character: Character,
        *,
        species_id: str | None = None,
    ) -> dict[str, Any]:
        """
        测试捕获：加权抽物种/品阶，并按品阶填满词条槽。

        异常:
            AppError: 40057 持有上限；物种不存在；池空。
        """
        require_pets_enabled()
        cfg = get_game_config().pets
        resolved_species = (species_id or "").strip() or None
        if resolved_species is None:
            try:
                resolved_species = pick_capture_test_species(
                    cfg.species,
                    cfg.capture_test_weights,
                )
            except ValueError as exc:
                raise AppError(
                    code=40000,
                    message=f"测试捕获池为空：{exc}",
                    http_status=400,
                ) from exc
        if resolved_species not in cfg.species:
            raise AppError(
                code=40000,
                message=f"未知物种：{resolved_species}",
                http_status=400,
            )
        species = cfg.species[resolved_species]
        if "capture_test" not in species.acquire_tags and "gm_grant" not in species.acquire_tags:
            raise AppError(
                code=40000,
                message=f"物种 {resolved_species} 不允许 capture_test",
                http_status=400,
            )
        grade = pick_capture_test_grade(cfg.capture_test_grade_weights)
        if cfg.grades and grade not in cfg.grades:
            grade = min(cfg.grades.keys())
        return await self.spawn_owned_pet(
            character,
            species_id=resolved_species,
            grade=grade,
            acquire_tag="capture_test",
        )

    async def spawn_owned_pet(
        self,
        character: Character,
        *,
        species_id: str,
        grade: int,
        acquire_tag: str,
    ) -> dict[str, Any]:
        """
        生成一只持有灵宠（捕获/孵化等共用）。

        参数:
            character: 角色。
            species_id: 物种 id。
            grade: 个体品阶。
            acquire_tag: 途径标签（仅日志/校验参考；白名单已由调用方检查）。

        异常:
            AppError: 持有上限 / 物种缺失。
        """
        require_pets_enabled()
        cfg = get_game_config().pets
        if species_id not in cfg.species:
            raise AppError(code=40000, message=f"未知物种：{species_id}", http_status=400)
        species = cfg.species[species_id]
        count = await self.count_pets(character.id)
        ok, code = can_hold_more(count, cfg.hold_cap)
        if not ok:
            raise AppError(code=code or 40057, message="灵宠持有已达上限", http_status=400)

        resolved_grade = int(grade)
        if cfg.grades and resolved_grade not in cfg.grades:
            resolved_grade = min(cfg.grades.keys())

        affixes = self._roll_capture_affixes(resolved_grade)
        skills_cfg = get_game_config().pet_skills
        pool = skills_cfg.pools.get(species.skill_pool_id)
        if pool is not None:
            learned, equipped = default_skills_for_pool(
                pool,
                equip_slots=skills_cfg.equip_slots,
            )
        else:
            learned, equipped = [], normalize_equipped_slots([], equip_slots=skills_cfg.equip_slots)

        # PET-D03：种族天赋必带；独立被动可空
        race = cfg.races.get(species.race)
        talent_id = race.racial_talent_id if race else ""
        if not talent_id:
            raise AppError(
                code=40000,
                message=f"种族 {species.race} 缺少 racial_talent_id",
                http_status=400,
            )
        if talent_id not in get_game_config().pet_passives.passives:
            raise AppError(
                code=40000,
                message=f"种族天赋配置缺失：{talent_id}",
                http_status=400,
            )
        rolled_passives: list[str] = []
        p_pool = get_game_config().pet_passives.pools.get(species.passive_pool_id)
        if p_pool is not None:
            picked = roll_independent_passive(
                empty_weight=p_pool.empty_weight,
                weights=p_pool.weights,
            )
            if picked:
                rolled_passives.append(picked)

        pet = Pet(
            character_id=character.id,
            species_id=species_id,
            grade=resolved_grade,
            level=1,
            nickname=species.name,
            affixes_json=json.dumps(affixes, ensure_ascii=False),
            value_reroll_counts_json="{}",
            type_reroll_counts_json="{}",
            skills_learned_json=json.dumps(learned, ensure_ascii=False),
            skills_equipped_json=json.dumps(equipped, ensure_ascii=False),
            racial_talent_id=talent_id,
            passives_json=json.dumps(rolled_passives, ensure_ascii=False),
            feed_counts_json="{}",
        )
        self._session.add(pet)
        await self._session.flush()
        await self._session.refresh(pet)
        await self._mark_dex(character.id, species_id, caught=True)
        logger.info(
            "pet spawned character_id=%s pet_id=%s species=%s grade=%s via=%s "
            "affixes=%s talent=%s passives=%s",
            character.id,
            pet.id,
            species_id,
            resolved_grade,
            acquire_tag,
            len(affixes),
            talent_id,
            rolled_passives,
        )
        return {
            "id": pet.id,
            "species_id": species_id,
            "grade": resolved_grade,
            "affix_count": len(affixes),
            "pet": self._pet_to_public(pet),
        }

    async def upgrade(self, character: Character, pet_id: int) -> dict[str, Any]:
        """升级占位：level+1，材料消耗占位。"""
        require_pets_enabled()
        pet = await self._get_owned_pet(character.id, pet_id)
        cfg = get_game_config().pets
        if pet.species_id not in cfg.species:
            raise AppError(code=40000, message="物种配置缺失", http_status=400)
        pet.level = int(pet.level) + 1
        await self._session.flush()
        stats = self._stats_for_pet(pet)
        logger.info(
            "pet upgraded character_id=%s pet_id=%s level=%s",
            character.id,
            pet.id,
            pet.level,
        )
        return {"id": pet.id, "level": pet.level, "stats": stats, "pet": self._pet_to_public(pet)}

    async def grade_up(self, character: Character, pet_id: int) -> dict[str, Any]:
        """
        升阶：扣灵石 → grade+1 → 槽位+1 并随机追加 1 条词条；旧词条保留。

        异常:
            AppError: 已达上限 / 灵石不足 / 配置缺失。
        """
        require_pets_enabled()
        pet = await self._get_owned_pet(character.id, pet_id)
        pets_cfg = get_game_config().pets
        affix_cfg = get_game_config().pet_affixes
        grade_up_cfg = pets_cfg.grade_up or {}
        current = int(pet.grade)
        max_grade = int(grade_up_cfg.get("max_grade") or (max(pets_cfg.grades.keys()) if pets_cfg.grades else 7))
        if current >= max_grade:
            raise AppError(code=40058, message="灵宠品阶已达上限", http_status=400)
        target = current + 1
        if pets_cfg.grades and target not in pets_cfg.grades:
            raise AppError(code=40000, message=f"品阶表缺少 grade={target}", http_status=400)

        cost = grade_up_spirit_cost(
            base=float(grade_up_cfg.get("spirit_stones_base", 200)),
            grow=float(grade_up_cfg.get("grow", 0.25)),
            target_grade=target,
        )
        stones = int(getattr(character, "spirit_stones", 0) or 0)
        if stones < cost:
            raise AppError(
                code=40012,
                message=f"灵石不足（需要 {cost}，当前 {stones}）",
                http_status=400,
            )
        character.spirit_stones = stones - cost

        old_affixes = self._load_affixes(pet)
        # 升阶前若词条未满（旧宠迁移），先按旧品阶补齐，再追加
        old_cap = pets_cfg.grades.get(current)
        expected_old = int(old_cap.affix_slots) if old_cap else len(old_affixes)
        while len(old_affixes) < expected_old:
            old_affixes.append(
                roll_one_affix(
                    len(old_affixes),
                    types=affix_cfg.types,
                    type_weights=affix_cfg.type_weights,
                    tier_weights=affix_cfg.tier_weights,
                ),
            )
        new_affixes = append_affix_on_grade_up(
            old_affixes,
            types=affix_cfg.types,
            type_weights=affix_cfg.type_weights,
            tier_weights=affix_cfg.tier_weights,
        )
        # 对齐新品阶槽上限（设计：升阶 +1 槽）
        new_cap = pets_cfg.grades[target].affix_slots
        if len(new_affixes) > new_cap:
            new_affixes = new_affixes[:new_cap]
        elif len(new_affixes) < new_cap:
            while len(new_affixes) < new_cap:
                new_affixes.append(
                    roll_one_affix(
                        len(new_affixes),
                        types=affix_cfg.types,
                        type_weights=affix_cfg.type_weights,
                        tier_weights=affix_cfg.tier_weights,
                    ),
                )

        pet.grade = target
        self._save_affixes(pet, new_affixes)
        await self._session.flush()
        logger.info(
            "pet grade_up character_id=%s pet_id=%s grade=%s cost=%s affixes=%s",
            character.id,
            pet.id,
            target,
            cost,
            len(new_affixes),
        )
        return {
            "id": pet.id,
            "grade": target,
            "spirit_stones_spent": cost,
            "spirit_stones": int(character.spirit_stones),
            "appended_slot": len(new_affixes) - 1,
            "pet": self._pet_to_public(pet),
        }

    async def reroll_affix_value(
        self,
        character: Character,
        pet_id: int,
        *,
        slot_index: int,
    ) -> dict[str, Any]:
        """
        数值-only 洗炼：同类型同品级区间内重 roll；扣灵石并递增槽计数。

        异常:
            AppError: 槽不存在 / 灵石不足。
        """
        require_pets_enabled()
        pet = await self._get_owned_pet(character.id, pet_id)
        affix_cfg = get_game_config().pet_affixes
        affixes = self._load_affixes(pet)
        counts = self._load_value_reroll_counts(pet)
        slot_key = str(int(slot_index))
        already = int(counts.get(slot_key, 0))
        cost = value_reroll_cost(
            base=float(affix_cfg.value_reroll.get("spirit_stones_base", 50)),
            grow=float(affix_cfg.value_reroll.get("grow", 0.1)),
            times_already=already,
        )
        stones = int(getattr(character, "spirit_stones", 0) or 0)
        if stones < cost:
            raise AppError(
                code=40012,
                message=f"灵石不足（需要 {cost}，当前 {stones}）",
                http_status=400,
            )

        # 洗炼前记录类型/品级，验收「不可改类型」
        before = next((a for a in affixes if int(a.get("slot_index", -1)) == int(slot_index)), None)
        if before is None:
            raise AppError(code=40059, message=f"词条槽 {slot_index} 不存在", http_status=400)
        before_type = str(before.get("affix_type_id"))
        before_tier = str(before.get("affix_tier"))

        try:
            new_affixes = reroll_affix_value_only(
                affixes,
                int(slot_index),
                types=affix_cfg.types,
            )
        except ValueError as exc:
            raise AppError(code=40059, message=str(exc), http_status=400) from exc

        after = next(a for a in new_affixes if int(a.get("slot_index", -1)) == int(slot_index))
        if str(after.get("affix_type_id")) != before_type or str(after.get("affix_tier")) != before_tier:
            raise AppError(code=50000, message="洗炼不应改变词条类型或品级", http_status=500)

        character.spirit_stones = stones - cost
        counts[slot_key] = already + 1
        self._save_affixes(pet, new_affixes)
        self._save_value_reroll_counts(pet, counts)
        await self._session.flush()
        logger.info(
            "pet affix value reroll character_id=%s pet_id=%s slot=%s cost=%s",
            character.id,
            pet.id,
            slot_index,
            cost,
        )
        return {
            "id": pet.id,
            "slot_index": int(slot_index),
            "spirit_stones_spent": cost,
            "spirit_stones": int(character.spirit_stones),
            "affix": self._affix_public_list([after])[0],
            "value_reroll_count": counts[slot_key],
            "pet": self._pet_to_public(pet),
        }

    async def type_reroll_status(self, character: Character, pet_id: int) -> dict[str, Any]:
        """
        灵兽宗：各槽改类型次数与下次报价。

        Returns:
            pet_id / enabled / type_reroll_slots / slots 列表。
        """
        require_pets_enabled()
        pet = await self._get_owned_pet(character.id, pet_id)
        type_slots = self._type_reroll_slots_for_grade(int(pet.grade))
        counts = self._load_type_reroll_counts(pet)
        affixes = self._load_affixes(pet)
        slots_out: list[dict[str, Any]] = []
        for item in affixes:
            slot_index = int(item.get("slot_index", 0))
            slots_out.append(
                self._next_type_reroll_preview(
                    counts,
                    slot_index,
                    type_reroll_slots=type_slots,
                ),
            )
        return {
            "pet_id": pet.id,
            "enabled": spirit_beast_sect_enabled(),
            "type_reroll_slots": type_slots,
            "slots": slots_out,
            "fee_formula": {
                "base_1": (get_game_config().pets.sect_reroll or {}).get("base_1", 100),
                "grow": (get_game_config().pets.sect_reroll or {}).get("grow", 0.1),
                "description": "cost_i,k = base_1 * i * (1+grow)^(k-1)",
            },
        }

    async def type_reroll_preview_quote(
        self,
        character: Character,
        *,
        pet_id: int | None = None,
        slot_index: int | None = None,
    ) -> dict[str, Any]:
        """
        灵兽宗改类型预览：费用公式 + 可选单槽报价。

        Args:
            character: 当前角色。
            pet_id: 可选；与 slot_index 同时给出时返回 quote。
            slot_index: 可选词条槽。
        """
        require_pets_enabled()
        cfg = get_game_config()
        facility = cfg.sects.facilities.get("spirit_beast_sect") or {}
        enabled = bool(facility.get("enabled"))
        sect_reroll = cfg.pets.sect_reroll or {}
        payload: dict[str, Any] = {
            "enabled": enabled,
            "facility_id": "spirit_beast_sect",
            "note": str(facility.get("note") or sect_reroll.get("note", "")),
            "fee_formula": {
                "base_1": sect_reroll.get("base_1", 100),
                "grow": sect_reroll.get("grow", 0.1),
                "description": "cost_i,k = base_1 * i * (1+grow)^(k-1)",
            },
            "quote": None,
        }
        if pet_id is not None and slot_index is not None:
            pet = await self._get_owned_pet(character.id, int(pet_id))
            type_slots = self._type_reroll_slots_for_grade(int(pet.grade))
            counts = self._load_type_reroll_counts(pet)
            preview = self._next_type_reroll_preview(
                counts,
                int(slot_index),
                type_reroll_slots=type_slots,
            )
            payload["quote"] = {
                "pet_id": pet.id,
                "spirit_stones": preview["next_cost_spirit_stones"],
                **preview,
            }
        return payload

    async def reroll_affix_type(
        self,
        character: Character,
        pet_id: int,
        *,
        slot_index: int,
    ) -> dict[str, Any]:
        """
        灵兽宗改词条类型：扣灵石 → 重 roll 该槽类型/品级/数值；分槽独立计数。

        Raises:
            AppError: 设施未开 / 槽不可改 / 灵石不足 / 槽不存在。
        """
        require_pets_enabled()
        if not spirit_beast_sect_enabled():
            raise AppError(
                code=50110,
                message="灵兽宗设施未开放（后台 sects.facilities.spirit_beast_sect）",
                http_status=501,
            )
        pet = await self._get_owned_pet(character.id, pet_id)
        type_slots = self._type_reroll_slots_for_grade(int(pet.grade))
        if int(slot_index) < 0 or int(slot_index) >= type_slots:
            raise AppError(
                code=40061,
                message=f"槽 {slot_index} 不可改类型（本宠可改槽 0～{type_slots - 1}）",
                http_status=400,
            )

        affix_cfg = get_game_config().pet_affixes
        sect = get_game_config().pets.sect_reroll or {}
        affixes = self._load_affixes(pet)
        before = next((a for a in affixes if int(a.get("slot_index", -1)) == int(slot_index)), None)
        if before is None:
            raise AppError(code=40059, message=f"词条槽 {slot_index} 不存在", http_status=400)

        counts = self._load_type_reroll_counts(pet)
        slot_key = str(int(slot_index))
        already = int(counts.get(slot_key, 0))
        cost = type_reroll_cost(
            base_1=float(sect.get("base_1", 100)),
            grow=float(sect.get("grow", 0.1)),
            slot_ordinal_1based=int(slot_index) + 1,
            times_already=already,
        )
        stones = int(getattr(character, "spirit_stones", 0) or 0)
        if stones < cost:
            raise AppError(
                code=40012,
                message=f"灵石不足（需要 {cost}，当前 {stones}）",
                http_status=400,
            )

        try:
            new_affixes = reroll_affix_type(
                affixes,
                int(slot_index),
                types=affix_cfg.types,
                type_weights=affix_cfg.type_weights,
                tier_weights=affix_cfg.tier_weights,
            )
        except ValueError as exc:
            raise AppError(code=40059, message=str(exc), http_status=400) from exc

        after = next(a for a in new_affixes if int(a.get("slot_index", -1)) == int(slot_index))
        character.spirit_stones = stones - cost
        counts[slot_key] = already + 1
        self._save_affixes(pet, new_affixes)
        self._save_type_reroll_counts(pet, counts)
        await self._session.flush()
        logger.info(
            "pet affix type reroll character_id=%s pet_id=%s slot=%s cost=%s type=%s→%s",
            character.id,
            pet.id,
            slot_index,
            cost,
            before.get("affix_type_id"),
            after.get("affix_type_id"),
        )
        return {
            "id": pet.id,
            "slot_index": int(slot_index),
            "spirit_stones_spent": cost,
            "spirit_stones": int(character.spirit_stones),
            "affix": self._affix_public_list([after])[0],
            "type_reroll_count": counts[slot_key],
            "pet": self._pet_to_public(pet),
        }

    async def feed(
        self,
        character: Character,
        pet_id: int,
        *,
        item_id: str,
        quantity: int = 1,
    ) -> dict[str, Any]:
        """
        丹药喂养：扣背包兽丹 → 累加次数 → 永久叠面板（PET-D04）。

        Raises:
            AppError: 未知丹 / 超上限 / 背包不足。
        """
        require_pets_enabled()
        pet = await self._get_owned_pet(character.id, pet_id)
        feed_cfg = get_game_config().pet_feed
        iid = (item_id or "").strip()
        item = feed_cfg.items.get(iid)
        qty = int(quantity)
        counts = self._load_feed_counts(pet)
        total_cap = self._feed_total_cap(pet)
        try:
            validate_feed_batch(
                item_id=iid,
                quantity=qty,
                counts=counts,
                item_cfg=item,
                total_cap=total_cap,
            )
        except ValueError as exc:
            raise AppError(code=40066, message=str(exc), http_status=400) from exc

        from app.services.inventory_service import InventoryService

        inv = InventoryService(self._session)
        owned = await inv.material_counts(character.id)
        if int(owned.get(iid, 0)) < qty:
            raise AppError(
                code=40055,
                message=f"背包兽丹不足（需要 {qty}，当前 {owned.get(iid, 0)}）",
                http_status=400,
            )
        await inv._remove_item_id(character.id, iid, qty)
        counts[iid] = int(counts.get(iid, 0)) + qty
        self._save_feed_counts(pet, counts)
        await self._session.flush()
        logger.info(
            "pet feed character_id=%s pet_id=%s item=%s qty=%s total=%s",
            character.id,
            pet.id,
            iid,
            qty,
            total_feed_used(counts),
        )
        return {
            "id": pet.id,
            "item_id": iid,
            "quantity": qty,
            "times_fed": counts[iid],
            "total_used": total_feed_used(counts),
            "total_cap": total_cap,
            "pet": self._pet_to_public(pet),
        }

    async def equip_skills(
        self,
        character: Character,
        pet_id: int,
        *,
        equipped: list[str | None],
    ) -> dict[str, Any]:
        """
        装备技能栏（最多 4）；须已学；禁重复与互斥。

        异常:
            AppError: 40060 装备非法。
        """
        require_pets_enabled()
        pet = await self._get_owned_pet(character.id, pet_id)
        skills_cfg = get_game_config().pet_skills
        learned = self._load_skills_learned(pet)
        try:
            slots = validate_equip_loadout(
                equipped,
                learned=learned,
                skills=skills_cfg.skills,
                equip_slots=skills_cfg.equip_slots,
            )
        except ValueError as exc:
            raise AppError(code=40060, message=str(exc), http_status=400) from exc
        self._save_skills(pet, learned=learned, equipped=slots)
        await self._session.flush()
        logger.info(
            "pet skills equipped character_id=%s pet_id=%s slots=%s",
            character.id,
            pet.id,
            slots,
        )
        return {"id": pet.id, "equipped_ids": slots, "pet": self._pet_to_public(pet)}

    async def learn_skill_from_pool(
        self,
        character: Character,
        pet_id: int,
        *,
        skill_id: str,
    ) -> dict[str, Any]:
        """
        从物种技能池领悟技能（PET-D02 占位：无等级门槛）。

        异常:
            AppError: 40061 不在池内 / 已学会。
        """
        require_pets_enabled()
        pet = await self._get_owned_pet(character.id, pet_id)
        pets_cfg = get_game_config().pets
        skills_cfg = get_game_config().pet_skills
        species = pets_cfg.species.get(pet.species_id)
        if species is None:
            raise AppError(code=40000, message="物种配置缺失", http_status=400)
        pool = skills_cfg.pools.get(species.skill_pool_id)
        if pool is None:
            raise AppError(code=40061, message="物种无技能池", http_status=400)
        sid = skill_id.strip()
        if not can_learn_from_pool(sid, pool.skill_ids):
            raise AppError(code=40061, message=f"技能不在物种池：{sid}", http_status=400)
        if sid not in skills_cfg.skills:
            raise AppError(code=40061, message=f"未知技能：{sid}", http_status=400)
        learned = self._load_skills_learned(pet)
        if sid in learned:
            raise AppError(code=40061, message="已学会该技能", http_status=400)
        learned.append(sid)
        equipped = self._load_skills_equipped(pet)
        self._save_skills(pet, learned=learned, equipped=equipped)
        await self._session.flush()
        return {
            "id": pet.id,
            "learned_skill_id": sid,
            "pet": self._pet_to_public(pet),
        }

    async def learn_skill_from_book(
        self,
        character: Character,
        pet_id: int,
        *,
        book_id: str,
    ) -> dict[str, Any]:
        """
        消耗技能书学会技能；校验 scope 与背包数量。

        异常:
            AppError: 40055 无书；40062 scope 不符；40061 已学。
        """
        require_pets_enabled()
        pet = await self._get_owned_pet(character.id, pet_id)
        books_cfg = get_game_config().pet_skill_books
        skills_cfg = get_game_config().pet_skills
        pets_cfg = get_game_config().pets
        bid = book_id.strip()
        book = books_cfg.books.get(bid)
        if book is None:
            raise AppError(code=40000, message=f"未知技能书：{bid}", http_status=400)
        species = pets_cfg.species.get(pet.species_id)
        if species is None:
            raise AppError(code=40000, message="物种配置缺失", http_status=400)
        if not book_eligible_for_pet(
            book,
            race_id=species.race,
            species_id=species.species_id,
        ):
            raise AppError(
                code=40062,
                message=f"该宠不符合技能书范围（scope={book.scope}）",
                http_status=400,
            )
        skill_id = book.skill_id
        if skill_id not in skills_cfg.skills:
            raise AppError(code=40061, message=f"技能书指向未知技能：{skill_id}", http_status=400)
        learned = self._load_skills_learned(pet)
        if skill_id in learned:
            raise AppError(code=40061, message="已学会该技能", http_status=400)

        from app.services.inventory_service import InventoryService

        inv = InventoryService(self._session)
        counts = await inv.material_counts(character.id)
        if counts.get(bid, 0) < 1:
            raise AppError(code=40055, message=f"技能书不足：{bid}", http_status=400)
        await inv._remove_item_id(character.id, bid, 1)

        learned.append(skill_id)
        equipped = self._load_skills_equipped(pet)
        self._save_skills(pet, learned=learned, equipped=equipped)
        await self._session.flush()
        logger.info(
            "pet learned from book character_id=%s pet_id=%s book=%s skill=%s",
            character.id,
            pet.id,
            bid,
            skill_id,
        )
        return {
            "id": pet.id,
            "book_id": bid,
            "learned_skill_id": skill_id,
            "pet": self._pet_to_public(pet),
        }

    async def patch_pet(
        self,
        character: Character,
        pet_id: int,
        *,
        nickname: str | None = None,
        is_deploy_preferred: bool | None = None,
    ) -> dict[str, Any]:
        """更新昵称或布阵偏好。"""
        require_pets_enabled()
        pet = await self._get_owned_pet(character.id, pet_id)
        if nickname is not None:
            pet.nickname = nickname.strip() or None
        if is_deploy_preferred is not None:
            pet.is_deploy_preferred = is_deploy_preferred
        await self._session.flush()
        return {
            "id": pet.id,
            "nickname": pet.nickname,
            "is_deploy_preferred": pet.is_deploy_preferred,
        }

    async def _get_owned_pet(self, character_id: int, pet_id: int) -> Pet:
        """按 id 取所属灵宠。"""
        result = await self._session.execute(
            select(Pet)
            .where(Pet.id == pet_id, Pet.character_id == character_id)
            .limit(1),
        )
        pet = result.scalar_one_or_none()
        if pet is None:
            raise AppError(
                code=40057,
                message="灵宠不存在或不属于当前角色",
                http_status=404,
            )
        return pet

    async def get_pet_stats(self, pet_id: int, character_id: int) -> dict[str, int]:
        """为布阵/战斗组装灵宠面板。"""
        pet = await self._get_owned_pet(character_id, pet_id)
        return self._stats_for_pet(pet)
