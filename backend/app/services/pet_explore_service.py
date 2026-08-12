"""
M4-D04c 野外探索：遭遇（区×时×天）→ 捕获检定（骰可审计）→ wild_capture 入园。
"""

from __future__ import annotations

import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.character import Character
from app.domain.pet_capture_rules import (
    beast_realm_index,
    compute_capture_probability,
    estimate_special_affix_count,
    player_realm_index,
    realm_diff_bonus,
)
from app.domain.pet_encounter_rules import (
    pick_encounter_entry,
    pick_encounter_table,
    pick_grade_from_weights,
)
from app.domain.pet_rules import can_hold_more
from app.schemas.common import AppError
from app.services.calendar_service import CalendarService
from app.services.dice_service import DiceService
from app.services.inventory_service import InventoryService
from app.services.m4_features import require_pets_enabled
from app.services.pet_service import PetService
from app.services.realm_config import get_game_config
from app.services.weather_service import WeatherService

logger = logging.getLogger(__name__)


@dataclass
class _EncounterSession:
    """内存遭遇会话（战后可捕占位）。"""

    character_id: int
    encounter_id: str
    region_id: str
    shichen: str
    weather: str
    encounter_type: str
    species_id: str
    grade: int
    special_affix_count: int
    label: str
    capturable: bool
    battle_resolved: bool
    seed: int
    created_at: float = field(default_factory=time.time)


class PetExploreSessionStore:
    """进程内遭遇会话。"""

    _lock = threading.Lock()
    _sessions: dict[str, _EncounterSession] = {}
    # character_id → (YYYY-MM-DD, attempts)
    _daily: dict[int, tuple[str, int]] = {}

    @classmethod
    def put(cls, session: _EncounterSession) -> None:
        """写入遭遇。"""
        with cls._lock:
            cls._sessions[session.encounter_id] = session

    @classmethod
    def get(cls, encounter_id: str) -> _EncounterSession | None:
        """读取遭遇。"""
        with cls._lock:
            return cls._sessions.get(encounter_id)

    @classmethod
    def remove(cls, encounter_id: str) -> None:
        """删除遭遇。"""
        with cls._lock:
            cls._sessions.pop(encounter_id, None)

    @classmethod
    def consume_daily(cls, character_id: int, *, cap: int) -> int:
        """
        消耗一次日额度；返回消耗后次数。

        Raises:
            AppError: 超日上限 40084。
        """
        if cap <= 0:
            return 0
        today = date.today().isoformat()
        with cls._lock:
            day, used = cls._daily.get(character_id, (today, 0))
            if day != today:
                used = 0
                day = today
            if used >= cap:
                raise AppError(
                    code=40084,
                    message=f"今日捕获尝试已达上限（{cap}）",
                    http_status=400,
                )
            used += 1
            cls._daily[character_id] = (day, used)
            return used

    @classmethod
    def clear_all(cls) -> None:
        """测试用清空。"""
        with cls._lock:
            cls._sessions.clear()
            cls._daily.clear()


