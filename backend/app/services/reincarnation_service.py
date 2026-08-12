"""
轮回服务：预览 / 祭坛 / 流水 / 永久加成 / 商店 / 新生（M5 + 轮回强化）。
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import now_utc, to_utc_iso
from app.db.models.avatar import Avatar
from app.db.models.character import Character
from app.db.models.constitution import ConstitutionItem, ConstitutionSlot
from app.db.models.defense_snapshot import DefenseSnapshot
from app.db.models.inventory_item import InventoryItem
from app.db.models.reincarnation_bonus import CharacterReincarnationBonus
from app.db.models.reincarnation_log import ReincarnationLog
from app.db.models.technique import CharacterTechnique
from app.db.models.user import User
from app.domain.env_preview import parse_spirit_root_tags_json
from app.domain.reincarnation_rules import (
    ERR_NEWBORN_SELECTION,
    ERR_NEWBORN_STATUS,
    ERR_SHOP_FATE,
    ERR_SHOP_ITEM,
    ERR_SHOP_POINTS,
    ERR_SHOP_REFRESH,
    ERR_SLOT_CAP,
    build_reincarnation_plan,
    compute_reincarnation_bag_slots,
    compute_reincarnation_points,
    compute_settle_permanent_delta,
    compute_slot_cap,
    dump_legacy_items,
    dump_shop_offers,
    dump_story_flags,
    filter_random_pool,
    meets_min_major_realm,
    normalize_points_path,
    parse_growth_attrs,
    parse_legacy_items_json,
    parse_shop_offers_json,
    parse_story_flags,
    resolve_peak_major,
    roll_shop_offers,
    shop_fixed_catalog,
)
from app.schemas.common import AppError
from app.services.play_gate import PlayGate
from app.services.realm_config import get_current_stage, get_game_config, get_major_realm

logger = logging.getLogger(__name__)


class ReincarnationService:
    """
    Application service for reincarnation preview, altar, shop, and transactional reset.

    Attributes:
        _session: Async SQLAlchemy session.
        _gate: Play gate.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: Request-scoped async session.
        """
        self._session = session
        self._gate = PlayGate(session)

    def _normalize_path(self, path: str) -> str:
        """
        Map API path aliases to design ids.

        Args:
            path: Client path (``self`` / ``voluntary_ferry`` / ``forced`` / ``altar``).

        Returns:
            str: Canonical path id for preview/logs.
        """
        raw = (path or "altar").strip().lower()
        if raw in ("self", "voluntary", "voluntary_ferry", "ferry"):
            return "voluntary_ferry"
        if raw in ("forced", "timeout", "force"):
            return "forced"
        if raw == "altar":
            return "altar"
        return "altar"

    def _peak_for(self, character: Character) -> str:
        """Resolve historical peak major for points / shop / settle bonus."""
        stored = getattr(character, "peak_major_realm", None)
        return resolve_peak_major(character.major_realm, stored)

    async def _get_or_create_bonus(
        self,
        character: Character,
    ) -> CharacterReincarnationBonus:
        """
        Load or insert permanent bonus row for character.

        Args:
            character: Character entity.

        Returns:
            CharacterReincarnationBonus: Bonus row.
        """
        result = await self._session.execute(
            select(CharacterReincarnationBonus).where(
                CharacterReincarnationBonus.character_id == character.id,
            ),
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return row
        row = CharacterReincarnationBonus(character_id=character.id)
        self._session.add(row)
        await self._session.flush()
        return row

    def _bonus_public(self, bonus: CharacterReincarnationBonus) -> dict[str, Any]:
        """Serialize permanent bonus for API."""
        return {
            "initial_attr_bonus": float(bonus.initial_attr_bonus),
            "minor_growth_bonus": float(bonus.minor_growth_bonus),
            "major_growth_bonus": float(bonus.major_growth_bonus),
            "break_rate_bonus": float(bonus.break_rate_bonus),
            "lifetime_applied_growth": float(bonus.lifetime_applied_growth),
            "constitution_slots_bought": int(bonus.constitution_slots_bought),
            "spirit_root_slots_bought": int(bonus.spirit_root_slots_bought),
        }

    def _slot_caps(
        self,
        character: Character,
        bonus: CharacterReincarnationBonus,
    ) -> dict[str, int]:
        """Compute constitution / spirit_root slot caps."""
        cfg = get_game_config().reincarnation
        slots = cfg.slots or {}
        count = int(character.reincarnation_count)
        return {
            "constitution": compute_slot_cap(
                reincarnation_count=count,
                bought=int(bonus.constitution_slots_bought),
                slots_kind_cfg=dict(slots.get("constitution") or {}),
            ),
            "spirit_root": compute_slot_cap(
                reincarnation_count=count,
                bought=int(bonus.spirit_root_slots_bought),
                slots_kind_cfg=dict(slots.get("spirit_root") or {}),
            ),
        }

    def _bag_capacity(self, character: Character) -> int:
        """Reincarnation bag slot capacity."""
        cfg = get_game_config().reincarnation
        return compute_reincarnation_bag_slots(
            int(character.reincarnation_count),
            cfg.bags or {},
        )

    def _altar_min_major(self) -> str:
        """Configured minimum major for voluntary altar reincarnation."""
        cfg = get_game_config().reincarnation
        return str(cfg.altar.get("min_major_realm") or "huashen").strip() or "huashen"

    def _altar_gate(self, character: Character) -> dict[str, Any]:
        """
        Evaluate whether the character may use the voluntary altar.

        Returns:
            dict: can_altar, block_reason, min_major_realm, min_major_label_zh.
        """
        from app.services.realm_config import get_major_realm

        min_major = self._altar_min_major()
        major_cfg = get_major_realm(min_major)
        min_label = major_cfg.name if major_cfg else "化神"
        current = str(character.major_realm or "")
        ok = meets_min_major_realm(current, min_major)
        reason = None
        if not ok:
            reason = f"须达{min_label}期方可主动入轮回（祭坛）"
        return {
            "can_altar": ok,
            "altar_block_reason": reason,
            "min_major_realm": min_major,
            "min_major_label_zh": min_label,
        }

    def _preview_payload(self, character: Character, path: str) -> dict[str, Any]:
        """
        Build reincarnation preview matching frontend ``ReincarnationPreview``.

        Args:
            character: Current character.
            path: Canonical path id.

        Returns:
            dict: keep / lose / points / permanent delta / bag capacity.
        """
        cfg = get_game_config().reincarnation
        peak = self._peak_for(character)
        points_gain = compute_reincarnation_points(peak, path, cfg.points)
        forced_gain = compute_reincarnation_points(peak, "forced", cfg.points)
        permanent_delta = compute_settle_permanent_delta(
            peak,
            cfg.permanent_bonus_on_settle or {},
        )
        pet_cfg = cfg.carry.get("pet_carry") or {}
        pet_enabled = bool(pet_cfg.get("enabled", False))
        bag_slots = compute_reincarnation_bag_slots(
            int(character.reincarnation_count) + 1,
            cfg.bags or {},
        )
        keep = [
            "道号（新生页只读）",
            "体质实例（槽位有上限；超额卸下）",
            "可轮回功法（traits 含 reincarnatable）",
            "轮回袋内物品",
            "前世阅历（story flags）",
            "轮回点与永久加成",
        ]
        lose = [
            "境界进度（重置锻体一层）",
            "不可轮回功法等级",
            "普通储物袋物品",
            "本世灵根 / 免费传承（新生重选）",
            "本世已应用成长（lifetime_applied_growth 清零）",
        ]
        if str(cfg.carry.get("formation", "reset")) == "reset":
            lose.append("阵法配置（重置为默认空阵）")
        if cfg.carry.get("clear_pools", True):
            lose.append("修为/炼体/制造进度池")
        if not pet_enabled:
            lose.append("灵宠（本配置未开启带宠）")
        pet_note = (
            f"带宠开启：最多 {pet_cfg.get('max_count', 1)} 只，概率 {pet_cfg.get('chance', 0)}"
            if pet_enabled
            else "带宠关闭"
        )
        altar_gate = self._altar_gate(character)
        payload: dict[str, Any] = {
            "path": path,
            "keep": keep,
            "lose": lose,
            "points_gain": points_gain,
            "points_gain_forced": forced_gain,
            "peak_major": peak,
            "permanent_delta": permanent_delta.to_dict(),
            "reincarnation_bag_slots_after": bag_slots,
            "path_multiplier_key": normalize_points_path(path),
            "pet_carry_note": pet_note,
            "character_snapshot": {
                "major_realm": character.major_realm,
                "peak_major_realm": peak,
                "reincarnation_points": int(character.reincarnation_points),
                "reincarnation_count": int(character.reincarnation_count),
            },
        }
        # 主动祭坛路径附带门槛（待引渡自选/强制不挡）
        if path == "altar":
            payload.update(altar_gate)
        return payload

    async def preview(
        self,
        user: User,
        *,
        path: str = "altar",
    ) -> dict[str, Any]:
        """
        Preview reincarnation keep/lose list.

        Args:
            user: Authenticated user.
            path: Entry path.

        Returns:
            dict: Preview payload.
        """
        character = await self._gate.require_character(user)
        return self._preview_payload(character, self._normalize_path(path))

    async def _character_dict(self, character: Character) -> dict[str, Any]:
        """Enrich character to public dict for API envelopes."""
        from app.services.character_service import (
            CharacterService,
            character_public_to_dict,
        )

        public = await CharacterService(self._session).enrich_public(character)
        return character_public_to_dict(public)

    async def _apply_technique_carry(self, character: Character) -> list[str]:
        """
        Keep reincarnatable techniques; reset others to level 0 via delete+regrant.

        Args:
            character: Character being reset.

        Returns:
            list[str]: Technique ids kept with level.
        """
        cfg = get_game_config().techniques
        result = await self._session.execute(
            select(CharacterTechnique).where(
                CharacterTechnique.character_id == character.id,
            ),
        )
        rows = list(result.scalars().all())
        kept: list[str] = []
        for row in rows:
            tech = cfg.get(row.technique_id)
            traits = tech.traits if tech is not None else ()
            if "reincarnatable" in traits:
                kept.append(row.technique_id)
                continue
            await self._session.delete(row)
        await self._session.flush()
        from app.services.technique_service import TechniqueService

        await TechniqueService(self._session).ensure_default_techniques(character.id)
        return kept

    async def _apply_bag_carry(self, character: Character) -> dict[str, int]:
        """
        Clear normal bag; trim reincarnation bag to capacity (oldest first).

        Args:
            character: Character being reset.

        Returns:
            dict: cleared_normal / kept_reincarnation / discarded_overflow.
        """
        cfg = get_game_config().reincarnation
        clear_normal = bool(
            (cfg.bags or {}).get("normal", {}).get("clear_on_reincarnate", True),
        )
        cleared = 0
        if clear_normal:
            result = await self._session.execute(
                delete(InventoryItem).where(
                    InventoryItem.character_id == character.id,
                    InventoryItem.bag_kind == "normal",
                ),
            )
            cleared = int(result.rowcount or 0)

        cap = compute_reincarnation_bag_slots(
            int(character.reincarnation_count),
            cfg.bags or {},
        )
        rein_result = await self._session.execute(
            select(InventoryItem)
            .where(
                InventoryItem.character_id == character.id,
                InventoryItem.bag_kind == "reincarnation",
            )
            .order_by(InventoryItem.created_at.asc(), InventoryItem.id.asc()),
        )
        rein_rows = list(rein_result.scalars().all())
        discarded = 0
        if len(rein_rows) > cap:
            for row in rein_rows[cap:]:
                await self._session.delete(row)
                discarded += 1
        await self._session.flush()
        return {
            "cleared_normal": cleared,
            "kept_reincarnation": min(len(rein_rows), cap),
            "discarded_overflow": discarded,
            "bag_capacity": cap,
        }

    async def _unequip_excess_constitution(
        self,
        character: Character,
        cap: int,
    ) -> int:
        """
        Unequip constitution items beyond slot cap.

        Args:
            character: Character entity.
            cap: Max equipped items.

        Returns:
            int: Number unequipped.
        """
        result = await self._session.execute(
            select(ConstitutionItem)
            .where(
                ConstitutionItem.character_id == character.id,
                ConstitutionItem.is_equipped.is_(True),
            )
            .order_by(ConstitutionItem.id.asc()),
        )
        equipped = list(result.scalars().all())
        if len(equipped) <= cap:
            return 0
        unequipped = 0
        for item in equipped[cap:]:
            item.is_equipped = False
            slots = await self._session.execute(
                select(ConstitutionSlot).where(
                    ConstitutionSlot.character_id == character.id,
                    ConstitutionSlot.item_instance_id == item.id,
                ),
            )
            for slot in slots.scalars().all():
                slot.item_instance_id = None
            unequipped += 1
        await self._session.flush()
        return unequipped

    async def apply_reincarnation(
        self,
        character: Character,
        *,
        path: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Transactionally apply reincarnation reset (caller manages outer commit).

        Args:
            character: Character in ferry / altar path.
            path: ``forced`` / ``self`` / ``altar`` / ``voluntary_ferry``.
            now: Optional frozen time.

        Returns:
            dict: Result summary + character fields after reset.
        """
        current = now_utc(now)
        character.status = "reincarnating"
        await self._session.flush()

        cfg = get_game_config().reincarnation
        reset = cfg.carry.get("realm_reset") or {}
        target_major = str(reset.get("major", "body_tempering"))
        target_stage = int(reset.get("stage", 1))
        stage = get_current_stage(target_major, target_stage)
        stage_label = stage.label if stage else "layer_1"

        peak = self._peak_for(character)
        # 结算前刷新 peak 持久化
        character.peak_major_realm = peak

        plan = build_reincarnation_plan(
            path=path,
            major_realm=character.major_realm,
            peak_major=peak,
            spirit_stones=int(character.spirit_stones),
            growth_attrs_json=character.growth_attrs_json,
            story_flags_json=character.story_flags_json,
            reincarnation_points=int(character.reincarnation_points),
            carry_cfg=cfg.carry,
            points_cfg=cfg.points,
            story_cfg=cfg.story,
            permanent_bonus_cfg=cfg.permanent_bonus_on_settle,
            bags_cfg=cfg.bags,
            growth_attr_gain=cfg.growth_attr_gain_placeholder,
            stage_label_for_reset=stage_label,
        )

        from_major = character.major_realm
        bonus = await self._get_or_create_bonus(character)
        delta = plan.permanent_delta
        bonus.initial_attr_bonus = float(bonus.initial_attr_bonus) + delta.initial_attr
        bonus.minor_growth_bonus = float(bonus.minor_growth_bonus) + delta.minor_growth
        bonus.major_growth_bonus = float(bonus.major_growth_bonus) + delta.major_growth
        bonus.break_rate_bonus = float(bonus.break_rate_bonus) + delta.break_rate
        bonus.lifetime_applied_growth = 0.0
        bonus.updated_at = current

        character.major_realm = plan.major_realm
        character.realm_stage = plan.realm_stage
        character.realm_stage_label = plan.realm_stage_label
        character.realm_progress = plan.realm_progress
        character.cultivation_points = plan.cultivation_points
        character.body_tempering_points = plan.body_tempering_points
        character.crafting_exp = plan.crafting_exp
        character.spirit_stones = plan.spirit_stones
        character.status = plan.status
        character.idle_direction = plan.idle_direction
        character.ferry_deadline_at = None
        character.reincarnation_points = int(character.reincarnation_points) + plan.reincarnation_points_delta
        character.reincarnation_count = int(character.reincarnation_count) + 1
        character.growth_attrs_json = json.dumps(plan.growth_attrs, ensure_ascii=False)
        character.story_flags_json = dump_story_flags(plan.story_flags)
        character.breakthrough_grade = "none"
        character.last_settled_at = current
        character.updated_at = current
        character.spirit_root_tags_json = json.dumps([], ensure_ascii=False)
        character.legacy_items_json = dump_legacy_items([])
        growth_after = parse_growth_attrs(character.growth_attrs_json)
        growth_after["newborn_extra_spirit_root_slots"] = 0
        character.growth_attrs_json = json.dumps(growth_after, ensure_ascii=False)

        kept_techs = await self._apply_technique_carry(character)
        bag_stats = await self._apply_bag_carry(character)
        caps = self._slot_caps(character, bonus)
        unequipped = await self._unequip_excess_constitution(
            character,
            caps["constitution"],
        )

        if plan.dissolve_avatar:
            await self._session.execute(
                delete(Avatar).where(Avatar.character_id == character.id),
            )

        if plan.invalidate_snapshots:
            await self._session.execute(
                delete(DefenseSnapshot).where(
                    DefenseSnapshot.character_id == character.id,
                ),
            )

        # M6：卸道主 + 清本命道/道值；道池跨轮回保留
        from app.services.dao_lord_service import DaoLordService
        from app.services.dao_service import DaoService

        cleared_lords = await DaoLordService(self._session).clear_lordship_for_character(
            character.id,
        )
        # 取消进行中赛会报名
        try:
            from app.db.models import DaoContest, DaoContestEntry
            from sqlalchemy import select as sa_select

            open_contest = (
                await self._session.execute(
                    sa_select(DaoContest).where(DaoContest.status == "registration").limit(1),
                )
            ).scalar_one_or_none()
            if open_contest:
                ent = (
                    await self._session.execute(
                        sa_select(DaoContestEntry).where(
                            DaoContestEntry.contest_id == open_contest.id,
                            DaoContestEntry.character_id == character.id,
                        ),
                    )
                ).scalar_one_or_none()
                if ent:
                    await self._session.delete(ent)
        except Exception:  # noqa: BLE001
            logger.exception("cancel contest entry on reincarnation failed")
        await DaoService(self._session).reset_for_reincarnation(character.id)

        # M7 L1：本宗贡献轮回归零（D4）
        try:
            from app.services.sect_service import SectService

            await SectService(self._session).zero_contribution_on_reincarnation(
                character.id,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "sect contribution zero on reincarnation failed character_id=%s",
                character.id,
            )

        formation_reset_slots = 0
        if str(cfg.carry.get("formation", "reset")) == "reset":
            from app.services.formation_service import FormationService

            formation_reset_slots = await FormationService(
                self._session,
            ).reset_presets_to_default(character)

        # 入轮回后刷新随机货架
        await self._ensure_random_offers(character, bonus, force=True, now=current)

        summary = dict(plan.summary)
        summary.update(
            {
                "kept_techniques": kept_techs,
                "bag": bag_stats,
                "unequipped_constitution": unequipped,
                "slot_caps": caps,
                "permanent_bonus_after": self._bonus_public(bonus),
                "formation_reset_slots": formation_reset_slots,
                "dao_lord_cleared": cleared_lords,
                "dao_pool_kept": True,
            },
        )

        log = ReincarnationLog(
            character_id=character.id,
            path=path,
            from_major=from_major,
            to_major=plan.major_realm,
            points_gained=plan.reincarnation_points_delta,
            snapshot_json=json.dumps(summary, ensure_ascii=False),
        )
        self._session.add(log)
        await self._session.flush()

        logger.info(
            "reincarnation applied character_id=%s path=%s from=%s peak=%s points=%s",
            character.id,
            path,
            from_major,
            peak,
            plan.reincarnation_points_delta,
        )
        major = get_major_realm(character.major_realm)
        return {
            "path": path,
            "from_major": from_major,
            "peak_major": peak,
            "to_major": character.major_realm,
            "to_major_name": major.name if major else character.major_realm,
            "realm_stage": character.realm_stage,
            "reincarnation_points": int(character.reincarnation_points),
            "reincarnation_count": int(character.reincarnation_count),
            "points_gained": plan.reincarnation_points_delta,
            "permanent_delta": delta.to_dict(),
            "permanent_bonus": self._bonus_public(bonus),
            "story_flags": parse_story_flags(character.story_flags_json),
            "growth_attrs": parse_growth_attrs(character.growth_attrs_json),
            "log_id": log.id,
        }

    async def altar(
        self,
        user: User,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Active altar reincarnation while status=normal.

        Args:
            user: Authenticated user.
            now: Optional frozen time.

        Returns:
            dict: Reincarnation result.

        Raises:
            AppError: ``40068`` when conditions fail.
        """
        character = await self._gate.require_character(user)
        cfg = get_game_config().reincarnation
        require_status = str(cfg.altar.get("require_status", "normal"))
        if character.status != require_status:
            raise AppError(code=40068, message="当前状态不可主动轮回", http_status=400)
        gate = self._altar_gate(character)
        if not gate["can_altar"]:
            raise AppError(
                code=40068,
                message=str(gate["altar_block_reason"] or "未达主动入轮回境界门槛"),
                http_status=400,
            )
        cost = int(cfg.altar.get("spirit_stone_cost", 1000))
        if int(character.spirit_stones) < cost:
            raise AppError(code=40068, message="灵石不足以支付祭坛轮回", http_status=400)
        character.spirit_stones = int(character.spirit_stones) - cost
        result = await self.apply_reincarnation(character, path="altar", now=now)
        result["message"] = "祭坛轮回完成，请前往新生页选择灵根/传承"
        result["snapshot_invalidated"] = True
        result["points_gain"] = int(result.get("points_gained") or 0)
        result["needs_newborn_setup"] = True
        result["character"] = await self._character_dict(character)
        return result

    def _require_reincarnating(self, character: Character) -> None:
        """
        Guard newborn / shop APIs.

        Raises:
            AppError: ``40078`` when status is not reincarnating.
        """
        if character.status != "reincarnating":
            raise AppError(
                code=ERR_NEWBORN_STATUS,
                message="仅轮回新生态可操作（请先完成轮回结算）",
                http_status=400,
            )

    def _catalog_options(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        """Flatten id→{label,summary} catalog to list options."""
        items: list[dict[str, Any]] = []
        for option_id, meta in (raw or {}).items():
            if not isinstance(meta, dict):
                continue
            items.append(
                {
                    "id": str(option_id),
                    "label": str(meta.get("label") or option_id),
                    "summary": str(meta.get("summary") or ""),
                },
            )
        return items

    def _spirit_root_slot_cap(
        self,
        character: Character,
        bonus: CharacterReincarnationBonus | None = None,
    ) -> int:
        """Spirit root selectable slot cap from slots formula."""
        cfg = get_game_config().reincarnation
        slots_cfg = dict((cfg.slots or {}).get("spirit_root") or {})
        if not slots_cfg:
            # 兼容：回落 newborn.free + growth extra
            free = int(cfg.newborn.get("free_spirit_root_slots", 1))
            growth = parse_growth_attrs(character.growth_attrs_json)
            extra = int(growth.get("newborn_extra_spirit_root_slots") or 0)
            bought = int(bonus.spirit_root_slots_bought) if bonus else 0
            return max(0, free + extra + bought)
        bought = int(bonus.spirit_root_slots_bought) if bonus else 0
        return compute_slot_cap(
            reincarnation_count=int(character.reincarnation_count),
            bought=bought,
            slots_kind_cfg=slots_cfg,
        )

    async def newborn_options(self, user: User) -> dict[str, Any]:
        """Catalog + current draft for reincarnating newborn setup."""
        character = await self._gate.require_character(user)
        self._require_reincarnating(character)
        cfg = get_game_config().reincarnation
        bonus = await self._get_or_create_bonus(character)
        caps = self._slot_caps(character, bonus)

        from app.services.constitution_service import ConstitutionService

        cons_state = await ConstitutionService(self._session).get_constitution_state(
            character,
        )
        kept_constitutions: list[dict[str, Any]] = []
        for row in cons_state.get("backpack") or []:
            if not isinstance(row, dict):
                continue
            kept_constitutions.append(
                {
                    "id": row.get("id"),
                    "def_id": row.get("def_id"),
                    "name": row.get("name") or row.get("def_id"),
                    "quality": row.get("quality"),
                    "kind": row.get("kind"),
                    "equipped": bool(row.get("is_equipped")),
                },
            )

        growth = parse_growth_attrs(character.growth_attrs_json)
        return {
            "status": character.status,
            "name": character.name,
            "reincarnation_points": int(character.reincarnation_points),
            "reincarnation_count": int(character.reincarnation_count),
            "spirit_root_slots": caps["spirit_root"],
            "constitution_slots": caps["constitution"],
            "free_spirit_root_slots": int(cfg.newborn.get("free_spirit_root_slots", 1)),
            "extra_spirit_root_slots": int(bonus.spirit_root_slots_bought),
            "free_legacy_slots": int(cfg.newborn.get("free_legacy_slots", 1)),
            "require_spirit_root": bool(cfg.newborn.get("require_spirit_root", True)),
            "spirit_roots": self._catalog_options(cfg.spirit_roots),
            "legacy_catalog": self._catalog_options(cfg.legacy_catalog),
            "constitution_paths": self._catalog_options(
                dict(cfg.newborn.get("constitution_paths") or {}),
            ),
            "kept_constitutions": kept_constitutions,
            "permanent_bonus": self._bonus_public(bonus),
            "reincarnation_bag_slots": self._bag_capacity(character),
            "current": {
                "spirit_root_tags": parse_spirit_root_tags_json(
                    character.spirit_root_tags_json,
                ),
                "legacy_items": parse_legacy_items_json(character.legacy_items_json),
                "constitution_path": str(growth.get("constitution_path") or "") or None,
            },
            "shop_hint": "可花费轮回点于轮回商店（同页）；可刷新随机商品",
        }

    def _format_shop_item(
        self,
        item_id: str,
        meta: dict[str, Any],
        *,
        source: str,
    ) -> dict[str, Any]:
        """Format one shop item for catalog response."""
        return {
            "id": str(item_id),
            "label": str(meta.get("label") or item_id),
            "summary": str(meta.get("summary") or ""),
            "cost_points": int(meta.get("cost_points") or 0),
            "effect": dict(meta.get("effect") or {}),
            "source": source,
        }

    async def _ensure_random_offers(
        self,
        character: Character,
        bonus: CharacterReincarnationBonus,
        *,
        force: bool = False,
        now: datetime | None = None,
        rng_seed: int | None = None,
    ) -> list[str]:
        """
        Ensure random shop offers exist; roll when empty or forced.

        Args:
            character: Character.
            bonus: Bonus row holding offers JSON.
            force: Force re-roll.
            now: Frozen time.
            rng_seed: Optional seed for tests.

        Returns:
            list[str]: Current offer ids.
        """
        current = parse_shop_offers_json(bonus.shop_random_offers_json)
        if current and not force:
            return current
        cfg = get_game_config().reincarnation
        random_cfg = (cfg.shop or {}).get("random") or {}
        pool = random_cfg.get("pool") or {}
        offer_count = int(random_cfg.get("offer_count", 3))
        peak = self._peak_for(character)
        eligible = filter_random_pool(
            pool,
            reincarnation_count=int(character.reincarnation_count),
            peak_major=peak,
        )
        import random as random_mod

        seed = int(rng_seed) if rng_seed is not None else secrets.randbits(31)
        rng = random_mod.Random(seed)
        offers = roll_shop_offers(eligible, offer_count, rng=rng)
        bonus.shop_random_offers_json = dump_shop_offers(offers)
        bonus.shop_seed = seed
        bonus.shop_refreshed_at = now_utc(now)
        bonus.updated_at = now_utc(now)
        await self._session.flush()
        return offers

    async def shop_catalog(self, user: User) -> dict[str, Any]:
        """List fixed + random reincarnation shop items."""
        character = await self._gate.require_character(user)
        self._require_reincarnating(character)
        cfg = get_game_config().reincarnation
        bonus = await self._get_or_create_bonus(character)
        offers = await self._ensure_random_offers(character, bonus, force=False)

        fixed_raw = shop_fixed_catalog(cfg.shop or {})
        fixed_items = [
            self._format_shop_item(item_id, meta, source="fixed")
            for item_id, meta in fixed_raw.items()
            if isinstance(meta, dict)
        ]
        pool = ((cfg.shop or {}).get("random") or {}).get("pool") or {}
        random_items: list[dict[str, Any]] = []
        for offer_id in offers:
            meta = pool.get(offer_id)
            if isinstance(meta, dict):
                random_items.append(
                    self._format_shop_item(offer_id, meta, source="random"),
                )

        random_cfg = (cfg.shop or {}).get("random") or {}
        caps = self._slot_caps(character, bonus)
        return {
            "reincarnation_points": int(character.reincarnation_points),
            "fate_luck": int(character.fate_luck),
            "items": fixed_items,  # 兼容旧客户端
            "fixed_items": fixed_items,
            "random_items": random_items,
            "refresh_cost_points": int(random_cfg.get("refresh_cost_points", 5)),
            "refresh_cost_fate_luck": int(random_cfg.get("refresh_cost_fate_luck", 10)),
            "slot_caps": caps,
            "permanent_bonus": self._bonus_public(bonus),
            "reincarnation_bag_slots": self._bag_capacity(character),
        }

    async def _apply_shop_effect(
        self,
        character: Character,
        bonus: CharacterReincarnationBonus,
        effect: dict[str, Any],
        cfg: Any,
    ) -> dict[str, Any]:
        """
        Apply shop item effect dict; mutate character/bonus.

        Args:
            character: Character.
            bonus: Bonus row.
            effect: Effect mapping from YAML.
            cfg: ReincarnationConfig.

        Returns:
            dict: Granted summary.

        Raises:
            AppError: Illegal effect / slot cap.
        """
        granted: dict[str, Any] = {}
        if "grant_spirit_stones" in effect:
            stones = int(effect["grant_spirit_stones"])
            character.spirit_stones = int(character.spirit_stones) + max(0, stones)
            granted["spirit_stones"] = stones

        if "grant_legacy_id" in effect:
            legacy_id = str(effect["grant_legacy_id"]).strip()
            if legacy_id not in (cfg.legacy_catalog or {}):
                raise AppError(
                    code=ERR_SHOP_ITEM,
                    message="商品传承 id 不在目录中",
                    http_status=400,
                )
            legacy = parse_legacy_items_json(character.legacy_items_json)
            if legacy_id not in legacy:
                legacy.append(legacy_id)
            character.legacy_items_json = dump_legacy_items(legacy)
            granted["legacy_id"] = legacy_id

        if "buy_spirit_root_slot" in effect:
            delta = max(0, int(effect["buy_spirit_root_slot"]))
            slots_cfg = dict((cfg.slots or {}).get("spirit_root") or {})
            shop_max = int(slots_cfg.get("shop_max_buy", 99))
            if int(bonus.spirit_root_slots_bought) + delta > shop_max:
                raise AppError(
                    code=ERR_SLOT_CAP,
                    message=f"灵根槽购买已达上限（最多再购 {shop_max}）",
                    http_status=400,
                )
            total_max = int(slots_cfg.get("total_max", 99))
            next_cap = compute_slot_cap(
                reincarnation_count=int(character.reincarnation_count),
                bought=int(bonus.spirit_root_slots_bought) + delta,
                slots_kind_cfg=slots_cfg,
            )
            if next_cap > total_max:
                raise AppError(code=ERR_SLOT_CAP, message="灵根槽已达总上限", http_status=400)
            bonus.spirit_root_slots_bought = int(bonus.spirit_root_slots_bought) + delta
            granted["buy_spirit_root_slot"] = delta

        if "buy_constitution_slot" in effect:
            delta = max(0, int(effect["buy_constitution_slot"]))
            slots_cfg = dict((cfg.slots or {}).get("constitution") or {})
            shop_max = int(slots_cfg.get("shop_max_buy", 99))
            if int(bonus.constitution_slots_bought) + delta > shop_max:
                raise AppError(
                    code=ERR_SLOT_CAP,
                    message=f"体质槽购买已达上限（最多再购 {shop_max}）",
                    http_status=400,
                )
            bonus.constitution_slots_bought = int(bonus.constitution_slots_bought) + delta
            granted["buy_constitution_slot"] = delta

        if "upgrade_permanent" in effect:
            up = effect["upgrade_permanent"] or {}
            if not isinstance(up, dict):
                raise AppError(code=ERR_SHOP_ITEM, message="永久升级效果非法", http_status=400)
            ia = float(up.get("initial_attr", 0) or 0)
            mi = float(up.get("minor_growth", 0) or 0)
            ma = float(up.get("major_growth", 0) or 0)
            br = float(up.get("break_rate", 0) or 0)
            bonus.initial_attr_bonus = float(bonus.initial_attr_bonus) + ia
            bonus.minor_growth_bonus = float(bonus.minor_growth_bonus) + mi
            bonus.major_growth_bonus = float(bonus.major_growth_bonus) + ma
            bonus.break_rate_bonus = float(bonus.break_rate_bonus) + br
            granted["upgrade_permanent"] = {
                "initial_attr": ia,
                "minor_growth": mi,
                "major_growth": ma,
                "break_rate": br,
            }

        # 兼容旧商品
        growth = parse_growth_attrs(character.growth_attrs_json)
        if "extra_spirit_root_slots" in effect:
            delta = int(effect["extra_spirit_root_slots"])
            bonus.spirit_root_slots_bought = int(bonus.spirit_root_slots_bought) + max(0, delta)
            granted["extra_spirit_root_slots"] = delta
        if "growth_placeholder_delta" in effect:
            delta = int(effect["growth_placeholder_delta"])
            prev = int(growth.get("placeholder") or 0)
            growth["placeholder"] = prev + delta
            character.growth_attrs_json = json.dumps(growth, ensure_ascii=False)
            granted["growth_placeholder_delta"] = delta

        return granted

    async def shop_buy(
        self,
        user: User,
        *,
        item_id: str,
        source: str = "fixed",
    ) -> dict[str, Any]:
        """
        Purchase one shop item with reincarnation points.

        Args:
            user: Authenticated user.
            item_id: Shop catalog id.
            source: ``fixed`` or ``random``.

        Returns:
            dict: Purchase result + character.
        """
        character = await self._gate.require_character(user)
        self._require_reincarnating(character)
        cfg = get_game_config().reincarnation
        bonus = await self._get_or_create_bonus(character)
        src = (source or "fixed").strip().lower()
        if src not in ("fixed", "random"):
            src = "fixed"

        meta: dict[str, Any] | None = None
        if src == "fixed":
            meta = shop_fixed_catalog(cfg.shop or {}).get(item_id)
        else:
            offers = await self._ensure_random_offers(character, bonus, force=False)
            if item_id not in offers:
                raise AppError(
                    code=ERR_SHOP_ITEM,
                    message="随机货架上无此商品（可刷新）",
                    http_status=404,
                )
            pool = ((cfg.shop or {}).get("random") or {}).get("pool") or {}
            meta = pool.get(item_id)

        if not isinstance(meta, dict):
            raise AppError(
                code=ERR_SHOP_ITEM,
                message="轮回商店无此商品",
                http_status=404,
            )
        cost = int(meta.get("cost_points") or 0)
        if cost < 0:
            raise AppError(code=ERR_SHOP_ITEM, message="商品价格非法", http_status=400)
        if int(character.reincarnation_points) < cost:
            raise AppError(
                code=ERR_SHOP_POINTS,
                message=f"轮回点不足（需要 {cost}，当前 {character.reincarnation_points}）",
                http_status=400,
            )

        character.reincarnation_points = int(character.reincarnation_points) - cost
        effect = dict(meta.get("effect") or {})
        granted = await self._apply_shop_effect(character, bonus, effect, cfg)
        granted["item_id"] = item_id
        granted["cost_points"] = cost
        granted["source"] = src

        if src == "random":
            # 购买后从货架移除该格
            offers = [
                x
                for x in parse_shop_offers_json(bonus.shop_random_offers_json)
                if x != item_id
            ]
            bonus.shop_random_offers_json = dump_shop_offers(offers)

        character.updated_at = now_utc()
        bonus.updated_at = now_utc()
        await self._session.flush()
        logger.info(
            "reincarnation shop buy character_id=%s item=%s source=%s cost=%s",
            character.id,
            item_id,
            src,
            cost,
        )
        return {
            "purchased": granted,
            "message": f"已购买「{meta.get('label') or item_id}」",
            "reincarnation_points": int(character.reincarnation_points),
            "permanent_bonus": self._bonus_public(bonus),
            "character": await self._character_dict(character),
        }

    async def shop_refresh(
        self,
        user: User,
        *,
        currency: str = "points",
    ) -> dict[str, Any]:
        """
        Refresh random shop offers using reincarnation points or fate_luck.

        Args:
            user: Authenticated user.
            currency: ``points`` or ``fate_luck``.

        Returns:
            dict: New catalog slice + balances.
        """
        character = await self._gate.require_character(user)
        self._require_reincarnating(character)
        cfg = get_game_config().reincarnation
        random_cfg = (cfg.shop or {}).get("random") or {}
        cur = (currency or "points").strip().lower()
        if cur not in ("points", "fate_luck"):
            raise AppError(code=ERR_SHOP_REFRESH, message="刷新货币须为 points 或 fate_luck", http_status=400)

        if cur == "points":
            cost = int(random_cfg.get("refresh_cost_points", 5))
            if int(character.reincarnation_points) < cost:
                raise AppError(
                    code=ERR_SHOP_POINTS,
                    message=f"轮回点不足（刷新需要 {cost}）",
                    http_status=400,
                )
            character.reincarnation_points = int(character.reincarnation_points) - cost
        else:
            cost = int(random_cfg.get("refresh_cost_fate_luck", 10))
            if int(character.fate_luck) < cost:
                raise AppError(
                    code=ERR_SHOP_FATE,
                    message=f"仙缘不足（刷新需要 {cost}）",
                    http_status=400,
                )
            character.fate_luck = int(character.fate_luck) - cost

        bonus = await self._get_or_create_bonus(character)
        offers = await self._ensure_random_offers(character, bonus, force=True)
        character.updated_at = now_utc()
        await self._session.flush()

        pool = random_cfg.get("pool") or {}
        random_items = [
            self._format_shop_item(oid, pool[oid], source="random")
            for oid in offers
            if isinstance(pool.get(oid), dict)
        ]
        return {
            "refreshed": True,
            "currency": cur,
            "cost": cost,
            "random_items": random_items,
            "reincarnation_points": int(character.reincarnation_points),
            "fate_luck": int(character.fate_luck),
            "message": "随机货架已刷新",
            "character": await self._character_dict(character),
        }

    async def complete_newborn(
        self,
        user: User,
        *,
        spirit_root_ids: list[str],
        legacy_ids: list[str],
        constitution_path: str | None = None,
    ) -> dict[str, Any]:
        """Confirm newborn selections and return status to ``normal``."""
        character = await self._gate.require_character(user)
        self._require_reincarnating(character)
        cfg = get_game_config().reincarnation
        bonus = await self._get_or_create_bonus(character)

        roots_catalog = cfg.spirit_roots or {}
        legacy_catalog = cfg.legacy_catalog or {}
        path_catalog = dict(cfg.newborn.get("constitution_paths") or {})

        cleaned_roots = [str(x).strip() for x in spirit_root_ids if str(x).strip()]
        cleaned_roots = list(dict.fromkeys(cleaned_roots))
        for root_id in cleaned_roots:
            if root_id not in roots_catalog:
                raise AppError(
                    code=ERR_NEWBORN_SELECTION,
                    message=f"未知灵根：{root_id}",
                    http_status=400,
                )
        slot_cap = self._spirit_root_slot_cap(character, bonus)
        if len(cleaned_roots) > slot_cap:
            raise AppError(
                code=ERR_NEWBORN_SELECTION,
                message=f"灵根选择超过上限（最多 {slot_cap}）",
                http_status=400,
            )
        if bool(cfg.newborn.get("require_spirit_root", True)) and not cleaned_roots:
            raise AppError(
                code=ERR_NEWBORN_SELECTION,
                message="须至少选择一个灵根",
                http_status=400,
            )

        already = set(parse_legacy_items_json(character.legacy_items_json))
        free_pick = [str(x).strip() for x in legacy_ids if str(x).strip()]
        free_pick = list(dict.fromkeys(free_pick))
        free_cap = int(cfg.newborn.get("free_legacy_slots", 1))
        new_free = [x for x in free_pick if x not in already]
        if len(new_free) > free_cap:
            raise AppError(
                code=ERR_NEWBORN_SELECTION,
                message=f"免费传承超过上限（最多 {free_cap}）",
                http_status=400,
            )
        for legacy_id in new_free:
            if legacy_id not in legacy_catalog:
                raise AppError(
                    code=ERR_NEWBORN_SELECTION,
                    message=f"未知传承：{legacy_id}",
                    http_status=400,
                )
        merged_legacy = list(already) + new_free

        path_id = (constitution_path or "").strip() or None
        if path_id is not None:
            if path_catalog and path_id not in path_catalog:
                raise AppError(
                    code=ERR_NEWBORN_SELECTION,
                    message=f"未知体质倾向：{path_id}",
                    http_status=400,
                )

        character.spirit_root_tags_json = json.dumps(cleaned_roots, ensure_ascii=False)
        character.legacy_items_json = dump_legacy_items(merged_legacy)
        growth = parse_growth_attrs(character.growth_attrs_json)
        if path_id:
            growth["constitution_path"] = path_id
        elif "constitution_path" in growth:
            growth.pop("constitution_path", None)
        character.growth_attrs_json = json.dumps(growth, ensure_ascii=False)
        character.status = "normal"
        character.idle_direction = "none"
        character.updated_at = now_utc()
        await self._session.flush()

        logger.info(
            "newborn complete character_id=%s roots=%s legacy=%s path=%s",
            character.id,
            cleaned_roots,
            merged_legacy,
            path_id,
        )
        return {
            "completed": True,
            "message": "新生完成，已进入本世修行",
            "spirit_root_tags": cleaned_roots,
            "legacy_items": merged_legacy,
            "constitution_path": path_id,
            "permanent_bonus": self._bonus_public(bonus),
            "character": await self._character_dict(character),
        }

    async def list_logs(
        self,
        user: User,
        *,
        limit: int = 20,
    ) -> dict[str, Any]:
        """List recent reincarnation logs."""
        character = await self._gate.require_character(user)
        result = await self._session.execute(
            select(ReincarnationLog)
            .where(ReincarnationLog.character_id == character.id)
            .order_by(ReincarnationLog.created_at.desc())
            .limit(limit),
        )
        rows = result.scalars().all()
        items: list[dict[str, Any]] = []
        for row in rows:
            from_major = get_major_realm(row.from_major)
            to_major = get_major_realm(row.to_major)
            from_name = from_major.name if from_major else row.from_major
            to_name = to_major.name if to_major else row.to_major
            path_label = {
                "altar": "祭坛主动轮回",
                "voluntary_ferry": "待引渡自选轮回",
                "self": "待引渡自选轮回",
                "forced": "超时强制轮回",
            }.get(row.path, row.path)
            items.append(
                {
                    "id": row.id,
                    "path": row.path,
                    "from_major": row.from_major,
                    "to_major": row.to_major,
                    "points_gained": row.points_gained,
                    "points_gain": row.points_gained,
                    "created_at": to_utc_iso(row.created_at),
                    "summary": f"{path_label} · 轮回点 +{row.points_gained}",
                    "from_realm_display": from_name,
                    "to_realm_display": to_name,
                },
            )
        return {"items": items, "logs": items}
