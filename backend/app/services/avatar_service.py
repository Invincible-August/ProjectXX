"""
化身应用服务：凝练、挂机、功能闸、互传、体力、探索/任务桩、神识读数。

分层约定:
    - 领域闸门 / 索引 → ``AvatarCapabilityIndex``（配置加载时预计算）
    - 体力账本 → ``AvatarStaminaLedger``（仅脏写 ORM）
    - 仓储 → ``avatar_repo.fetch_avatar_row``（跨服务轻量查询）
    - 本类只做用例编排；面板分 lite / full，避免 enrich_public 反复算功能表。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import now_utc, to_utc_iso
from app.db.models.avatar import Avatar
from app.db.models.character import Character
from app.db.models.user import User
from app.domain.avatar_capability import AvatarCapabilityIndex
from app.constants.avatar import (
    AVATAR_CONDENSE_MAJOR_REALM,
    ERR_AVATAR_BUSY,
    ERR_AVATAR_EXISTS_OR_MISSING,
    ERR_CONDENSE_CULTIVATION,
    ERR_CONDENSE_TECHNIQUE,
    LOADOUT_ACTOR_AVATAR,
)
from app.domain.avatar_rules import (
    ERR_FEATURE_LOCKED,
    build_condense_eligibility,
    build_initial_stats,
    can_condense,
    compute_transfer_preview,
    is_allowed_avatar_idle_direction,
    validate_transfer_resource,
)
from app.domain.avatar_stamina import AvatarStaminaLedger
from app.constants.m4 import AvatarFeature, AvatarStatus, IdleDirection
from app.schemas.common import AppError
from app.services.avatar_repo import fetch_avatar_row
from app.services.character_service import CharacterService
from app.services.divine_sense_service import DivineSenseService
from app.services.m4_features import require_avatar_enabled
from app.services.play_gate import PlayGate
from app.services.realm_config import AvatarConfig, get_game_config

logger = logging.getLogger(__name__)


class AvatarService:
    """
    化身用例门面。

    请求级缓存配置与能力索引，避免同一请求内反复 ``get_game_config()``。
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        参数:
            session: SQLAlchemy 异步会话。
        """
        self._session = session
        self._gate = PlayGate(session)
        self._characters = CharacterService(session)
        # 请求内惰性缓存（配置热更新后下一请求自然换新）
        self._cfg: AvatarConfig | None = None
        self._capability: AvatarCapabilityIndex | None = None
        self._stamina_ledger: AvatarStaminaLedger | None = None

    # ------------------------------------------------------------------
    # 配置 / 能力（封装）
    # ------------------------------------------------------------------

    def _config(self) -> AvatarConfig:
        """取化身配置（请求内缓存）。"""
        if self._cfg is None:
            self._cfg = get_game_config().avatar
        return self._cfg

    def capability(self) -> AvatarCapabilityIndex:
        """
        取预计算能力索引；若 Bundle 尚未注入则现场构建一次。

        返回:
            AvatarCapabilityIndex。
        """
        if self._capability is not None:
            return self._capability
        cfg = self._config()
        if cfg.capability is not None:
            self._capability = cfg.capability
        else:
            self._capability = AvatarCapabilityIndex.from_config(
                cfg,
                get_game_config().realms,
            )
        return self._capability

    def _ledger(self) -> AvatarStaminaLedger:
        """体力账本（绑定当前能力索引）。"""
        if self._stamina_ledger is None:
            self._stamina_ledger = AvatarStaminaLedger(self.capability())
        return self._stamina_ledger

    def _require_feature(self, character: Character, feature_id: str) -> None:
        """功能未解锁 → AppError 40090。"""
        ok, code, msg = self.capability().check_feature(character.major_realm, feature_id)
        if not ok:
            raise AppError(code=code or ERR_FEATURE_LOCKED, message=msg, http_status=400)

    # ------------------------------------------------------------------
    # 仓储包装（兼容旧调用）
    # ------------------------------------------------------------------

    async def get_avatar_row(self, character_id: int) -> Avatar | None:
        """按 character_id 查化身行。"""
        return await fetch_avatar_row(self._session, character_id)

    # ------------------------------------------------------------------
    # 体力（仅脏写）
    # ------------------------------------------------------------------

    def refresh_stamina_state(
        self,
        avatar: Avatar,
        character: Character,
        *,
        now: datetime | None = None,
        persist: bool = True,
    ) -> dict[str, Any] | None:
        """
        若已解锁体力：演算恢复/日切；默认仅脏时写 ORM。

        参数:
            persist: False 时只读演算不写库（大厅摘要等）。
        """
        cap_idx = self.capability()
        if not cap_idx.is_unlocked(character.major_realm, AvatarFeature.STAMINA):
            return None
        stamp = now_utc(now)
        result = self._ledger().tick(
            character_major=character.major_realm,
            stamina=int(avatar.stamina),
            daily_actions_used=int(avatar.daily_actions_used),
            daily_actions_day=avatar.daily_actions_day or None,
            stamina_recovered_at=avatar.stamina_recovered_at,
            now=stamp,
        )
        if persist and result.dirty:
            avatar.stamina = result.stamina
            avatar.daily_actions_used = result.daily_actions_used
            avatar.daily_actions_day = result.daily_actions_day
            avatar.stamina_recovered_at = result.stamina_recovered_at
        return result.snapshot.to_dict()

    def spend_avatar_action(
        self,
        avatar: Avatar,
        character: Character,
        *,
        action_key: str,
        now: datetime | None = None,
    ) -> None:
        """
        消耗化身体力与 1 次日行动（须已解锁 stamina）。

        异常:
            AppError: 40090/40091/40092。
        """
        self._require_feature(character, AvatarFeature.STAMINA)
        stamp = now_utc(now)
        result, code, msg = self._ledger().spend(
            character_major=character.major_realm,
            stamina=int(avatar.stamina),
            daily_actions_used=int(avatar.daily_actions_used),
            daily_actions_day=avatar.daily_actions_day or None,
            stamina_recovered_at=avatar.stamina_recovered_at,
            action_key=action_key,
            now=stamp,
        )
        if code is not None:
            raise AppError(code=code, message=msg, http_status=400)
        if result.dirty:
            avatar.stamina = result.stamina
            avatar.daily_actions_used = result.daily_actions_used
            avatar.daily_actions_day = result.daily_actions_day
            avatar.stamina_recovered_at = result.stamina_recovered_at

    # ------------------------------------------------------------------
    # 面板序列化
    # ------------------------------------------------------------------

    def _base_panel(self, avatar: Avatar) -> dict[str, Any]:
        """核心字段（无功能表 / 无体力刷新）——供 enrich_public 等高频路径。"""
        stats = json.loads(avatar.base_stats_json or "{}")
        return {
            "id": avatar.id,
            "name": avatar.name,
            "status": avatar.status,
            "idle_direction": avatar.idle_direction,
            "cultivation_points": int(avatar.cultivation_points),
            "body_tempering_points": int(avatar.body_tempering_points),
            "crafting_exp": int(avatar.crafting_exp),
            "base_stats": stats,
            "major_realm": str(getattr(avatar, "major_realm", "") or ""),
            "realm_stage": int(getattr(avatar, "realm_stage", 1) or 1),
            "realm_stage_label": str(getattr(avatar, "realm_stage_label", "") or ""),
            "realm_progress": int(getattr(avatar, "realm_progress", 0) or 0),
            "assist_friends_enabled": bool(getattr(avatar, "assist_friends_enabled", 0)),
            "last_settled_at": to_utc_iso(avatar.last_settled_at),
            "created_at": to_utc_iso(avatar.created_at),
        }

    def _panel_dict(
        self,
        avatar: Avatar,
        character: Character | None = None,
        *,
        now: datetime | None = None,
        full: bool = True,
        persist_stamina: bool = True,
    ) -> dict[str, Any]:
        """
        化身 ORM → 面板字典。

        参数:
            full: True 附带 features / battle_modes / transfer 说明；False 仅核心字段。
            persist_stamina: full 时是否允许脏写体力。
        """
        payload = self._base_panel(avatar)
        if character is None or not full:
            return payload

        cap_idx = self.capability()
        features, preview = cap_idx.list_feature_states(character.major_realm)
        payload["features"] = features
        payload["unlock_preview"] = preview
        payload["stamina"] = self.refresh_stamina_state(
            avatar,
            character,
            now=now,
            persist=persist_stamina,
        )
        # 助战专用体力（与探索/独战 stamina 隔离；仅随境界变容）
        if cap_idx.is_unlocked(character.major_realm, AvatarFeature.FRIEND_ASSIST):
            from app.services.avatar_assist_service import AvatarAssistService

            payload["assist_stamina"] = AvatarAssistService(
                self._session,
            ).refresh_assist_stamina(
                avatar,
                character,
                persist=persist_stamina,
            )
        else:
            payload["assist_stamina"] = None
        payload["battle_modes"] = {
            "with_main": True,
        }
        payload["transfer_summary"] = cap_idx.transfer_summary
        payload["transfer_retention_ratio"] = cap_idx.retention_ratio(character.major_realm)
        return payload

    async def get_summary(self, character: Character) -> dict[str, Any] | None:
        """
        轻量摘要（大厅 / enrich_public）：不建功能表、不刷新体力。

        返回:
            核心面板或 None。
        """
        avatar = await self.get_avatar_row(character.id)
        if avatar is None:
            return None
        panel = self._base_panel(avatar)
        await self._attach_dao(panel, character, avatar)
        return panel

    async def get_me(self, character: Character, now: datetime | None = None) -> dict[str, Any] | None:
        """化身完整面板；未凝练返回 None。"""
        avatar = await self.get_avatar_row(character.id)
        if avatar is None:
            return None
        panel = self._panel_dict(avatar, character, now=now, full=True)
        await self._enrich_combat_panel(panel, avatar, character)
        await self._attach_dao(panel, character, avatar)
        return panel

    async def _attach_dao(
        self,
        panel: dict[str, Any],
        character: Character,
        avatar: Avatar,
    ) -> None:
        """把化身独立大道摘要挂到面板。"""
        from app.services.dao_service import DaoService

        panel["dao"] = await DaoService(self._session).enrich_avatar_dao_summary(
            character,
            avatar,
        )

    async def get_features(self, character: Character) -> dict[str, Any]:
        """
        GET /avatar/features：功能表 + 凝练权威闸。

        ``condense`` 与 POST /condense 同源规则，前端 UI 闸应消费此字段，勿本地抄境界序。
        """
        require_avatar_enabled()
        features, preview = self.capability().list_feature_states(character.major_realm)
        avatar_cfg = self._config()
        existing = await self.get_avatar_row(character.id)
        condense = build_condense_eligibility(
            character_major=character.major_realm,
            spirit_stones=int(character.spirit_stones),
            cultivation_points=int(character.cultivation_points),
            has_avatar=existing is not None,
            unlock_major=avatar_cfg.unlock_major_realm,
            max_avatars=avatar_cfg.max_avatars,
            spirit_stone_cost=avatar_cfg.condense_spirit_stone_cost,
            cultivation_cost=avatar_cfg.condense_cultivation_cost,
            realms=get_game_config().realms,
        )
        await self._attach_condense_recipe(character, avatar_cfg, condense)
        return {
            "major_realm": character.major_realm,
            "features": features,
            "unlock_preview": preview,
            "condense": condense,
        }

    async def _attach_condense_recipe(
        self,
        character: Character,
        avatar_cfg: AvatarConfig,
        condense: dict[str, Any],
    ) -> None:
        """把功法/媒介候选挂到凝练闸（未凝练页点槽用）。"""
        from app.services.inventory_service import InventoryService
        from app.services.technique_service import TechniqueService

        techs = await TechniqueService(self._session).list_my_techniques(character)
        allow_tech = set(avatar_cfg.condense_technique_ids)
        if allow_tech:
            techs = [row for row in techs if str(row.get("id")) in allow_tech]
        technique_candidates = [
            {
                "id": str(row["id"]),
                "name": str(row.get("name") or row["id"]),
                "level": int(row.get("level") or 0),
                "max_level": int(row.get("max_level") or 0),
            }
            for row in techs
        ]
        bag = await InventoryService(self._session).list_items(character.id)
        allow_med = set(avatar_cfg.condense_medium_item_ids)
        qty_need = int(avatar_cfg.condense_medium_quantity)
        grouped: dict[str, dict[str, Any]] = {}
        for item in bag:
            if str(item.get("bag_kind") or "normal") != "normal":
                continue
            item_id = str(item.get("item_id") or "")
            if not item_id:
                continue
            if allow_med and item_id not in allow_med:
                continue
            if str(item.get("item_type") or "") != "material":
                continue
            slot = grouped.setdefault(
                item_id,
                {
                    "item_id": item_id,
                    "name": str(item.get("name") or item_id),
                    "quantity": 0,
                },
            )
            slot["quantity"] = int(slot["quantity"]) + int(item.get("quantity") or 0)
        medium_candidates = list(grouped.values())
        technique_ok = bool(technique_candidates)
        medium_ok = (
            not allow_med
            or any(int(row["quantity"]) >= qty_need for row in medium_candidates)
        )
        condense["cultivation_cost"] = int(avatar_cfg.condense_cultivation_cost)
        condense["technique_required"] = True
        condense["technique_candidates"] = technique_candidates
        condense["technique_ok"] = technique_ok
        condense["medium_required"] = bool(allow_med)
        condense["medium_item_ids"] = list(avatar_cfg.condense_medium_item_ids)
        condense["medium_quantity"] = qty_need
        condense["medium_candidates"] = medium_candidates
        condense["medium_ok"] = medium_ok

    def _jindan_start_fields(self) -> dict[str, Any]:
        """凝练起始：金丹第一档、修为池 0。"""
        from app.services.realm_config import get_major_realm

        major = get_major_realm(AVATAR_CONDENSE_MAJOR_REALM)
        first = major.stages[0] if major and major.stages else None
        stage = int(first.stage) if first else 1
        label = str(first.label) if first else "early"
        return {
            "major_realm": AVATAR_CONDENSE_MAJOR_REALM,
            "realm_stage": stage,
            "realm_stage_label": label,
            "realm_progress": 0,
            "cultivation_points": 0,
        }

    async def _enrich_combat_panel(
        self,
        payload: dict[str, Any],
        avatar: Avatar,
        character: Character,
    ) -> None:
        """按化身自身境界 + 独立穿戴槽组装战力（与本体槽互不影响）。"""
        packed = await self._characters.build_combat_attrs(
            character,
            entity_kind="avatar",
            apply_reincarnation_attr_bonus=False,
            realm_major=str(getattr(avatar, "major_realm", "") or "") or character.major_realm,
            realm_stage=int(getattr(avatar, "realm_stage", 0) or 0) or character.realm_stage,
            loadout_actor=LOADOUT_ACTOR_AVATAR,
        )
        combat = packed.get("combat") or {}
        life = packed.get("life") or {}
        hp_max = int((combat.get("final") or {}).get("hp") or 0)
        mp_max = int((combat.get("final") or {}).get("mp") or 0)
        payload["combat"] = combat
        payload["life"] = life
        payload["hp_max"] = hp_max
        payload["hp_current"] = hp_max
        payload["mp_max"] = mp_max
        payload["mp_current"] = mp_max

    # ------------------------------------------------------------------
    # 用例
    # ------------------------------------------------------------------

    async def condense(
        self,
        user: User,
        *,
        technique_id: str | None = None,
        medium_item_id: str | None = None,
        skip_cost: bool = False,
        require_recipe: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        凝练化身（PlayGate 清 pending + 双线程 settle 先行）。

        玩法 HTTP 传 ``require_recipe=True``，须填化身功法与媒介。
        单测内部调用可省略配方，只扣灵石（与旧行为兼容）。

        异常:
            AppError: 40050/40051/40053/40054/灵石不足/材料不足。
        """
        require_avatar_enabled()
        character, _ = await self._gate.prepare_for_play(user, now=now)

        avatar_cfg = self._config()
        cap_idx = self.capability()
        existing = await self.get_avatar_row(character.id)
        allowed, err = can_condense(
            character_major=character.major_realm,
            has_avatar=existing is not None,
            unlock_major=avatar_cfg.unlock_major_realm,
            max_avatars=avatar_cfg.max_avatars,
            realms=get_game_config().realms,
        )
        if not allowed:
            # 细分文案，便于联调与前端提示（错误码仍与 can_condense 一致）
            if err == 40051:
                message = "已凝练化身"
            elif err == 40050:
                message = (
                    f"未达凝练境界（需 {avatar_cfg.unlock_major_realm} 及以上）"
                )
            else:
                message = "未达凝练境界或已有化身"
            raise AppError(
                code=err or 40050,
                message=message,
                http_status=400,
            )

        stone_cost = int(avatar_cfg.condense_spirit_stone_cost)
        cult_cost = int(avatar_cfg.condense_cultivation_cost)
        if not skip_cost:
            if int(character.spirit_stones) < stone_cost:
                raise AppError(code=40000, message="灵石不足以凝练化身", http_status=400)
            if require_recipe and int(character.cultivation_points) < cult_cost:
                raise AppError(
                    code=ERR_CONDENSE_CULTIVATION,
                    message=f"灵力不足（需 {cult_cost}）",
                    http_status=400,
                )
            if require_recipe:
                await self._consume_condense_recipe(
                    character,
                    avatar_cfg,
                    technique_id=technique_id,
                    medium_item_id=medium_item_id,
                )
            character.spirit_stones = int(character.spirit_stones) - stone_cost
            if require_recipe and cult_cost > 0:
                character.cultivation_points = int(character.cultivation_points) - cult_cost

        main_atk, main_hp, _, _ = await self._characters.build_combat_stats(character)
        stats = build_initial_stats(
            main_atk,
            main_hp,
            initial_stat_ratio=avatar_cfg.initial_stat_ratio,
            material_mod=avatar_cfg.material_mod_placeholder,
        )
        created_at = now_utc(now)
        initial_stamina = 0
        if cap_idx.is_unlocked(character.major_realm, AvatarFeature.STAMINA):
            initial_stamina = cap_idx.stamina_cap(character.major_realm)
        # 助战体力独立满额初始化（已解锁 friend_assist 时）
        initial_assist_stamina = 0
        assist_recovered_at = None
        if cap_idx.is_unlocked(character.major_realm, AvatarFeature.FRIEND_ASSIST):
            from app.domain.avatar_assist_stamina import assist_stamina_cap

            initial_assist_stamina = assist_stamina_cap(
                character_major=str(character.major_realm),
                assist_cfg=avatar_cfg.friend_assist,
            )
            assist_recovered_at = created_at
        avatar = Avatar(
            character_id=character.id,
            name=f"{character.name}化身",
            status=AvatarStatus.IDLE,
            idle_direction=IdleDirection.NONE,
            body_tempering_points=0,
            crafting_exp=0,
            base_stats_json=json.dumps(stats, ensure_ascii=False),
            stamina=initial_stamina,
            daily_actions_used=0,
            daily_actions_day="",
            stamina_recovered_at=created_at if initial_stamina > 0 else None,
            assist_stamina=initial_assist_stamina,
            assist_stamina_recovered_at=assist_recovered_at,
            assist_stamina_locked=0,
            last_settled_at=created_at,
            created_at=created_at,
            **self._jindan_start_fields(),
        )
        self._session.add(avatar)
        await self._session.flush()
        await self._session.refresh(avatar)
        logger.info("avatar condensed character_id=%s avatar_id=%s", character.id, avatar.id)
        panel = self._panel_dict(avatar, character, now=created_at)
        await self._enrich_combat_panel(panel, avatar, character)
        await self._attach_dao(panel, character, avatar)
        return panel

    async def _consume_condense_recipe(
        self,
        character: Character,
        avatar_cfg: AvatarConfig,
        *,
        technique_id: str | None,
        medium_item_id: str | None,
    ) -> None:
        """校验并消耗凝练配方（功法不消耗，媒介从背包扣）。"""
        from app.services.inventory_service import InventoryService
        from app.services.technique_service import TechniqueService

        tid = str(technique_id or "").strip()
        if not tid:
            raise AppError(
                code=ERR_CONDENSE_TECHNIQUE,
                message="请填入化身功法",
                http_status=400,
            )
        learned = await TechniqueService(self._session).list_my_techniques(character)
        if not any(str(row.get("id")) == tid for row in learned):
            raise AppError(
                code=ERR_CONDENSE_TECHNIQUE,
                message="尚未学会该化身功法",
                http_status=400,
            )
        allow_tech = set(avatar_cfg.condense_technique_ids)
        if allow_tech and tid not in allow_tech:
            raise AppError(
                code=ERR_CONDENSE_TECHNIQUE,
                message="该功法不可用于凝练化身",
                http_status=400,
            )

        allow_med = list(avatar_cfg.condense_medium_item_ids)
        if not allow_med:
            return
        mid = str(medium_item_id or "").strip()
        if not mid:
            raise AppError(code=40055, message="请填入凝练媒介", http_status=400)
        if mid not in allow_med:
            raise AppError(code=40055, message="该物品不可作为凝练媒介", http_status=400)
        await InventoryService(self._session).remove_materials(
            character.id,
            [{"item_id": mid, "quantity": int(avatar_cfg.condense_medium_quantity)}],
        )

    async def dismiss(
        self,
        user: User,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        破除已凝练化身（不退资源）。

        异常:
            AppError: 尚未凝练 / 工坊占用中。
        """
        require_avatar_enabled()
        character, _ = await self._gate.prepare_for_play(user, now=now)
        avatar = await self.get_avatar_row(character.id)
        if avatar is None:
            raise AppError(
                code=ERR_AVATAR_EXISTS_OR_MISSING,
                message="尚未凝练化身",
                http_status=400,
            )

        from app.constants.m4 import CRAFT_ACTIVE_STATUSES, CraftActor
        from app.db.models.craft_job import CraftJob
        from sqlalchemy import select, update

        from app.db.models.avatar_assist import AvatarAssistSession

        stamp = now_utc(now)
        active_job = (
            await self._session.execute(
                select(CraftJob.id).where(
                    CraftJob.character_id == character.id,
                    CraftJob.actor == CraftActor.AVATAR,
                    CraftJob.status.in_(tuple(CRAFT_ACTIVE_STATUSES)),
                ).limit(1),
            )
        ).scalar_one_or_none()
        if active_job is not None:
            raise AppError(
                code=ERR_AVATAR_BUSY,
                message="化身正在工坊中，请先完成或领取后再破除",
                http_status=400,
            )

        if str(avatar.idle_direction or "") == "sect_mining":
            from app.services.sect_facility_service import SectFacilityService

            await SectFacilityService(self._session).stop_avatar_mining(character, avatar)

        from app.services.equipment_service import EquipmentService

        await EquipmentService(self._session).unequip_all_avatar(character.id)
        transferred = int(avatar.cultivation_points or 0)
        if transferred > 0:
            character.cultivation_points = int(character.cultivation_points) + transferred
        # 淬体值随化身行删除，不转入本体

        await self._session.execute(
            update(AvatarAssistSession)
            .where(
                AvatarAssistSession.avatar_id == avatar.id,
                AvatarAssistSession.status.in_(("invited", "active")),
            )
            .values(status="ended", ended_at=stamp),
        )

        avatar_id = int(avatar.id)
        await self._session.delete(avatar)
        await self._session.flush()

        from app.services.formation_service import FormationService

        await FormationService(self._session).prune_invalid_units_from_presets(character)
        logger.info(
            "avatar dismissed character_id=%s avatar_id=%s",
            character.id,
            avatar_id,
        )
        return {
            "dismissed": True,
            "avatar_id": avatar_id,
            "transferred_cultivation": transferred,
        }

    async def set_idle(
        self,
        user: User,
        direction: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """设置化身挂机方向（校验 feature idle_*）。"""
        require_avatar_enabled()
        character, _ = await self._gate.prepare_for_play(user, now=now, settle=False)
        from app.services.idle_service import IdleService

        dual = await IdleService(self._session).settle_dual_async(character, now=now)
        avatar = await self.get_avatar_row(character.id)
        if avatar is None:
            raise AppError(code=40051, message="尚未凝练化身", http_status=400)

        if not is_allowed_avatar_idle_direction(direction):
            raise AppError(code=40000, message="无效的挂机方向", http_status=400)

        # 离开采矿：先结算再切方向
        prev_dir = str(avatar.idle_direction or "none")
        if prev_dir == "sect_mining" and direction != "sect_mining":
            from app.services.sect_facility_service import SectFacilityService

            await SectFacilityService(self._session).stop_avatar_mining(character, avatar)

        ok, blocked_feature = self.capability().idle_direction_allowed(
            character.major_realm,
            direction,
        )
        if not ok:
            if blocked_feature and not self.capability().is_unlocked(
                character.major_realm,
                blocked_feature,
            ):
                self._require_feature(character, blocked_feature)
            raise AppError(
                code=ERR_FEATURE_LOCKED,
                message=f"化身挂机方向未开放：{direction}",
                http_status=400,
            )

        if direction == "sect_mining":
            from app.services.sect_facility_service import SectFacilityService

            await SectFacilityService(self._session).start_avatar_mining(character, avatar)
            panel = self._panel_dict(avatar, character, now=now)
            return await self._idle_mutation_payload(panel, dual, character)

        avatar.idle_direction = direction
        # 从点击切换起重新计时一整段 tick（与本体 set_direction 一致，非墙钟整分对齐）
        if direction in {"spirit", "body", "crafting"}:
            avatar.last_settled_at = now_utc(now)
        await self._session.flush()
        panel = self._panel_dict(avatar, character, now=now)
        return await self._idle_mutation_payload(panel, dual, character)

    @staticmethod
    def _with_idle_gains(panel: dict[str, Any], dual: Any) -> dict[str, Any]:
        """Attach this settle's avatar thread gains for hall event logs."""
        av = getattr(dual, "avatar", None)
        panel["idle_gains"] = {
            "settled_ticks": int(getattr(av, "ticks", 0) or 0),
            "gained_cultivation": int(getattr(av, "gained_cultivation", 0) or 0),
            "gained_body": int(getattr(av, "gained_body", 0) or 0),
            "gained_crafting": int(getattr(av, "gained_crafting", 0) or 0),
            "spent_spirit_stones": int(getattr(av, "spent_spirit_stones", 0) or 0),
        }
        return panel

    async def _idle_mutation_payload(
        self,
        panel: dict[str, Any],
        dual: Any,
        character: Character,
    ) -> dict[str, Any]:
        """
        化身切方向回包：面板 + 最新角色（含独立 avatar_last_settled_at）。

        大厅进度条读 character.dual_idle_preview，必须在同一次响应里带上重置后的锚点，
        避免前端再 GET /characters/me 时被在途 idle sync 用旧相位覆盖。
        """
        panel = self._with_idle_gains(panel, dual)
        avatar = await self.get_avatar_row(character.id)
        if avatar is not None:
            await self._attach_dao(panel, character, avatar)
        public = await self._characters.enrich_public(character)
        return {
            "avatar": panel,
            "character": self._characters.public_to_dict(public),
            "idle_gains": panel.get("idle_gains"),
        }

    async def transfer_preview(
        self,
        user: User,
        *,
        direction: str,
        resource: str,
        amount: int,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """互传预览（只读：不 settle、不扣池）。"""
        del now  # 预览不依赖 settle 时刻
        require_avatar_enabled()
        character = await self._gate.require_character(user)
        avatar = await self.get_avatar_row(character.id)
        if avatar is None:
            raise AppError(code=40051, message="尚未凝练化身", http_status=400)
        self._require_feature(character, AvatarFeature.TRANSFER_CULTIVATION)
        cap_idx = self.capability()
        ok, err = validate_transfer_resource(
            resource,
            allow=cap_idx.transfer_allow,
            deny=cap_idx.transfer_deny,
        )
        if not ok:
            raise AppError(code=err or 40052, message="该资源不可互传", http_status=400)
        retention = cap_idx.retention_ratio(character.major_realm)
        preview = compute_transfer_preview(
            amount,
            retention_ratio=retention,
            min_amount=cap_idx.transfer_min_amount,
        )
        preview["direction"] = direction
        preview["resource"] = resource
        preview["summary"] = cap_idx.transfer_summary
        return preview

    async def transfer(
        self,
        user: User,
        *,
        direction: str,
        resource: str,
        amount: int,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        修为互传（按 retention_ratio 到账）。

        异常:
            AppError: 40052 / 40090 / 40000。
        """
        require_avatar_enabled()
        character, _ = await self._gate.prepare_for_play(user, now=now)
        avatar = await self.get_avatar_row(character.id)
        if avatar is None:
            raise AppError(code=40051, message="尚未凝练化身", http_status=400)

        self._require_feature(character, AvatarFeature.TRANSFER_CULTIVATION)
        cap_idx = self.capability()
        ok, err = validate_transfer_resource(
            resource,
            allow=cap_idx.transfer_allow,
            deny=cap_idx.transfer_deny,
        )
        if not ok:
            raise AppError(code=err or 40052, message="该资源不可互传", http_status=400)

        retention = cap_idx.retention_ratio(character.major_realm)
        preview = compute_transfer_preview(
            amount,
            retention_ratio=retention,
            min_amount=cap_idx.transfer_min_amount,
        )
        if not preview["ok"]:
            raise AppError(code=40000, message=preview["message"] or "互传数量非法", http_status=400)

        gross = int(preview["gross"])
        net = int(preview["net"])

        if direction == "main_to_avatar":
            if int(character.cultivation_points) < gross:
                raise AppError(code=40000, message="本体修为不足", http_status=400)
            character.cultivation_points = int(character.cultivation_points) - gross
            avatar.cultivation_points = int(avatar.cultivation_points) + net
        elif direction == "avatar_to_main":
            if int(avatar.cultivation_points) < gross:
                raise AppError(code=40000, message="化身修为不足", http_status=400)
            avatar.cultivation_points = int(avatar.cultivation_points) - gross
            character.cultivation_points = int(character.cultivation_points) + net
        else:
            raise AppError(code=40000, message="无效转移方向", http_status=400)

        await self._session.flush()
        await self._session.refresh(character)
        await self._session.refresh(avatar)
        logger.info(
            "avatar transfer character_id=%s dir=%s gross=%s net=%s retention=%s",
            character.id,
            direction,
            gross,
            net,
            retention,
        )
        public = await self._characters.enrich_public(character)
        return {
            "main_cultivation": int(character.cultivation_points),
            "avatar_cultivation": int(avatar.cultivation_points),
            "gross": gross,
            "net": net,
            "fee": int(preview["fee"]),
            "retention_ratio": retention,
            "summary": cap_idx.transfer_summary,
            "character": self._characters.public_to_dict(public),
            "avatar": self._panel_dict(avatar, character, now=now),
        }

    async def explore_status(
        self,
        user: User,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """探索代理桩：只读，不 settle。"""
        require_avatar_enabled()
        character = await self._gate.require_character(user)
        avatar = await self.get_avatar_row(character.id)
        if avatar is None:
            raise AppError(code=40051, message="尚未凝练化身", http_status=400)
        cap_idx = self.capability()
        unlocked = cap_idx.is_unlocked(character.major_realm, AvatarFeature.EXPLORE_PROXY)
        # 只读：不持久化体力 tick，避免桩接口写库
        stamina_panel = self.refresh_stamina_state(
            avatar,
            character,
            now=now,
            persist=False,
        )
        return {
            "unlocked": unlocked,
            "implemented": False,
            "message": (
                "探索代理已解锁（占位）；真地图行走见 M9"
                if unlocked
                else "化神后方可探索代理"
            ),
            "region_id": None,
            "stamina": stamina_panel,
            "action_cost": cap_idx.action_cost("explore_step"),
        }

    async def quest_accept_stub(
        self,
        user: User,
        *,
        quest_kind: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """任务能力闸 + 桩：解锁后耗体但不改进度。"""
        require_avatar_enabled()
        character, _ = await self._gate.prepare_for_play(user, now=now)
        avatar = await self.get_avatar_row(character.id)
        if avatar is None:
            raise AppError(code=40051, message="尚未凝练化身", http_status=400)

        if quest_kind not in {"npc", "sect"}:
            raise AppError(code=40000, message="quest_kind 须为 npc 或 sect", http_status=400)
        feature_id = (
            AvatarFeature.QUEST_NPC if quest_kind == "npc" else AvatarFeature.QUEST_SECT
        )
        self._require_feature(character, feature_id)
        if self.capability().is_unlocked(character.major_realm, AvatarFeature.STAMINA):
            self.spend_avatar_action(avatar, character, action_key="quest_accept", now=now)
            await self._session.flush()

        return {
            "ok": False,
            "code": 50110,
            "implemented": False,
            "quest_kind": quest_kind,
            "message": "化身任务玩法尚未实装（挂 M7）；能力闸已通过",
            "avatar": self._panel_dict(avatar, character, now=now),
        }

    async def get_sense(
        self,
        character: Character,
        units: list[dict] | None = None,
    ) -> dict[str, Any]:
        """
        神识读数。

        ``units is None``（角色面板 / GET /avatar/sense / 开战超载）：按装备栏合计
        （化身上阵开关 + 灵宠槽 + 傀儡编成板）。与棋盘是否落子无关。
        传入编成列表时只统计该列表（兼容旧调用）。
        """
        if units is None:
            av_count, pet_costs, puppet_costs = await self._persistent_sense_parts(character)
        else:
            av_count, _pet_n, pet_costs, _pup_n, puppet_costs = (
                DivineSenseService.count_deployed_from_units(units)
            )
            pet_costs = await self._enrich_pet_costs(character.id, units)
        return DivineSenseService.snapshot_for_character(
            character,
            avatar_deploy_count=av_count,
            pet_deploy_count=len(pet_costs),
            pet_costs=pet_costs or None,
            puppet_deploy_count=len(puppet_costs),
            puppet_costs=puppet_costs or None,
        )

    async def _persistent_sense_parts(
        self,
        character: Character,
    ) -> tuple[int, list[int], list[int]]:
        """角色面板：装备栏化身开关 + 灵宠槽 + 编成板傀儡。"""
        from sqlalchemy import select

        from app.db.models.avatar import Avatar
        from app.services.equipment_service import EquipmentService

        eq = EquipmentService(self._session)
        loadout, _bag = await eq.list_puppet_loadout(character.id)
        puppet_costs = [
            int(p.get("divine_sense_cost") or 0)
            for p in loadout
            if p.get("counts_toward_load", True)
        ]

        av_count = 0
        result = await self._session.execute(
            select(Avatar).where(Avatar.character_id == character.id).limit(1),
        )
        avatar = result.scalar_one_or_none()
        if avatar is not None and int(getattr(avatar, "is_deployed", 0) or 0) == 1:
            av_count = 1

        pet_costs: list[int] = []
        equipped = await self._equipped_pet_sense_cost(character.id)
        if equipped is not None:
            pet_costs = [equipped]
        return av_count, pet_costs, puppet_costs

    async def _enrich_pet_costs(
        self,
        character_id: int,
        units: list[dict[str, Any]],
    ) -> list[int]:
        """按编成 ref_id 套物种 divine_sense_cost。"""
        from sqlalchemy import select

        from app.constants.battle import PIECE_KIND_PET
        from app.db.models.pet import Pet

        cfg = get_game_config()
        ds = cfg.divine_sense
        pets_cfg = cfg.pets
        costs: list[int] = []
        for unit in units:
            if str(unit.get("unit_kind") or "") != PIECE_KIND_PET:
                continue
            cost = int(ds.cost_pet)
            ref_id = unit.get("ref_id")
            if ref_id is not None:
                row = await self._session.execute(
                    select(Pet).where(
                        Pet.id == int(ref_id),
                        Pet.character_id == character_id,
                    ),
                )
                pet_row = row.scalar_one_or_none()
                if pet_row is not None:
                    sp = pets_cfg.species.get(pet_row.species_id)
                    if sp is not None and sp.divine_sense_cost is not None:
                        cost = int(sp.divine_sense_cost)
            costs.append(cost)
        return costs

    async def _equipped_pet_sense_cost(self, character_id: int) -> int | None:
        """灵宠槽已上阵时的神识消耗；空槽返回 None。"""
        from sqlalchemy import select

        from app.constants.equipment import EQUIPMENT_SLOT_PET
        from app.db.models.character_equipment import CharacterEquipmentSlot
        from app.db.models.inventory_item import InventoryItem

        row = await self._session.execute(
            select(CharacterEquipmentSlot).where(
                CharacterEquipmentSlot.character_id == character_id,
                CharacterEquipmentSlot.slot == EQUIPMENT_SLOT_PET,
            ),
        )
        slot = row.scalar_one_or_none()
        if slot is None or slot.inventory_item_id is None:
            return None
        inv = await self._session.get(InventoryItem, int(slot.inventory_item_id))
        if inv is None:
            return None
        cfg = get_game_config()
        cost = int(cfg.divine_sense.cost_pet)
        species_id = str(inv.item_id)
        try:
            meta = json.loads(inv.meta_json or "{}")
        except json.JSONDecodeError:
            meta = {}
        if meta.get("species_id"):
            species_id = str(meta["species_id"])
        elif meta.get("pet_id"):
            from app.db.models.pet import Pet

            pet_row = await self._session.get(Pet, int(meta["pet_id"]))
            if pet_row is not None:
                species_id = pet_row.species_id
        sp = cfg.pets.species.get(species_id)
        if sp is not None and sp.divine_sense_cost is not None:
            cost = int(sp.divine_sense_cost)
        return cost

    async def live_combat_stats(
        self,
        character: Character,
        avatar: Avatar,
    ) -> dict[str, int]:
        """
        化身上阵战力：自身境界 + 独立装备/功法槽（不读凝练快照）。

        Args:
            character: 宿主角色（背包与功法收藏仍挂在本体上）。
            avatar: 化身 ORM。

        Returns:
            dict[str, int]: atk / hp / speed，均至少为 1。
        """
        packed = await self._characters.build_combat_attrs(
            character,
            entity_kind="avatar",
            apply_reincarnation_attr_bonus=False,
            realm_major=str(getattr(avatar, "major_realm", "") or "jindan"),
            realm_stage=int(getattr(avatar, "realm_stage", 0) or 1),
            loadout_actor=LOADOUT_ACTOR_AVATAR,
        )
        final = (packed.get("combat") or {}).get("final") or {}
        return {
            "atk": max(1, int(final.get("phys_atk") or final.get("atk") or 1)),
            "hp": max(1, int(final.get("hp") or 1)),
            "speed": max(1, int(final.get("speed") or 8)),
        }

    @staticmethod
    def avatar_combat_stats(avatar: Avatar) -> dict[str, int]:
        """从化身快照 JSON 读取战斗面板（客串缺宿主时的回退）。"""
        stats = json.loads(avatar.base_stats_json or "{}")
        return {
            "atk": max(1, int(stats.get("atk", 1))),
            "hp": max(1, int(stats.get("hp", 1))),
            "speed": max(1, int(stats.get("speed", 8))),
        }