class PetExploreService:
    """
    野外遭遇与捕获。

    属性:
        _session: DB 会话。
        _pets: PetService。
        _inventory: InventoryService。
    """

    def __init__(self, session: AsyncSession) -> None:
        """绑定请求级会话。"""
        self._session = session
        self._pets = PetService(session)
        self._inventory = InventoryService(session)

    def _resolve_env(self, region_id: str) -> tuple[str, str, str, str, str, str]:
        """
        解析 region / 时辰 / 天气及其中文名。

        Returns:
            tuple: region_id, region_label, shichen, shichen_label, weather, weather_label.
        """
        from app.domain.display_labels import label_zh_or_unknown

        bundle = get_game_config()
        map_cfg = bundle.map
        rid = (region_id or "default").strip() or "default"
        if rid not in map_cfg.regions:
            raise AppError(
                code=40081,
                message=f"未知区域：{rid}",
                http_status=400,
            )
        region_meta = map_cfg.regions[rid] or {}
        region_label = str(region_meta.get("name") or label_zh_or_unknown(rid))
        weather_region = str(region_meta.get("weather_region") or rid)
        cal = CalendarService().get_snapshot()
        weather = WeatherService().get_snapshot(region_id=weather_region)
        shichen = str(cal["shichen_id"])
        weather_id = str(weather["weather_id"])
        return (
            rid,
            region_label,
            shichen,
            str(cal.get("label") or label_zh_or_unknown(shichen, bundle.calendar.labels)),
            weather_id,
            str(
                weather.get("label")
                or label_zh_or_unknown(weather_id, bundle.weather.labels),
            ),
        )

    def _public_encounter(self, enc: _EncounterSession) -> dict[str, Any]:
        """遭遇公共字段（含中文名，禁止裸英文 id 上屏）。"""
        from app.domain.display_labels import label_zh_or_unknown

        bundle = get_game_config()
        region_meta = (bundle.map.regions.get(enc.region_id) or {})
        species_name = None
        if enc.species_id and enc.species_id in bundle.pets.species:
            species_name = bundle.pets.species[enc.species_id].name
        return {
            "encounter_id": enc.encounter_id,
            "region_id": enc.region_id,
            "region_label": str(region_meta.get("name") or label_zh_or_unknown(enc.region_id)),
            "shichen": enc.shichen,
            "shichen_label": label_zh_or_unknown(enc.shichen, bundle.calendar.labels),
            "weather": enc.weather,
            "weather_label": label_zh_or_unknown(enc.weather, bundle.weather.labels),
            "type": enc.encounter_type,
            "species_id": enc.species_id or None,
            "species_name": species_name,
            "grade": enc.grade if enc.species_id else None,
            "special_affix_count": enc.special_affix_count,
            "label": enc.label,
            "capturable": enc.capturable,
            "battle_resolved": enc.battle_resolved,
            "seed": enc.seed,
        }

    async def preview(
        self,
        character: Character,
        *,
        region_id: str = "default",
    ) -> dict[str, Any]:
        """当前区×时×天遭遇池预览（不扣费、不建会话）。"""
        require_pets_enabled()
        rid, region_label, shichen, shichen_label, weather, weather_label = (
            self._resolve_env(region_id)
        )
        enc_cfg = get_game_config().pet_encounter
        table = pick_encounter_table(
            enc_cfg.tables,
            region_id=rid,
            shichen=shichen,
            weather=weather,
        )
        entries_out: list[dict[str, Any]] = []
        if table is not None:
            pets_cfg = get_game_config().pets
            for e in table.get("entries") or []:
                sid = e.get("species_id") or None
                sname = None
                if sid and sid in pets_cfg.species:
                    sname = pets_cfg.species[str(sid)].name
                entries_out.append(
                    {
                        "type": e.get("type"),
                        "species_id": sid,
                        "species_name": sname,
                        "weight": int(e.get("weight") or 0),
                        "label": e.get("label") or sname or "",
                        "capturable": str(e.get("type") or "")
                        in enc_cfg.capturable_types,
                    },
                )
        bag_ok, lure_count = await self._bag_and_lure(character)
        cap_cfg = get_game_config().pet_capture
        return {
            "region_id": rid,
            "region_label": region_label,
            "shichen": shichen,
            "shichen_label": shichen_label,
            "weather": weather,
            "weather_label": weather_label,
            "skip_battle": enc_cfg.skip_battle,
            "entries": entries_out,
            "require_bag": cap_cfg.require_bag,
            "bag_ok": bag_ok,
            "lure_item_id": cap_cfg.lure_item_id,
            "lure_count": lure_count,
            "daily_attempt_cap": cap_cfg.daily_attempt_cap,
            "auto_capture_enabled": cap_cfg.auto_capture_enabled,
        }

    async def _bag_and_lure(self, character: Character) -> tuple[bool, int]:
        """是否持有灵兽袋、诱灵草数量。"""
        cap_cfg = get_game_config().pet_capture
        counts = await self._inventory.material_counts(character.id)
        lure = int(counts.get(cap_cfg.lure_item_id, 0))
        if not cap_cfg.require_bag:
            return True, lure
        bag_ok = int(counts.get(cap_cfg.bag_item_id, 0)) >= 1
        return bag_ok, lure

    async def encounter(
        self,
        character: Character,
        *,
        region_id: str = "default",
        seed: int | None = None,
    ) -> dict[str, Any]:
        """
        掷一次遭遇；可捕类型标 seen；建内存会话。

        Raises:
            AppError: 40080/40081。
        """
        require_pets_enabled()
        rid, _region_label, shichen, _shichen_label, weather, _weather_label = (
            self._resolve_env(region_id)
        )
        enc_cfg = get_game_config().pet_encounter
        table = pick_encounter_table(
            enc_cfg.tables,
            region_id=rid,
            shichen=shichen,
            weather=weather,
        )
        if table is None or not (table.get("entries") or []):
            raise AppError(
                code=40080,
                message="当前区域无遭遇表",
                http_status=400,
            )
        resolved_seed = int(seed) if seed is not None else secrets.randbelow(2**31 - 1)
        rng = DiceService.make_rng(resolved_seed)
        entry = pick_encounter_entry(list(table["entries"]), rng=rng)
        if entry is None:
            raise AppError(code=40080, message="遭遇池为空", http_status=400)

        etype = str(entry.get("type") or "monster")
        species_id = str(entry.get("species_id") or "").strip()
        capturable = etype in enc_cfg.capturable_types and bool(species_id)
        grade = 1
        special_n = 0
        label = str(entry.get("label") or "")
        pets_cfg = get_game_config().pets
        if capturable:
            if species_id not in pets_cfg.species:
                raise AppError(
                    code=40080,
                    message=f"遭遇物种未知：{species_id}",
                    http_status=400,
                )
            sp = pets_cfg.species[species_id]
            if "wild_capture" not in sp.acquire_tags:
                raise AppError(
                    code=40085,
                    message=f"物种「{sp.name}」不允许野外捕获",
                    http_status=400,
                )
            grade = pick_grade_from_weights(
                entry.get("grade_weights") or pets_cfg.capture_test_grade_weights,
                rng=rng,
            )
            label = label or sp.name
            await self._pets._mark_dex(character.id, species_id, caught=False)
            cap_cfg = get_game_config().pet_capture
            if cap_cfg.estimate_special_affixes:
                grade_cfg = pets_cfg.grades.get(grade)
                slots = int(grade_cfg.affix_slots) if grade_cfg else 3
                special_n = estimate_special_affix_count(
                    slots=slots,
                    tier_weights=get_game_config().pet_affixes.tier_weights,
                    min_tier=cap_cfg.special_affix_min_tier,
                    rng=rng,
                )
        else:
            label = label or "不可捕获遭遇"

        eid = secrets.token_hex(8)
        enc = _EncounterSession(
            character_id=character.id,
            encounter_id=eid,
            region_id=rid,
            shichen=shichen,
            weather=weather,
            encounter_type=etype,
            species_id=species_id if capturable else "",
            grade=grade if capturable else 0,
            special_affix_count=special_n,
            label=label,
            capturable=capturable,
            battle_resolved=bool(enc_cfg.skip_battle),
            seed=resolved_seed,
        )
        PetExploreSessionStore.put(enc)
        logger.info(
            "pet encounter character_id=%s id=%s type=%s species=%s grade=%s "
            "region=%s shichen=%s weather=%s",
            character.id,
            eid,
            etype,
            species_id,
            grade,
            rid,
            shichen,
            weather,
        )
        return self._public_encounter(enc)

    def _capture_factors(
        self,
        character: Character,
        *,
        species_id: str,
        grade: int,
        special_affix_count: int,
    ) -> tuple[float, dict[str, float]]:
        """组装捕获成功率与分项。"""
        pets_cfg = get_game_config().pets
        cap_cfg = get_game_config().pet_capture
        species = pets_cfg.species[species_id]
        race = pets_cfg.races.get(species.race)
        p_race = float(
            cap_cfg.species_capture_override.get(species_id)
            or (race.base_capture_rate if race else 0.3),
        )
        # 御兽功法：首版读配置表，角色功法未接入则 0
        p_taming = 0.0
        for _tid, bonus in cap_cfg.taming_tech_bonus.items():
            # 预留：持有功法则加；当前空表
            p_taming += float(bonus) * 0.0

        major_order = list(get_game_config().realms.keys())
        p_idx = player_realm_index(
            major_order=major_order,
            major_realm=str(character.major_realm),
            realm_stage=int(character.realm_stage),
        )
        b_idx = beast_realm_index(
            grade=grade,
            stages_per_grade=cap_cfg.realm_diff_beast_stages_per_grade,
        )
        p_realm = realm_diff_bonus(
            player_index=p_idx,
            beast_index=b_idx,
            per_stage=cap_cfg.realm_diff_per_stage,
            clamp_min=cap_cfg.realm_diff_clamp_min,
            clamp_max=cap_cfg.realm_diff_clamp_max,
        )

        p_root = 0.0
        try:
            tags = json.loads(character.spirit_root_tags_json or "[]")
            if isinstance(tags, list):
                for tag in tags:
                    race_map = cap_cfg.root_affinity.get(str(tag)) or {}
                    p_root += float(race_map.get(species.race, 0.0))
        except (TypeError, ValueError, json.JSONDecodeError):
            p_root = 0.0

        pen_g = float(cap_cfg.pen_grade.get(int(grade), 0.0))
        return compute_capture_probability(
            p_race=p_race,
            p_taming_tech=p_taming,
            p_realm_diff=p_realm,
            p_root_affinity=p_root,
            n_special_affix=special_affix_count,
            pen_affix=cap_cfg.pen_affix,
            pen_grade=pen_g,
        )

    async def capture(
        self,
        character: Character,
        *,
        encounter_id: str,
        seed: int | None = None,
    ) -> dict[str, Any]:
        """
        对可捕遭遇发起捕获：扣诱灵草 → 全因子骰 → 成功 wild_capture 入园。

        Raises:
            AppError: 40055/40057/40080～40085。
        """
        require_pets_enabled()
        enc = PetExploreSessionStore.get(encounter_id)
        if enc is None or enc.character_id != character.id:
            raise AppError(code=40080, message="遭遇已失效", http_status=400)
        if not enc.capturable or not enc.species_id:
            raise AppError(code=40080, message="该遭遇不可捕获", http_status=400)
        if not enc.battle_resolved:
            raise AppError(
                code=40080,
                message="须先完成战斗方可捕获",
                http_status=400,
            )

        pets_cfg = get_game_config().pets
        sp = pets_cfg.species[enc.species_id]
        if "wild_capture" not in sp.acquire_tags:
            raise AppError(
                code=40085,
                message=f"物种「{sp.name}」不允许野外捕获",
                http_status=400,
            )

        cap_cfg = get_game_config().pet_capture
        bag_ok, lure_count = await self._bag_and_lure(character)
        if not bag_ok:
            raise AppError(
                code=40083,
                message="需要灵兽袋方可捕获",
                http_status=400,
            )
        if lure_count < 1:
            raise AppError(
                code=40082,
                message="诱灵草不足",
                http_status=400,
            )

        count = await self._pets.count_pets(character.id)
        ok, code = can_hold_more(count, pets_cfg.hold_cap)
        if not ok:
            raise AppError(code=code or 40057, message="灵宠持有已达上限", http_status=400)

        PetExploreSessionStore.consume_daily(
            character.id,
            cap=cap_cfg.daily_attempt_cap,
        )

        await self._inventory._remove_item_id(
            character.id,
            cap_cfg.lure_item_id,
            1,
        )

        p, factors = self._capture_factors(
            character,
            species_id=enc.species_id,
            grade=enc.grade,
            special_affix_count=enc.special_affix_count,
        )
        # 捕获骰独立 seed（可指定）；与遭遇 seed 分离便于审计
        # 显式 roll 对齐 DiceService.chance：success = random() < p
        roll_seed = int(seed) if seed is not None else secrets.randbelow(2**31 - 1)
        rng = DiceService.make_rng(roll_seed)
        roll_value = float(rng.random())
        success = roll_value < p

        result: dict[str, Any] = {
            "success": success,
            "p": p,
            "factors": factors,
            "roll": roll_value,
            "seed": roll_seed,
            "encounter": self._public_encounter(enc),
            "consumed": {cap_cfg.lure_item_id: 1},
            "acquire_tag": "wild_capture",
            "pet": None,
        }
        if success:
            spawned = await self._pets.spawn_owned_pet(
                character,
                species_id=enc.species_id,
                grade=enc.grade,
                acquire_tag="wild_capture",
            )
            result["pet"] = spawned.get("pet")
            result["id"] = spawned.get("id")
            PetExploreSessionStore.remove(encounter_id)
            logger.info(
                "wild_capture success character_id=%s pet_id=%s species=%s p=%s roll=%s",
                character.id,
                spawned.get("id"),
                enc.species_id,
                p,
                roll_value,
            )
        else:
            logger.info(
                "wild_capture fail character_id=%s species=%s p=%s roll=%s",
                character.id,
                enc.species_id,
                p,
                roll_value,
            )
        return result

    async def auto_capture(
        self,
        character: Character,
        *,
        region_id: str = "default",
        seed: int | None = None,
    ) -> dict[str, Any]:
        """
        批量探索自动捕：最多 max_rolls 次遭遇，遇可捕且有草/袋则尝试一次后返回。

        Raises:
            AppError: 未开放 / 环境错误。
        """
        require_pets_enabled()
        cap_cfg = get_game_config().pet_capture
        if not cap_cfg.auto_capture_enabled:
            raise AppError(code=40080, message="自动捕未开放", http_status=400)

        base_seed = int(seed) if seed is not None else secrets.randbelow(2**31 - 1)
        rolls: list[dict[str, Any]] = []
        capture_result: dict[str, Any] | None = None
        max_rolls = max(1, int(cap_cfg.auto_capture_max_rolls))

        for i in range(max_rolls):
            enc = await self.encounter(
                character,
                region_id=region_id,
                seed=base_seed + i * 97,
            )
            rolls.append(enc)
            if not enc.get("capturable"):
                continue
            bag_ok, lure = await self._bag_and_lure(character)
            if not bag_ok or lure < 1:
                break
            capture_result = await self.capture(
                character,
                encounter_id=str(enc["encounter_id"]),
                seed=base_seed + i * 97 + 1,
            )
            break

        return {
            "rolls": rolls,
            "capture": capture_result,
            "seed": base_seed,
            "auto": True,
        }
