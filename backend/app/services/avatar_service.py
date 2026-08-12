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
from app.domain.m4_constants import AvatarFeature, AvatarStatus, IdleDirection
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
        solo_ok = cap_idx.is_unlocked(character.major_realm, AvatarFeature.SOLO_BATTLE)
        payload["battle_modes"] = {
            "with_main": True,
            "solo_battle": solo_ok,
            "solo_battle_hint": (
                None if solo_ok else "化神后方可化身独战（编成可不含本体）"
            ),
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
        return self._base_panel(avatar)

    async def get_me(self, character: Character, now: datetime | None = None) -> dict[str, Any] | None:
        """化身完整面板；未凝练返回 None。"""
        avatar = await self.get_avatar_row(character.id)
        if avatar is None:
            return None
        return self._panel_dict(avatar, character, now=now, full=True)

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
            has_avatar=existing is not None,
            unlock_major=avatar_cfg.unlock_major_realm,
            max_avatars=avatar_cfg.max_avatars,
            spirit_stone_cost=avatar_cfg.condense_spirit_stone_cost,
            realms=get_game_config().realms,
        )
        return {
            "major_realm": character.major_realm,
            "features": features,
            "unlock_preview": preview,
            "condense": condense,
        }

    # ------------------------------------------------------------------
    # 用例
    # ------------------------------------------------------------------

    async def condense(
        self,
        user: User,
        *,
        skip_cost: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        凝练化身（PlayGate 清 pending + 双线程 settle 先行）。

        异常:
            AppError: 40050/40051/灵石不足。
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

        cost = avatar_cfg.condense_spirit_stone_cost
        if not skip_cost and int(character.spirit_stones) < cost:
            raise AppError(code=40000, message="灵石不足以凝练化身", http_status=400)
        if not skip_cost:
            character.spirit_stones = int(character.spirit_stones) - cost

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
        avatar = Avatar(
            character_id=character.id,
            name=f"{character.name}化身",
            status=AvatarStatus.IDLE,
            idle_direction=IdleDirection.NONE,
            cultivation_points=int(character.cultivation_points),
            body_tempering_points=0,
            crafting_exp=0,
            base_stats_json=json.dumps(stats, ensure_ascii=False),
            stamina=initial_stamina,
            daily_actions_used=0,
            daily_actions_day="",
            stamina_recovered_at=created_at if initial_stamina > 0 else None,
            last_settled_at=created_at,
            created_at=created_at,
        )
        self._session.add(avatar)
        await self._session.flush()
        await self._session.refresh(avatar)
        logger.info("avatar condensed character_id=%s avatar_id=%s", character.id, avatar.id)
        return self._panel_dict(avatar, character, now=created_at)

    async def set_idle(
        self,
        user: User,
        direction: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """设置化身挂机方向（校验 feature idle_*）。"""
        require_avatar_enabled()
        character, _ = await self._gate.prepare_for_play(user, now=now)
        avatar = await self.get_avatar_row(character.id)
        if avatar is None:
            raise AppError(code=40051, message="尚未凝练化身", http_status=400)

        if not is_allowed_avatar_idle_direction(direction):
            raise AppError(code=40000, message="无效的挂机方向", http_status=400)

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

        avatar.idle_direction = direction
        await self._session.flush()
        return self._panel_dict(avatar, character, now=now)

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
        """神识读数。"""
        deploy_units = units or []
        av_count, pet_count, pet_costs = DivineSenseService.count_deployed_from_units(
            deploy_units,
        )
        return DivineSenseService.snapshot_for_character(
            character,
            avatar_deploy_count=av_count,
            pet_deploy_count=pet_count,
            pet_costs=pet_costs or None,
        )

    @staticmethod
    def avatar_combat_stats(avatar: Avatar) -> dict[str, int]:
        """从化身快照 JSON 读取战斗面板。"""
        stats = json.loads(avatar.base_stats_json or "{}")
        return {
            "atk": max(1, int(stats.get("atk", 1))),
            "hp": max(1, int(stats.get("hp", 1))),
            "speed": max(1, int(stats.get("speed", 8))),
        }
