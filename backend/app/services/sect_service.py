"""
宗门应用服务（M7 L1）：拜入 / 自建 / 任务 / 商店 / 魂灯 / 兑宠。

服务端权威；贡献与入园只在本层写库。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time_utils import now_utc
from app.db.models import Avatar, Character, User
from app.db.models.sect import (
    Sect,
    SectContributionLedger,
    SectMember,
    SectQuestProgress,
)
from app.domain.sect_rules import (
    can_create_sect,
    can_join_npc_sect,
    feature_label_zh,
    quest_assignee_allowed,
    role_label_zh,
    shop_item_visible,
    species_allowed_for_exchange,
    unlocked_features_for_founder_realm,
    validate_sect_name,
)
from app.schemas.common import AppError
from app.services.play_gate import PlayGate
from app.services.realm_config import get_game_config, get_major_realm

logger = logging.getLogger(__name__)


def require_sect_system_enabled() -> None:
    """
    宗门总开关闸。

    Raises:
        AppError: ``40171`` 风格关闭时用 ``40000``+中文；对齐设计用设施闸优先。
    """
    settings = get_settings()
    if not bool(getattr(settings, "sect_system_enabled", True)):
        raise AppError(code=40000, message="宗门系统未开放", http_status=403)
    facilities = get_game_config().sects.facilities
    hall = facilities.get("sect_hall") or {}
    if hall and not bool(hall.get("enabled", True)):
        raise AppError(
            code=40000,
            message=str(hall.get("note") or "宗门大厅未开放"),
            http_status=403,
        )


class SectService:
    """宗门用例编排。"""

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: 异步 SQLAlchemy 会话。
        """
        self._session = session
        self._gate = PlayGate(session)

    def _cfg(self):
        """当前 SectsConfig 快照。"""
        return get_game_config().sects

    def _realm_chain(self) -> list[str]:
        """大境界有序键（配置表顺序）。"""
        return list(get_game_config().realms.keys())

    async def enrich_sect_summary(self, character: Character) -> dict[str, Any] | None:
        """
        挂到 CharacterPublic.sect 的摘要；散修返回 wanderer 占位。

        Args:
            character: 角色。

        Returns:
            dict | None: 摘要；系统关闭时仍返回散修说明。
        """
        cfg = self._cfg()
        wanderer = {
            "in_sect": False,
            "sect_id": None,
            "name": None,
            "role": None,
            "role_label_zh": None,
            "contrib": 0,
            "kind": None,
            "template_id": None,
            "idle_bonus_vs_wanderer": 1.0,
            "unlocked_features": [],
            "unlocked_features_zh": [],
            "hint_zh": (
                f"散修可通关；入宗挂机修为占位乘区约 ×{cfg.idle_bonus_vs_wanderer:.2f}"
            ),
        }
        if character.sect_id is None:
            return wanderer
        sect = await self._session.get(Sect, int(character.sect_id))
        if sect is None:
            return wanderer
        member = await self._get_member(character.id)
        if member is None:
            return wanderer
        features = await self._unlocked_features_for_sect(sect)
        bonus = float(cfg.idle_bonus_vs_wanderer)
        if sect.kind == "npc" and sect.template_id:
            npc = cfg.npc_sects.get(str(sect.template_id)) or {}
            bonus = float(npc.get("idle_bonus_vs_wanderer") or bonus)
        return {
            "in_sect": True,
            "sect_id": sect.id,
            "name": sect.name,
            "role": member.role,
            "role_label_zh": role_label_zh(
                getattr(member, "rank", None) or member.role,
            ),
            "rank": getattr(member, "rank", None) or member.role,
            "rank_label_zh": role_label_zh(
                getattr(member, "rank", None) or member.role,
            ),
            "contrib": int(member.contribution),
            "kind": sect.kind,
            "template_id": sect.template_id,
            "motto": sect.motto,
            "grade": getattr(sect, "grade", None) or "hut",
            "specialty": getattr(sect, "specialty", None),
            "idle_bonus_vs_wanderer": bonus,
            "unlocked_features": features,
            "unlocked_features_zh": [feature_label_zh(f) for f in features],
            "hint_zh": f"入宗相对散修挂机修为占位 ×{bonus:.2f}",
        }

    async def get_me(self, user: User) -> dict[str, Any]:
        """
        我的宗门面板。

        Args:
            user: 当前用户。

        Returns:
            dict: me 摘要 + 设施闸。
        """
        require_sect_system_enabled()
        character = await self._gate.require_character(user)
        summary = await self.enrich_sect_summary(character)
        return {
            "sect": summary,
            "facilities": {
                fid: {
                    "enabled": bool(body.get("enabled")),
                    "note": str(body.get("note") or ""),
                }
                for fid, body in self._cfg().facilities.items()
            },
            "create_cost_spirit_stones": int(self._cfg().create_cost_spirit_stones),
            "character": await self._character_public(character),
        }

    async def list_npc(self, user: User) -> dict[str, Any]:
        """
        NPC 宗门目录（含是否已达门槛）。

        Args:
            user: 当前用户。

        Returns:
            dict: items 列表。
        """
        require_sect_system_enabled()
        character = await self._gate.require_character(user)
        items: list[dict[str, Any]] = []
        for template_id, body in self._cfg().npc_sects.items():
            min_realm = str(body.get("join_min_realm") or "")
            ok, reason = can_join_npc_sect(
                character_major_realm=str(character.major_realm),
                join_min_realm=min_realm,
            )
            major = get_major_realm(min_realm) if min_realm else None
            items.append(
                {
                    "template_id": template_id,
                    "label_zh": str(body.get("label_zh") or template_id),
                    "summary": str(body.get("summary") or ""),
                    "motto": str(body.get("motto") or ""),
                    "join_min_realm": min_realm,
                    "join_min_realm_label_zh": major.name if major else min_realm,
                    "join_cost_spirit_stones": int(body.get("join_cost_spirit_stones") or 0),
                    "idle_bonus_vs_wanderer": float(
                        body.get("idle_bonus_vs_wanderer")
                        or self._cfg().idle_bonus_vs_wanderer,
                    ),
                    "can_join": ok and character.sect_id is None,
                    "block_reason_zh": (
                        "已有宗门" if character.sect_id is not None else reason
                    ),
                },
            )
        return {"items": items, "wanderer": character.sect_id is None}

    async def join(self, user: User, *, template_id: str) -> dict[str, Any]:
        """
        拜入 NPC 宗门。

        Args:
            user: 当前用户。
            template_id: NPC 模板 id。

        Returns:
            dict: 结果摘要。

        Raises:
            AppError: 已入宗 / 门槛 / 灵石 / 未知模板。
        """
        require_sect_system_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        if character.sect_id is not None:
            raise AppError(code=40101, message="已有宗门，不可重复拜入", http_status=400)
        cfg = self._cfg()
        npc = cfg.npc_sects.get(str(template_id))
        if not npc:
            raise AppError(code=40000, message=f"未知 NPC 宗门：{template_id}", http_status=400)
        ok, reason = can_join_npc_sect(
            character_major_realm=str(character.major_realm),
            join_min_realm=str(npc.get("join_min_realm") or ""),
        )
        if not ok:
            raise AppError(code=40000, message=reason or "不可拜入", http_status=400)
        cost = int(npc.get("join_cost_spirit_stones") or 0)
        if int(character.spirit_stones) < cost:
            raise AppError(
                code=40102,
                message=f"灵石不足：拜入需 {cost} 灵石",
                http_status=400,
            )
        if cost > 0:
            character.spirit_stones = int(character.spirit_stones) - cost

        sect = await self._ensure_npc_sect_row(str(template_id), npc)
        member = SectMember(
            sect_id=sect.id,
            character_id=character.id,
            role="member",
            rank="laborer",
            contribution=0,
        )
        self._session.add(member)
        character.sect_id = sect.id
        await self._session.flush()
        # 入宗赠贡献占位，便于商店/兑宠联调
        await self._apply_contribution(
            member,
            delta=10,
            reason="join_bonus",
            note_zh="拜入赠礼贡献",
        )
        await self._session.flush()
        logger.info(
            "sect join character_id=%s sect_id=%s template=%s",
            character.id,
            sect.id,
            template_id,
        )
        return {
            "message": f"已拜入「{sect.name}」",
            "sect": await self.enrich_sect_summary(character),
            "character": await self._character_public(character),
        }

    async def create(
        self,
        user: User,
        *,
        name: str,
        motto: str | None,
        specialty: str | None = None,
    ) -> dict[str, Any]:
        """
        自建宗门（D2/D3：有钱即可；创建者=创派祖师+掌门；须选专精）。

        Args:
            user: 当前用户。
            name: 宗门名。
            motto: 箴言。
            specialty: 专精键（M7-V+ 必选）。

        Returns:
            dict: 结果。
        """
        require_sect_system_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        if character.sect_id is not None:
            raise AppError(code=40101, message="已有宗门，不可再建", http_status=400)
        cfg = self._cfg()
        ok_name, name_reason = validate_sect_name(name, max_len=int(cfg.max_name_len))
        if not ok_name:
            raise AppError(code=40000, message=name_reason or "宗门名非法", http_status=400)
        cleaned_name = name.strip()
        cleaned_motto = (motto or "").strip() or None
        if cleaned_motto and len(cleaned_motto) > int(cfg.max_motto_len):
            raise AppError(
                code=40000,
                message=f"箴言过长（最多 {cfg.max_motto_len} 字）",
                http_status=400,
            )
        spec = (specialty or "").strip()
        if not spec or spec not in cfg.specialties:
            raise AppError(code=40000, message="建宗须选择有效专精", http_status=400)
        ok_cost, cost_reason = can_create_sect(
            spirit_stones=int(character.spirit_stones),
            create_cost=int(cfg.create_cost_spirit_stones),
        )
        if not ok_cost:
            raise AppError(code=40102, message=cost_reason or "灵石不足", http_status=400)

        # 重名拒绝
        existing = (
            await self._session.execute(select(Sect).where(Sect.name == cleaned_name))
        ).scalar_one_or_none()
        if existing is not None:
            raise AppError(code=40000, message="宗门名已被占用", http_status=400)

        character.spirit_stones = int(character.spirit_stones) - int(
            cfg.create_cost_spirit_stones,
        )
        sect = Sect(
            kind="player",
            template_id=None,
            name=cleaned_name,
            motto=cleaned_motto,
            grade="hut",
            specialty=spec,
            founder_character_id=character.id,
            leader_character_id=character.id,
        )
        self._session.add(sect)
        await self._session.flush()
        # 初始设施
        from app.db.models.sect import SectFacility

        for fid, fdef in cfg.facility_defs.items():
            self._session.add(
                SectFacility(
                    sect_id=sect.id,
                    facility_id=str(fid),
                    level=int(fdef.get("initial_level") or 1),
                ),
            )
        member = SectMember(
            sect_id=sect.id,
            character_id=character.id,
            role="founder",
            rank="founder",
            contribution=0,
        )
        self._session.add(member)
        character.sect_id = sect.id
        await self._session.flush()
        await self._apply_contribution(
            member,
            delta=50,
            reason="create_bonus",
            note_zh="建宗创始贡献",
        )
        await self._session.flush()
        logger.info(
            "sect create character_id=%s sect_id=%s name=%s specialty=%s",
            character.id,
            sect.id,
            cleaned_name,
            spec,
        )
        return {
            "message": f"已创建宗门「{cleaned_name}」",
            "sect": await self.enrich_sect_summary(character),
            "character": await self._character_public(character),
        }

    async def list_quests(self, user: User) -> dict[str, Any]:
        """
        可接/进行中任务列表。

        Args:
            user: 当前用户。

        Returns:
            dict: quests。
        """
        require_sect_system_enabled()
        self._require_facility("sect_tasks")
        character = await self._gate.require_character(user)
        if character.sect_id is None:
            raise AppError(code=40101, message="未入宗，不可查看宗门任务", http_status=400)
        sect = await self._session.get(Sect, int(character.sect_id))
        if sect is None:
            raise AppError(code=40101, message="宗门不存在", http_status=400)
        features = set(await self._unlocked_features_for_sect(sect))
        if "quests_basic" not in features:
            raise AppError(
                code=40103,
                message="祖师未解锁基础宗门任务",
                http_status=400,
            )
        progress_rows = (
            await self._session.execute(
                select(SectQuestProgress).where(
                    SectQuestProgress.character_id == character.id,
                    SectQuestProgress.status == "accepted",
                ),
            )
        ).scalars().all()
        accepted_map = {(r.quest_id, r.assignee): r for r in progress_rows}
        has_avatar = (
            await self._session.execute(
                select(Avatar.id).where(Avatar.character_id == character.id).limit(1),
            )
        ).scalar_one_or_none() is not None
        items: list[dict[str, Any]] = []
        for quest_id, body in self._cfg().quests.items():
            require = str(body.get("require_feature") or "")
            if require and require not in features:
                continue
            modes = [str(m) for m in (body.get("assignee_modes") or ["body"])]
            for assignee in modes:
                key = (quest_id, assignee)
                row = accepted_map.get(key)
                block = None
                if assignee == "avatar" and not has_avatar:
                    block = "尚未凝练化身，不可接化身任务"
                items.append(
                    {
                        "quest_id": quest_id,
                        "label_zh": str(body.get("label_zh") or quest_id),
                        "summary": str(body.get("summary") or ""),
                        "assignee": assignee,
                        "assignee_label_zh": "化身" if assignee == "avatar" else "本体",
                        "reward_contribution": int(body.get("reward_contribution") or 0),
                        "status": row.status if row else "available",
                        "can_accept": row is None and block is None,
                        "can_complete": row is not None and row.status == "accepted",
                        "block_reason_zh": block,
                    },
                )
        return {"items": items, "has_avatar": has_avatar}

    async def accept_quest(
        self,
        user: User,
        *,
        quest_id: str,
        assignee: str,
    ) -> dict[str, Any]:
        """
        接取任务（化身无需本体在场 · M4-D06）。

        Args:
            user: 当前用户。
            quest_id: 任务 id。
            assignee: body / avatar。

        Returns:
            dict: 结果。
        """
        require_sect_system_enabled()
        self._require_facility("sect_tasks")
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        member, sect, quest = await self._require_quest_context(
            character,
            quest_id=quest_id,
            assignee=assignee,
        )
        if not quest_assignee_allowed(quest, assignee):
            raise AppError(code=40000, message="该任务不支持此接取方", http_status=400)
        if assignee == "avatar":
            has_avatar = (
                await self._session.execute(
                    select(Avatar.id).where(Avatar.character_id == character.id).limit(1),
                )
            ).scalar_one_or_none()
            if has_avatar is None:
                raise AppError(code=40000, message="尚未凝练化身", http_status=400)
        existing = (
            await self._session.execute(
                select(SectQuestProgress).where(
                    SectQuestProgress.character_id == character.id,
                    SectQuestProgress.quest_id == quest_id,
                    SectQuestProgress.assignee == assignee,
                    SectQuestProgress.status == "accepted",
                ),
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise AppError(code=40000, message="任务进行中，请先完成", http_status=400)
        # 清理同键已完成行，便于再次接取
        old_done = (
            await self._session.execute(
                select(SectQuestProgress).where(
                    SectQuestProgress.character_id == character.id,
                    SectQuestProgress.quest_id == quest_id,
                    SectQuestProgress.assignee == assignee,
                    SectQuestProgress.status == "completed",
                ),
            )
        ).scalar_one_or_none()
        if old_done is not None:
            await self._session.delete(old_done)
            await self._session.flush()
        row = SectQuestProgress(
            character_id=character.id,
            sect_id=sect.id,
            quest_id=quest_id,
            assignee=assignee,
            status="accepted",
        )
        self._session.add(row)
        await self._session.flush()
        logger.info(
            "sect quest accept character_id=%s quest=%s assignee=%s",
            character.id,
            quest_id,
            assignee,
        )
        return {
            "message": f"已接取「{quest.get('label_zh') or quest_id}」",
            "quest_id": quest_id,
            "assignee": assignee,
            "sect": await self.enrich_sect_summary(character),
        }

    async def complete_quest(
        self,
        user: User,
        *,
        quest_id: str,
        assignee: str,
    ) -> dict[str, Any]:
        """
        完成任务并发贡献（占位：接取后即可交，无战斗检定）。

        Args:
            user: 当前用户。
            quest_id: 任务 id。
            assignee: body / avatar。

        Returns:
            dict: 结果。
        """
        require_sect_system_enabled()
        self._require_facility("sect_tasks")
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        member, _sect, quest = await self._require_quest_context(
            character,
            quest_id=quest_id,
            assignee=assignee,
        )
        row = (
            await self._session.execute(
                select(SectQuestProgress).where(
                    SectQuestProgress.character_id == character.id,
                    SectQuestProgress.quest_id == quest_id,
                    SectQuestProgress.assignee == assignee,
                    SectQuestProgress.status == "accepted",
                ),
            )
        ).scalar_one_or_none()
        if row is None:
            raise AppError(code=40000, message="没有进行中的该任务", http_status=400)
        reward = int(quest.get("reward_contribution") or 0)
        row.status = "completed"
        row.completed_at = now_utc()
        await self._apply_contribution(
            member,
            delta=reward,
            reason="quest_reward",
            note_zh=f"任务奖励：{quest.get('label_zh') or quest_id}",
        )
        await self._session.flush()
        logger.info(
            "sect quest complete character_id=%s quest=%s reward=%s",
            character.id,
            quest_id,
            reward,
        )
        return {
            "message": f"任务完成，贡献 +{reward}",
            "reward_contribution": reward,
            "sect": await self.enrich_sect_summary(character),
            "character": await self._character_public(character),
        }

    async def list_shop(self, user: User) -> dict[str, Any]:
        """
        贡献商店列表。

        Args:
            user: 当前用户。

        Returns:
            dict: items。
        """
        require_sect_system_enabled()
        self._require_facility("sect_shop")
        character = await self._gate.require_character(user)
        if character.sect_id is None:
            raise AppError(code=40101, message="未入宗，不可使用宗门商店", http_status=400)
        sect = await self._session.get(Sect, int(character.sect_id))
        if sect is None:
            raise AppError(code=40101, message="宗门不存在", http_status=400)
        features = set(await self._unlocked_features_for_sect(sect))
        if "shop_basic" not in features:
            raise AppError(code=40103, message="祖师未解锁基础贡献商店", http_status=400)
        member = await self._get_member(character.id)
        items: list[dict[str, Any]] = []
        for item_id, body in self._cfg().shop_items.items():
            if not shop_item_visible(body, features):
                continue
            cost = int(body.get("cost_contribution") or 0)
            items.append(
                {
                    "item_id": item_id,
                    "label_zh": str(body.get("label_zh") or item_id),
                    "summary": str(body.get("summary") or ""),
                    "cost_contribution": cost,
                    "reward_spirit_stones": int(body.get("reward_spirit_stones") or 0),
                    "can_buy": member is not None and int(member.contribution) >= cost,
                },
            )
        return {
            "items": items,
            "contrib": int(member.contribution) if member else 0,
        }

    async def buy_shop(self, user: User, *, item_id: str) -> dict[str, Any]:
        """
        购买贡献商店条目。

        Args:
            user: 当前用户。
            item_id: 条目 id。

        Returns:
            dict: 结果。
        """
        require_sect_system_enabled()
        self._require_facility("sect_shop")
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        if character.sect_id is None:
            raise AppError(code=40101, message="未入宗", http_status=400)
        sect = await self._session.get(Sect, int(character.sect_id))
        if sect is None:
            raise AppError(code=40101, message="宗门不存在", http_status=400)
        features = set(await self._unlocked_features_for_sect(sect))
        body = self._cfg().shop_items.get(str(item_id))
        if not body or not shop_item_visible(body, features):
            raise AppError(code=40000, message="商品不存在或未解锁", http_status=400)
        member = await self._get_member(character.id)
        if member is None:
            raise AppError(code=40101, message="非本宗成员", http_status=400)
        cost = int(body.get("cost_contribution") or 0)
        if int(member.contribution) < cost:
            raise AppError(code=40000, message="贡献不足", http_status=400)
        await self._apply_contribution(
            member,
            delta=-cost,
            reason="shop_buy",
            note_zh=f"商店兑换：{body.get('label_zh') or item_id}",
        )
        reward_stones = int(body.get("reward_spirit_stones") or 0)
        if reward_stones > 0:
            character.spirit_stones = int(character.spirit_stones) + reward_stones
        await self._session.flush()
        return {
            "message": f"已兑换「{body.get('label_zh') or item_id}」",
            "reward_spirit_stones": reward_stones,
            "sect": await self.enrich_sect_summary(character),
            "character": await self._character_public(character),
        }

    async def list_soul_lamps(self, user: User) -> dict[str, Any]:
        """
        魂灯列表：本宗弟子状态摘要（散修无入口）。

        Args:
            user: 当前用户。

        Returns:
            dict: lamps。
        """
        require_sect_system_enabled()
        character = await self._gate.require_character(user)
        if character.sect_id is None:
            raise AppError(code=40101, message="散修无魂灯", http_status=400)
        members = (
            await self._session.execute(
                select(SectMember).where(SectMember.sect_id == int(character.sect_id)),
            )
        ).scalars().all()
        lamps: list[dict[str, Any]] = []
        for mem in members:
            ch = await self._session.get(Character, mem.character_id)
            if ch is None:
                continue
            lamps.append(
                {
                    "character_id": ch.id,
                    "name": ch.name,
                    "role": mem.role,
                    "role_label_zh": role_label_zh(mem.role),
                    "status": ch.status,
                    "status_label_zh": _status_label_zh(ch.status),
                    "major_realm": ch.major_realm,
                    "major_realm_label_zh": (
                        get_major_realm(ch.major_realm).name
                        if get_major_realm(ch.major_realm)
                        else ch.major_realm
                    ),
                    "awaiting_ferry": ch.status == "awaiting_ferry",
                    "region_stub": "same_region",  # M7 同图桩；真坐标 → M9
                },
            )
        return {"items": lamps, "count": len(lamps)}

    async def exchange_pet(self, user: User, *, species_id: str) -> dict[str, Any]:
        """
        宗门兑宠：扣贡献 → spawn_owned_pet(acquire_tag=sect_exchange)。

        Args:
            user: 当前用户。
            species_id: 物种 id。

        Returns:
            dict: 结果。
        """
        require_sect_system_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        if character.sect_id is None:
            raise AppError(code=40101, message="未入宗，不可兑宠", http_status=400)
        sect = await self._session.get(Sect, int(character.sect_id))
        if sect is None:
            raise AppError(code=40101, message="宗门不存在", http_status=400)
        features = set(await self._unlocked_features_for_sect(sect))
        if "pet_exchange" not in features:
            raise AppError(
                code=40103,
                message="祖师未达金丹档，宗门兑宠未开",
                http_status=400,
            )
        ex = self._cfg().sect_exchange
        if not bool(ex.get("enabled", True)):
            raise AppError(code=40000, message="宗门兑宠未开放", http_status=403)
        whitelist = [str(x) for x in (ex.get("whitelist_species") or [])]
        if not species_allowed_for_exchange(species_id, whitelist):
            raise AppError(code=40000, message="该物种不在兑宠白名单", http_status=400)
        pets_cfg = get_game_config().pets
        if species_id not in pets_cfg.species:
            raise AppError(code=40000, message=f"未知物种：{species_id}", http_status=400)
        species = pets_cfg.species[species_id]
        if "sect_exchange" not in species.acquire_tags:
            raise AppError(
                code=40000,
                message="该物种未开放宗门兑换途径",
                http_status=400,
            )
        member = await self._get_member(character.id)
        if member is None:
            raise AppError(code=40101, message="非本宗成员", http_status=400)
        cost = int(ex.get("cost_contribution") or 0)
        if int(member.contribution) < cost:
            raise AppError(code=40000, message="贡献不足，无法兑宠", http_status=400)
        await self._apply_contribution(
            member,
            delta=-cost,
            reason="pet_exchange",
            note_zh=f"兑宠：{species.name}",
        )
        from app.services.pet_service import PetService

        grade = int(ex.get("grade") or 1)
        spawned = await PetService(self._session).spawn_owned_pet(
            character,
            species_id=species_id,
            grade=grade,
            acquire_tag="sect_exchange",
        )
        await self._session.flush()
        logger.info(
            "sect pet exchange character_id=%s species=%s cost=%s",
            character.id,
            species_id,
            cost,
        )
        return {
            "message": f"已兑换灵宠「{species.name}」",
            "pet": spawned,
            "sect": await self.enrich_sect_summary(character),
            "character": await self._character_public(character),
        }

    async def exchange_catalog(self, user: User) -> dict[str, Any]:
        """
        兑宠目录（白名单 + 费用）。

        Args:
            user: 当前用户。

        Returns:
            dict: catalog。
        """
        require_sect_system_enabled()
        character = await self._gate.require_character(user)
        ex = self._cfg().sect_exchange
        pets_cfg = get_game_config().pets
        items: list[dict[str, Any]] = []
        for sid in ex.get("whitelist_species") or []:
            sp = pets_cfg.species.get(str(sid))
            items.append(
                {
                    "species_id": str(sid),
                    "name": sp.name if sp else str(sid),
                    "cost_contribution": int(ex.get("cost_contribution") or 0),
                    "grade": int(ex.get("grade") or 1),
                    "enabled": bool(ex.get("enabled", True)) and sp is not None,
                },
            )
        member = await self._get_member(character.id) if character.sect_id else None
        return {
            "enabled": bool(ex.get("enabled", True)),
            "items": items,
            "contrib": int(member.contribution) if member else 0,
            "in_sect": character.sect_id is not None,
        }

    async def zero_contribution_on_reincarnation(self, character_id: int) -> dict[str, Any]:
        """
        轮回归零本宗贡献（D4）；由 ReincarnationService 同事务调用。

        Args:
            character_id: 角色 id。

        Returns:
            dict: 清零摘要。
        """
        cfg = self._cfg()
        if not bool(cfg.contribution_zero_on_reincarnation):
            return {"zeroed": False, "reason": "config_disabled"}
        member = await self._get_member(character_id)
        if member is None:
            return {"zeroed": False, "reason": "not_in_sect"}
        before = int(member.contribution)
        if before == 0:
            return {"zeroed": True, "before": 0, "after": 0}
        await self._apply_contribution(
            member,
            delta=-before,
            reason="reincarnation_zero",
            note_zh="轮回归零宗门贡献",
        )
        await self._session.flush()
        logger.info(
            "sect contrib zero on reincarnation character_id=%s before=%s",
            character_id,
            before,
        )
        return {"zeroed": True, "before": before, "after": 0}

    # ----- helpers -----

    def _require_facility(self, facility_id: str) -> None:
        """设施子闸。"""
        body = self._cfg().facilities.get(facility_id) or {}
        if body and not bool(body.get("enabled", True)):
            raise AppError(
                code=40000,
                message=str(body.get("note") or f"{facility_id} 未开放"),
                http_status=403,
            )

    async def _get_member(self, character_id: int) -> SectMember | None:
        """按角色取成员行。"""
        return (
            await self._session.execute(
                select(SectMember).where(SectMember.character_id == character_id),
            )
        ).scalar_one_or_none()

    async def _ensure_npc_sect_row(self, template_id: str, npc: dict[str, Any]) -> Sect:
        """惰性创建 NPC 宗门行（每模板一行）。"""
        existing = (
            await self._session.execute(
                select(Sect).where(
                    Sect.kind == "npc",
                    Sect.template_id == template_id,
                ),
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        name = str(npc.get("label_zh") or template_id)
        # 若重名（极端），加后缀
        clash = (
            await self._session.execute(select(Sect).where(Sect.name == name))
        ).scalar_one_or_none()
        if clash is not None:
            name = f"{name}·{template_id}"
        sect = Sect(
            kind="npc",
            template_id=template_id,
            name=name,
            motto=str(npc.get("motto") or "") or None,
            grade=str(npc.get("grade") or "hut"),
            specialty=str(npc.get("specialty") or "") or None,
            founder_character_id=None,
            leader_character_id=None,
        )
        self._session.add(sect)
        await self._session.flush()
        # NPC 初始设施
        from app.db.models.sect import SectFacility

        for fid, fdef in self._cfg().facility_defs.items():
            self._session.add(
                SectFacility(
                    sect_id=sect.id,
                    facility_id=str(fid),
                    level=int(fdef.get("initial_level") or 1),
                ),
            )
        await self._session.flush()
        return sect

    async def _unlocked_features_for_sect(self, sect: Sect) -> list[str]:
        """按祖师境界（或 NPC 默认金丹档）解析功能。"""
        cfg = self._cfg()
        if sect.kind == "npc":
            # NPC：取模板 join_min_realm 作为「祖师」等效档，至少 jindan 开兑宠
            template = cfg.npc_sects.get(str(sect.template_id) or "") or {}
            founder_realm = str(template.get("join_min_realm") or "jindan")
            # 抬到至少金丹以开放兑宠样本
            chain = self._realm_chain()
            if "jindan" in chain and meets_or_above(founder_realm, "jindan", chain):
                founder_realm = max_realm(founder_realm, "jindan", chain)
            else:
                founder_realm = "jindan" if "jindan" in chain else founder_realm
        else:
            founder_id = sect.founder_character_id
            if founder_id is None:
                return list(
                    unlocked_features_for_founder_realm(
                        "body_tempering",
                        cfg.features_by_founder_realm,
                        realm_chain=self._realm_chain(),
                    ),
                )
            founder = await self._session.get(Character, int(founder_id))
            founder_realm = (
                str(founder.major_realm) if founder else "body_tempering"
            )
        return unlocked_features_for_founder_realm(
            founder_realm,
            cfg.features_by_founder_realm,
            realm_chain=self._realm_chain(),
        )

    async def _require_quest_context(
        self,
        character: Character,
        *,
        quest_id: str,
        assignee: str,
    ) -> tuple[SectMember, Sect, dict[str, Any]]:
        """任务接交共用校验。"""
        if character.sect_id is None:
            raise AppError(code=40101, message="未入宗", http_status=400)
        sect = await self._session.get(Sect, int(character.sect_id))
        if sect is None:
            raise AppError(code=40101, message="宗门不存在", http_status=400)
        features = set(await self._unlocked_features_for_sect(sect))
        if "quests_basic" not in features:
            raise AppError(code=40103, message="祖师未解锁宗门任务", http_status=400)
        quest = self._cfg().quests.get(str(quest_id))
        if not quest:
            raise AppError(code=40000, message=f"未知任务：{quest_id}", http_status=400)
        require = str(quest.get("require_feature") or "")
        if require and require not in features:
            raise AppError(code=40103, message="任务功能未解锁", http_status=400)
        member = await self._get_member(character.id)
        if member is None:
            raise AppError(code=40101, message="非本宗成员", http_status=400)
        _ = assignee  # 调用方再验
        return member, sect, quest

    async def _apply_contribution(
        self,
        member: SectMember,
        *,
        delta: int,
        reason: str,
        note_zh: str | None,
    ) -> None:
        """写贡献余额 + 流水。"""
        new_balance = int(member.contribution) + int(delta)
        if new_balance < 0:
            raise AppError(code=40000, message="贡献不足", http_status=400)
        member.contribution = new_balance
        self._session.add(
            SectContributionLedger(
                sect_id=member.sect_id,
                character_id=member.character_id,
                delta=int(delta),
                reason=reason,
                note_zh=note_zh,
                balance_after=new_balance,
            ),
        )

    async def _character_public(self, character: Character) -> dict[str, Any]:
        """刷新角色公开面板。"""
        from app.services.character_service import CharacterService

        # flush 后 onupdate 可能使 updated_at 过期；先 refresh 避免 sync lazy load
        await self._session.refresh(character)
        return (
            await CharacterService(self._session).enrich_public(character)
        ).model_dump(mode="json")


def _status_label_zh(status: str) -> str:
    """角色状态中文。"""
    mapping = {
        "normal": "正常",
        "breaking_through": "突破中",
        "tribulation": "渡劫中",
        "awaiting_ferry": "待引渡",
        "reincarnating": "轮回中",
    }
    return mapping.get(status, status)


def meets_or_above(current: str, required: str, chain: list[str]) -> bool:
    """境界比较辅助。"""
    from app.domain.reincarnation_rules import meets_min_major_realm

    return meets_min_major_realm(current, required)


def max_realm(a: str, b: str, chain: list[str]) -> str:
    """取链上较高境界。"""
    try:
        return a if chain.index(a) >= chain.index(b) else b
    except ValueError:
        return a
