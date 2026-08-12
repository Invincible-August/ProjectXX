"""
防守快照应用服务（M3战斗成型设计.md §6 · S6）。

- 手动更新：1 小时冷却；渡劫等禁止态 → ``40046``；
- 每日定点：请求路径 **惰性补刷**（槽位标记幂等，不引入 APScheduler，见 M3-D01）；
- 快照内容：冻结战力 / 棋子 / 布阵 / 阵法 / 哈希；不含挂机瞬时进度。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time_utils import now_utc, to_utc_iso
from app.db.models.character import Character
from app.db.models.defense_snapshot import DefenseSnapshot
from app.domain.snapshot_hash import compute_content_hash
from app.schemas.common import AppError
from app.services.avatar_service import AvatarService
from app.services.character_service import CharacterService
from app.services.divine_sense_service import DivineSenseService
from app.services.formation_service import FormationService
from app.services.pet_service import PetService
from app.services.realm_config import (
    build_realm_display,
    get_game_config,
)

logger = logging.getLogger(__name__)

# 禁止更新快照 / 开战的角色状态（渡劫等 M5 状态提前占位）
_SNAPSHOT_FORBIDDEN_STATUSES = {"tribulation", "awaiting_ferry", "reincarnating"}


class SnapshotService:
    """
    防守快照用例：构建 / 手动更新 / 惰性定点补刷 / 预览。

    属性:
        _session: 请求级异步会话。
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        参数:
            session: SQLAlchemy 异步会话。
        """
        self._session = session
        self._characters = CharacterService(session)
        self._formations = FormationService(session)

    # ------------------------------------------------------------------
    # 构建
    # ------------------------------------------------------------------

    async def build_payload(self, character: Character) -> dict[str, Any]:
        """
        用「防守预设 + 实时属性」构建快照 payload（设计 §6.1）。

        本体 atk/hp 取 ``build_combat_stats`` 权威值并冻结；
        试炼木傀按 board.yaml 比例推导。
        """
        board = get_game_config().board
        snapshots_cfg = get_game_config().snapshots
        preset = await self._formations.get_defense_preset(character)
        main_atk, main_hp, _, _ = await self._characters.build_combat_stats(character)
        from app.services.avatar_repo import fetch_avatar_row

        pet_svc = PetService(self._session)
        avatar_row = await fetch_avatar_row(self._session, character.id)

        units: list[dict[str, Any]] = []
        preset_units = json.loads(preset.units_json or "[]")
        for unit in preset_units:
            kind = str(unit.get("unit_kind", "main"))
            defaults = board.unit_defaults.get(kind) or board.unit_defaults["main"]
            ref_id = unit.get("ref_id")
            if kind == "main":
                atk, hp, name = main_atk, main_hp, character.name
            elif kind == "avatar" and avatar_row is not None:
                stats = AvatarService.avatar_combat_stats(avatar_row)
                atk, hp, name = stats["atk"], stats["hp"], avatar_row.name
                ref_id = avatar_row.id
            elif kind == "pet" and ref_id is not None:
                stats = await pet_svc.get_pet_stats(int(ref_id), character.id)
                atk, hp = stats["atk"], stats["hp"]
                name = f"pet_{ref_id}"
            elif kind == "puppet":
                atk = max(1, int(main_atk * defaults.atk_ratio))
                hp = max(1, int(main_hp * defaults.hp_ratio))
                name = "试炼木傀" if str(unit.get("unit_uid", "")).startswith("puppet_") else "傀儡"
            else:
                atk = max(1, int(main_atk * defaults.atk_ratio))
                hp = max(1, int(main_hp * defaults.hp_ratio))
                name = kind
            speed = defaults.speed
            if kind == "pet" and ref_id is not None:
                speed = (await pet_svc.get_pet_stats(int(ref_id), character.id))["speed"]
            entry: dict[str, Any] = {
                "unit_uid": str(unit["unit_uid"]),
                "unit_kind": kind,
                "x": int(unit["x"]),
                "y": int(unit["y"]),
                "atk": atk,
                "hp": hp,
                "speed": speed,
                "attack_range": defaults.attack_range,
                "attack_kind": defaults.attack_kind,
                "can_fly": defaults.can_fly,
                "name": name,
            }
            if ref_id is not None:
                entry["ref_id"] = ref_id
            units.append(entry)

        av_count, _pet_count, pet_costs = DivineSenseService.count_deployed_from_units(
            preset_units,
        )
        # 物种 divine_sense_cost 覆盖（按 ref_id 查 species）
        from app.db.models.pet import Pet

        pets_cfg = get_game_config().pets
        ds_cfg = get_game_config().divine_sense
        enriched_costs: list[int] = []
        for unit in preset_units:
            if str(unit.get("unit_kind")) != "pet":
                continue
            cost = ds_cfg.cost_pet
            ref_id = unit.get("ref_id")
            if ref_id is not None:
                row = await self._session.execute(
                    select(Pet).where(
                        Pet.id == int(ref_id),
                        Pet.character_id == character.id,
                    ),
                )
                pet_row = row.scalar_one_or_none()
                if pet_row is not None:
                    sp = pets_cfg.species.get(pet_row.species_id)
                    if sp is not None and sp.divine_sense_cost is not None:
                        cost = int(sp.divine_sense_cost)
            enriched_costs.append(cost)

        sense = DivineSenseService.snapshot_for_character(
            character,
            avatar_deploy_count=av_count,
            pet_deploy_count=len(enriched_costs),
            pet_costs=enriched_costs or None,
        )
        if sense["load"] > sense["soft_cap"]:
            mult = sense["overload_mult"]
            for idx, u in enumerate(units):
                units[idx]["atk"] = max(1, int(u["atk"] * mult))
                units[idx]["hp"] = max(1, int(u["hp"] * mult))
        if sense["load"] > sense["hard_cap"]:
            character.divine_sense_backlash = True
            logger.info(
                "snapshot divine backlash set character_id=%s tier=%s",
                character.id,
                sense.get("backlash_tier"),
            )

        payload: dict[str, Any] = {
            "schema_version": snapshots_cfg.schema_version,
            "character_id": character.id,
            "dao_name": character.name,
            "realm": {
                "major": character.major_realm,
                "stage": character.realm_stage,
                "label": build_realm_display(
                    character.major_realm,
                    character.realm_stage_label,
                ),
            },
            "breakthrough_grade": character.breakthrough_grade,
            "formation_id": preset.formation_id,
            "units": units,
            "divine_sense_load": sense["load"],
            "array_craft_level": int(character.array_craft_level),
            "combat_stats_note": "frozen at snapshot time",
            "created_at": to_utc_iso(now_utc()),
        }
        payload["content_hash"] = compute_content_hash(payload)
        return payload

    # ------------------------------------------------------------------
    # 读取 / 惰性刷新
    # ------------------------------------------------------------------

    async def get_row(self, character_id: int) -> DefenseSnapshot | None:
        """取快照行；不存在返回 None。"""
        result = await self._session.execute(
            select(DefenseSnapshot)
            .where(DefenseSnapshot.character_id == character_id)
            .limit(1),
        )
        return result.scalar_one_or_none()

    async def ensure_snapshot(self, character: Character) -> DefenseSnapshot:
        """确保角色存在快照（创角 / 旧号首次访问时自动生成默认快照）。"""
        row = await self.get_row(character.id)
        if row is not None:
            return row
        payload = await self.build_payload(character)
        row = DefenseSnapshot(
            character_id=character.id,
            payload_json=json.dumps(payload, ensure_ascii=False),
            content_hash=str(payload["content_hash"]),
            updated_at=now_utc(),
        )
        self._session.add(row)
        await self._session.flush()
        logger.info("defense snapshot created character_id=%s", character.id)
        return row

    @staticmethod
    def _latest_due_slot(now: datetime, hours_utc: tuple[int, ...]) -> str | None:
        """
        计算「当前时刻应达到的最近一个定点槽位」标记（如 ``2026-08-05T10``）。

        今天已过的最大钟点；若今天所有钟点都未到，取昨天最后一个钟点。
        """
        if not hours_utc:
            return None
        sorted_hours = sorted(hours_utc)
        now_utc_dt = now.astimezone(timezone.utc)
        passed = [h for h in sorted_hours if h <= now_utc_dt.hour]
        if passed:
            slot_day = now_utc_dt.date()
            slot_hour = passed[-1]
        else:
            slot_day = (now_utc_dt - timedelta(days=1)).date()
            slot_hour = sorted_hours[-1]
        return f"{slot_day.isoformat()}T{slot_hour:02d}"

    async def lazy_daily_refresh(
        self,
        character: Character,
        now: datetime | None = None,
    ) -> DefenseSnapshot:
        """
        惰性定点补刷（设计 §6.3）：若「上次 auto 槽」落后于应达钟点则静默重建。

        渡劫等禁止态跳过；槽位标记保证同槽幂等不双刷。
        """
        current_time = now_utc(now)
        row = await self.ensure_snapshot(character)
        settings = get_settings()
        if not settings.snapshot_lazy_daily_enabled:
            return row
        if character.status in _SNAPSHOT_FORBIDDEN_STATUSES:
            return row

        cfg = get_game_config().snapshots
        due_slot = self._latest_due_slot(current_time, cfg.daily_refresh_hours_utc)
        if due_slot is None or row.last_auto_slot == due_slot:
            return row

        payload = await self.build_payload(character)
        row.payload_json = json.dumps(payload, ensure_ascii=False)
        row.content_hash = str(payload["content_hash"])
        row.last_auto_slot = due_slot
        row.updated_at = current_time
        await self._session.flush()
        logger.info(
            "defense snapshot lazy refreshed character_id=%s slot=%s",
            character.id,
            due_slot,
        )
        return row

    # ------------------------------------------------------------------
    # 手动更新
    # ------------------------------------------------------------------

    def cooldown_remaining(
        self,
        row: DefenseSnapshot | None,
        now: datetime,
    ) -> int:
        """手动更新冷却剩余秒数（0 表示可更新）。"""
        if row is None or row.last_manual_update_at is None:
            return 0
        cfg = get_game_config().snapshots
        anchor = row.last_manual_update_at
        # SQLite 可能回读 naive datetime → 统一按 UTC 处理
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=timezone.utc)
        elapsed = (now - anchor).total_seconds()
        return max(0, int(cfg.manual_cooldown_seconds - elapsed))

    async def manual_update(
        self,
        character: Character,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        手动更新防守快照。

        异常:
            AppError: ``40045`` 冷却中；``40046`` 状态禁止。
        """
        current_time = now_utc(now)
        if character.status in _SNAPSHOT_FORBIDDEN_STATUSES:
            raise AppError(
                code=40046,
                message="当前状态禁止更新防守快照",
                http_status=409,
            )
        row = await self.ensure_snapshot(character)
        remaining = self.cooldown_remaining(row, current_time)
        if remaining > 0:
            raise AppError(
                code=40045,
                message=f"快照手动更新冷却中（剩余 {remaining} 秒）",
                http_status=429,
            )

        payload = await self.build_payload(character)
        row.payload_json = json.dumps(payload, ensure_ascii=False)
        row.content_hash = str(payload["content_hash"])
        row.last_manual_update_at = current_time
        row.updated_at = current_time
        await self._session.flush()
        logger.info("defense snapshot manual updated character_id=%s", character.id)
        return {
            "snapshot": payload,
            "cooldown_remaining_seconds": self.cooldown_remaining(row, current_time),
        }

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    async def my_summary(
        self,
        character: Character,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """我的快照摘要（进大厅 / 布阵页读取；触发惰性补刷）。"""
        current_time = now_utc(now)
        row = await self.lazy_daily_refresh(character, now=current_time)
        payload = json.loads(row.payload_json)
        return {
            "snapshot": payload,
            "updated_at": to_utc_iso(row.updated_at),
            "cooldown_remaining_seconds": self.cooldown_remaining(row, current_time),
        }

    async def preview_for_attack(
        self,
        target_character_id: int,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        攻打前预览目标快照（公开战斗用字段）。

        异常:
            AppError: ``40048`` 目标无有效防守快照。
        """
        row = await self.get_row(target_character_id)
        if row is None:
            # 目标角色存在但从未生成快照 → 惰性补建（创角必有的兜底）
            result = await self._session.execute(
                select(Character).where(Character.id == target_character_id).limit(1),
            )
            target = result.scalar_one_or_none()
            if target is None:
                raise AppError(code=40048, message="目标无有效防守快照", http_status=404)
            row = await self.ensure_snapshot(target)
        payload = json.loads(row.payload_json)
        formation_id = str(payload.get("formation_id") or "none")
        formation_name = "无阵法"
        if formation_id != "none":
            try:
                formation_name = FormationService.get_formation_def_static(
                    formation_id,
                ).name
            except AppError:
                from app.domain.display_labels import label_zh_or_unknown

                formation_name = label_zh_or_unknown(formation_id)
        # 只暴露公开字段（不含 content_hash 等内部信息也无妨，此处保留全量供演算）
        return {
            "character_id": payload["character_id"],
            "dao_name": payload["dao_name"],
            "realm": payload["realm"],
            "breakthrough_grade": payload["breakthrough_grade"],
            "formation_id": formation_id,
            "formation_name": formation_name,
            "units": payload["units"],
            "updated_at": to_utc_iso(row.updated_at),
        }

    async def load_payload_for_battle(
        self,
        target_character_id: int,
    ) -> dict[str, Any]:
        """PVP 开战加载目标快照 payload；无 → ``40048``。"""
        row = await self.get_row(target_character_id)
        if row is None:
            raise AppError(code=40048, message="目标无有效防守快照", http_status=404)
        return json.loads(row.payload_json)
