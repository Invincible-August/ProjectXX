"""
宗门设施应用服务（M7-V+）：藏宝阁 / 藏经阁 / 工坊 / 大阵 / 矿脉 / 灵药园。
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.inventory import ERR_BLUEPRINT_TYPE_MISMATCH, ItemType
from app.constants.technique import TECHNIQUE_SOURCE_SECT
from app.constants.technique_craft import CARD_MANUAL_ID, ERR_SCRIPTURE_DONATE
from app.core.time_utils import now_utc
from app.db.models import Character, User
from app.db.models.inventory_item import InventoryItem
from app.db.models.sect import (
    Sect,
    SectContributionLedger,
    SectCraftJob,
    SectDonationReview,
    SectFacility,
    SectFormationState,
    SectHerbPlot,
    SectMember,
    SectMineMiner,
    SectMineState,
    SectScriptureEntry,
    SectTreasuryItem,
    SectWorkshopBlueprint,
)
from app.domain.dice_rules import chance
from app.domain.game_day import game_day_number
from app.domain.sect_blueprint_rules import (
    blueprint_catalog_item_id,
    manual_kind_matches_workshop,
    recipe_branch_matches_workshop,
    workshop_manual_kind,
)
from app.domain.sect_org_rules import (
    council_action_allowed,
    deposit_type_forbidden,
    herb_plot_capacity,
    mine_max_miners,
    mine_pool_rate_per_hour,
    normalize_member_rank,
    treasury_page_allowed,
)
from app.schemas.common import AppError
from app.services.calendar_service import CalendarService
from app.services.inventory_service import InventoryService
from app.services.play_gate import PlayGate
from app.services.realm_config import get_game_config
from app.services.sect_org_service import SectOrgService
from app.services.sect_service import require_sect_system_enabled

logger = logging.getLogger(__name__)


class SectFacilityService:
    """宗门设施用例。"""

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: 异步会话。
        """
        self._session = session
        self._gate = PlayGate(session)
        self._org = SectOrgService(session)

    def _cfg(self):
        """SectsConfig。"""
        return get_game_config().sects

    def _game_day(self) -> int:
        """当前游戏日。"""
        snap = CalendarService().get_snapshot(now_utc())
        return game_day_number(
            now_utc(),
            epoch=str(get_game_config().calendar.epoch_utc),
            slot_seconds=int(snap.get("slot_seconds") or 60),
        )

    def _require_facility_gate(self, facility_id: str) -> None:
        """设施总闸。"""
        body = self._cfg().facilities.get(facility_id) or {}
        if body and not bool(body.get("enabled", True)):
            raise AppError(
                code=40000,
                message=str(body.get("note") or f"{facility_id} 未开放"),
                http_status=403,
            )

    async def _ctx(self, user: User) -> tuple[Character, Sect, SectMember]:
        """入宗上下文。"""
        return await self._org._require_member(user)

    def _rank(self, member: SectMember) -> str:
        """职位键。"""
        return normalize_member_rank(
            getattr(member, "rank", None),
            getattr(member, "role", None),
        )

    async def _facility_level(self, sect_id: int, facility_id: str) -> int:
        """单设施等级。"""
        sect = await self._session.get(Sect, sect_id)
        if sect is not None:
            await self._org.ensure_default_facilities(sect)
        row = (
            await self._session.execute(
                select(SectFacility).where(
                    SectFacility.sect_id == sect_id,
                    SectFacility.facility_id == facility_id,
                ),
            )
        ).scalar_one_or_none()
        return int(row.level) if row else 0

    async def _apply_contrib(
        self,
        member: SectMember,
        *,
        delta: int,
        reason: str,
        note_zh: str,
    ) -> None:
        """贡献增减。"""
        new_bal = int(member.contribution) + int(delta)
        if new_bal < 0:
            raise AppError(code=40102, message="贡献不足", http_status=400)
        member.contribution = new_bal
        self._session.add(
            SectContributionLedger(
                sect_id=member.sect_id,
                character_id=member.character_id,
                delta=int(delta),
                reason=reason,
                note_zh=note_zh,
                balance_after=new_bal,
            ),
        )

    # ----- 藏宝阁 -----

    async def treasury_list(self, user: User) -> dict[str, Any]:
        """藏宝阁目录 + 库存。"""
        require_sect_system_enabled()
        self._require_facility_gate("treasure_pavilion")
        _c, sect, member = await self._ctx(user)
        await self._org.ensure_sect_org_fields(sect)
        cfg = self._cfg()
        treasury = cfg.treasury or {}
        catalog = dict(treasury.get("catalog") or {})
        items = (
            await self._session.execute(
                select(SectTreasuryItem).where(SectTreasuryItem.sect_id == sect.id),
            )
        ).scalars().all()
        rank = self._rank(member)
        return {
            "catalog": [
                {
                    "item_key": kid,
                    "label_zh": str(body.get("label_zh") or kid),
                    "summary": str(body.get("summary") or ""),
                    "cost_contribution": int(body.get("cost_contribution") or 0),
                    "item_type": str(body.get("item_type") or "material"),
                    "region": str(body.get("region") or "common"),
                    "page": int(body.get("page") or 0),
                }
                for kid, body in catalog.items()
            ],
            "stock": [
                {
                    "id": row.id,
                    "page": row.page,
                    "item_type": row.item_type,
                    "item_id": row.item_id,
                    "quantity": row.quantity,
                    "label_zh": row.label_zh,
                }
                for row in items
            ],
            "my_treasury_page_max": int(
                (cfg.disciple_ranks.get(rank) or {}).get("treasury_page_max") or 0,
            ),
            "forbidden_deposit_types": list(treasury.get("forbidden_deposit_types") or []),
            "contrib": int(member.contribution),
        }

    async def treasury_exchange(self, user: User, *, item_key: str) -> dict[str, Any]:
        """贡献兑换基础物（记流水；真背包发放占位为灵石 0 + 贡献扣减）。"""
        require_sect_system_enabled()
        self._require_facility_gate("treasure_pavilion")
        _c, sect, member = await self._ctx(user)
        catalog = dict((self._cfg().treasury or {}).get("catalog") or {})
        body = catalog.get(item_key)
        if not body:
            raise AppError(code=40000, message="未知兑换物", http_status=400)
        cost = int(body.get("cost_contribution") or 0)
        await self._apply_contrib(
            member,
            delta=-cost,
            reason="treasury_exchange",
            note_zh=f"藏宝阁兑换 {body.get('label_zh') or item_key}",
        )
        await self._session.flush()
        return {
            "message": f"已兑换「{body.get('label_zh') or item_key}」",
            "item_key": item_key,
            "contrib": int(member.contribution),
        }

    async def treasury_deposit(
        self,
        user: User,
        *,
        page: int,
        item_type: str,
        item_id: str,
        quantity: int,
        label_zh: str | None = None,
    ) -> dict[str, Any]:
        """有权者放入藏宝阁（禁止图纸类型）。"""
        require_sect_system_enabled()
        self._require_facility_gate("treasure_pavilion")
        character, sect, member = await self._ctx(user)
        cfg = self._cfg()
        rank = self._rank(member)
        if not treasury_page_allowed(
            rank=rank,
            page=int(page),
            disciple_ranks=cfg.disciple_ranks,
        ):
            raise AppError(code=40000, message="无权向该页放入物品", http_status=403)
        forbidden = list((cfg.treasury or {}).get("forbidden_deposit_types") or [])
        inv_cfg = get_game_config().inventory
        defn = inv_cfg.items.get(str(item_id))
        resolved_type = str(defn.item_type) if defn is not None else str(item_type)
        resolved_kind = str(defn.manual_kind) if defn is not None and defn.manual_kind else None
        if deposit_type_forbidden(
            resolved_type,
            forbidden,
            manual_kind=resolved_kind,
        ):
            raise AppError(
                code=40000,
                message="不可将锻造/符箓/丹方/傀儡图纸放入藏宝阁",
                http_status=400,
            )
        if int(quantity) <= 0:
            raise AppError(code=40000, message="数量非法", http_status=400)
        row = SectTreasuryItem(
            sect_id=sect.id,
            page=int(page),
            item_type=resolved_type,
            item_id=str(item_id),
            quantity=int(quantity),
            label_zh=label_zh or (defn.name if defn else None),
            deposited_by=character.id,
        )
        self._session.add(row)
        await self._session.flush()
        return {"message": "已放入藏宝阁", "id": row.id, "page": row.page}

    async def treasury_allocate(
        self,
        user: User,
        *,
        stock_id: int,
        to_character_id: int,
        quantity: int,
    ) -> dict[str, Any]:
        """分配藏宝阁物品给弟子（扣库存；真背包占位）。"""
        require_sect_system_enabled()
        self._require_facility_gate("treasure_pavilion")
        _c, sect, member = await self._ctx(user)
        cfg = self._cfg()
        rank = self._rank(member)
        row = await self._session.get(SectTreasuryItem, int(stock_id))
        if row is None or row.sect_id != sect.id:
            raise AppError(code=40000, message="库存条目不存在", http_status=400)
        if not treasury_page_allowed(
            rank=rank,
            page=int(row.page),
            disciple_ranks=cfg.disciple_ranks,
        ):
            raise AppError(code=40000, message="无权分配该页物品", http_status=403)
        target = (
            await self._session.execute(
                select(SectMember).where(
                    SectMember.sect_id == sect.id,
                    SectMember.character_id == int(to_character_id),
                ),
            )
        ).scalar_one_or_none()
        if target is None:
            raise AppError(code=40000, message="目标非本宗门众", http_status=400)
        qty = int(quantity)
        if qty <= 0 or qty > int(row.quantity):
            raise AppError(code=40000, message="分配数量非法", http_status=400)
        row.quantity = int(row.quantity) - qty
        if row.quantity <= 0:
            await self._session.delete(row)
        await self._session.flush()
        return {
            "message": f"已分配给弟子（角色 {to_character_id}）×{qty}",
            "remaining": int(row.quantity) if row.quantity > 0 else 0,
        }

    # ----- 藏经阁 -----

    async def scripture_list(self, user: User) -> dict[str, Any]:
        """藏经阁目录与已收录。"""
        from app.services.technique_craft_service import TechniqueCraftService

        require_sect_system_enabled()
        self._require_facility_gate("scripture_pavilion")
        character, sect, member = await self._ctx(user)
        await self._org.ensure_sect_org_fields(sect)
        cfg = self._cfg()
        scripture = cfg.scripture or {}
        catalog = dict(scripture.get("catalog") or {})
        entries = (
            await self._session.execute(
                select(SectScriptureEntry).where(SectScriptureEntry.sect_id == sect.id),
            )
        ).scalars().all()
        stocked = {e.technique_id for e in entries}
        craft = TechniqueCraftService(self._session)
        entry_views: list[dict[str, Any]] = []
        for e in entries:
            origin = str(e.origin_technique_id or e.technique_id or "")
            owned = (
                await craft._already_learned_origin(character, origin) if origin else False
            )
            entry_views.append(
                {
                    "technique_id": e.technique_id,
                    "origin_technique_id": e.origin_technique_id,
                    "author_character_id": e.author_character_id,
                    "label_zh": e.label_zh,
                    "major_rank": e.major_rank,
                    "cost_contribution": int(e.cost_contribution),
                    "source": e.source,
                    "has_snapshot": bool(e.payload_json),
                    "owned": owned,
                    "specialty_tag": e.specialty_tag,
                }
            )
        return {
            "specialty": sect.specialty,
            "catalog": [
                {
                    "technique_id": tid,
                    "label_zh": str(body.get("label_zh") or tid),
                    "summary": str(body.get("summary") or ""),
                    "cost_contribution": int(body.get("cost_contribution") or 0),
                    "specialty_tags": list(body.get("specialty_tags") or []),
                    "owned": tid in stocked,
                }
                for tid, body in catalog.items()
            ],
            "entries": entry_views,
            "contrib": int(member.contribution),
        }

    async def scripture_exchange(self, user: User, *, technique_id: str) -> dict[str, Any]:
        """
        Exchange contribution for a scripture technique.

        Snapshot entries: learn first via ``learn_from_manual_meta`` (source=sect),
        then charge ``entry.cost_contribution``. Learn failures do not charge.
        Catalog / no-snapshot rows keep the placeholder grant behavior.
        """
        from app.services.technique_craft_service import TechniqueCraftService

        require_sect_system_enabled()
        self._require_facility_gate("scripture_pavilion")
        character, sect, member = await self._ctx(user)
        cfg = self._cfg()
        catalog = dict((cfg.scripture or {}).get("catalog") or {})
        body = catalog.get(technique_id)
        entry = (
            await self._session.execute(
                select(SectScriptureEntry).where(
                    SectScriptureEntry.sect_id == sect.id,
                    SectScriptureEntry.technique_id == technique_id,
                ),
            )
        ).scalar_one_or_none()

        if entry is not None and entry.payload_json:
            try:
                payload = json.loads(entry.payload_json or "{}")
            except json.JSONDecodeError:
                payload = {}
            try:
                stats = json.loads(entry.stats_json or "{}")
            except json.JSONDecodeError:
                stats = {}
            try:
                affix_ids = json.loads(entry.affix_ids_json or "[]")
            except json.JSONDecodeError:
                affix_ids = []
            if not isinstance(payload, dict):
                payload = {}
            if not isinstance(stats, dict):
                stats = {}
            if not isinstance(affix_ids, list):
                affix_ids = []
            meta = {
                "manual_kind": "technique",
                "origin_technique_id": str(
                    entry.origin_technique_id or entry.technique_id
                ),
                "author_character_id": entry.author_character_id,
                "label_zh": entry.label_zh,
                "major_rank": entry.major_rank,
                "payload": payload,
                "stats": stats,
                "affix_ids": affix_ids,
            }
            learned = await TechniqueCraftService(self._session).learn_from_manual_meta(
                character, meta, source=TECHNIQUE_SOURCE_SECT
            )
            cost = int(entry.cost_contribution)
            await self._apply_contrib(
                member,
                delta=-cost,
                reason="scripture_exchange",
                note_zh=f"藏经阁兑换 {entry.label_zh or technique_id}",
            )
            await self._session.flush()
            return {
                "message": "已学会宗门功法",
                "technique_id": str(learned["technique_id"]),
                "contrib": int(member.contribution),
            }

        if body is None and entry is None:
            raise AppError(code=40000, message="功法未收录", http_status=400)
        cost = int((body or {}).get("cost_contribution") or 60)
        await self._apply_contrib(
            member,
            delta=-cost,
            reason="scripture_exchange",
            note_zh=f"藏经阁兑换 {(body or {}).get('label_zh') or technique_id}",
        )
        await self._session.flush()
        return {
            "message": "已兑换功法（占位授予）",
            "technique_id": technique_id,
            "contrib": int(member.contribution),
        }

    async def scripture_donate(
        self,
        user: User,
        *,
        item_uid: str,
    ) -> dict[str, Any]:
        """
        Submit a printed technique manual for scripture-pavilion review.

        Consumes one ``tech_manual`` owned by the acting character. Only the
        snapshot author may donate. Does not grant contribution (approval does).
        An existing scripture entry for the same origin does not block submit.

        Args:
            user: Acting user (must be in a sect).
            item_uid: Inventory uid of the ``tech_manual`` row.

        Returns:
            dict[str, Any]: Confirmation message and ``review_id``.

        Raises:
            AppError: 40000 missing item / facility / membership; 40227 wrong
                item, non-author, or duplicate pending review for the origin.
        """
        from app.services.technique_craft_service import TechniqueCraftService

        require_sect_system_enabled()
        self._require_facility_gate("scripture_pavilion")
        character, sect, _member = await self._ctx(user)
        await self._org.ensure_sect_org_fields(sect)

        uid = str(item_uid or "").strip()
        row = (
            await self._session.execute(
                select(InventoryItem).where(
                    InventoryItem.character_id == character.id,
                    InventoryItem.item_uid == uid,
                ),
            )
        ).scalar_one_or_none()
        if row is None:
            raise AppError(code=40000, message="背包物品不存在", http_status=400)
        if str(row.item_id) != CARD_MANUAL_ID:
            raise AppError(
                code=ERR_SCRIPTURE_DONATE,
                message="仅可上缴功法秘籍",
                http_status=400,
            )

        meta = InventoryService._parse_row_meta(row)
        snapshot = TechniqueCraftService._require_manual_snapshot(meta)
        if int(snapshot["author_character_id"]) != int(character.id):
            raise AppError(
                code=ERR_SCRIPTURE_DONATE,
                message="仅创作者可上缴",
                http_status=400,
            )

        origin = str(snapshot["origin_technique_id"])
        pending_rows = (
            await self._session.execute(
                select(SectDonationReview).where(
                    SectDonationReview.sect_id == sect.id,
                    SectDonationReview.kind == "scripture",
                    SectDonationReview.status == "pending",
                ),
            )
        ).scalars().all()
        for pending in pending_rows:
            try:
                body = json.loads(pending.payload_json or "{}")
            except json.JSONDecodeError:
                continue
            if not isinstance(body, dict):
                continue
            if str(body.get("origin_technique_id") or "") == origin:
                raise AppError(
                    code=ERR_SCRIPTURE_DONATE,
                    message="该功法已在审核中",
                    http_status=400,
                )

        payload = {
            "manual_kind": "technique",
            "origin_technique_id": origin,
            "author_character_id": int(snapshot["author_character_id"]),
            "label_zh": str(snapshot["label_zh"] or ""),
            "major_rank": str(snapshot["major_rank"]),
            "payload": snapshot["payload"],
            "stats": snapshot["stats"],
            "affix_ids": list(snapshot["affix_ids"]),
        }
        raw_specialty = meta.get("specialty_tag") if isinstance(meta, dict) else None
        if isinstance(raw_specialty, str) and raw_specialty.strip():
            payload["specialty_tag"] = raw_specialty.strip()
        await InventoryService(self._session).remove_one_by_uid(character.id, uid)
        review = SectDonationReview(
            sect_id=sect.id,
            character_id=character.id,
            kind="scripture",
            payload_json=json.dumps(payload, ensure_ascii=False),
            status="pending",
        )
        self._session.add(review)
        await self._session.flush()
        return {
            "message": "已提交审核",
            "review_id": review.id,
        }

    async def list_donations(self, user: User) -> dict[str, Any]:
        """
        List pending donation reviews for the acting character's sect.

        Restricted to founder / leader / supreme_elder.

        Args:
            user: Acting user.

        Returns:
            dict[str, Any]: ``items`` of pending reviews with id, kind, label,
            origin, donor character id, and created_at.

        Raises:
            AppError: 403 if rank is not an admin office.
        """
        require_sect_system_enabled()
        _character, sect, member = await self._ctx(user)
        rank = self._rank(member)
        if rank not in ("founder", "leader", "supreme_elder"):
            raise AppError(code=40000, message="无权查看上供审核", http_status=403)
        rows = (
            await self._session.execute(
                select(SectDonationReview)
                .where(
                    SectDonationReview.sect_id == sect.id,
                    SectDonationReview.status == "pending",
                )
                .order_by(SectDonationReview.id.asc()),
            )
        ).scalars().all()
        items: list[dict[str, Any]] = []
        for row in rows:
            try:
                body = json.loads(row.payload_json or "{}")
            except json.JSONDecodeError:
                body = {}
            if not isinstance(body, dict):
                body = {}
            origin = str(
                body.get("origin_technique_id")
                or body.get("technique_id")
                or body.get("recipe_id")
                or body.get("formation_id")
                or ""
            )
            items.append(
                {
                    "id": int(row.id),
                    "kind": str(row.kind),
                    "label_zh": str(body.get("label_zh") or ""),
                    "origin_technique_id": origin or None,
                    "character_id": int(row.character_id),
                    "created_at": (
                        row.created_at.isoformat() if row.created_at else None
                    ),
                },
            )
        return {"items": items}

    async def review_donation(
        self,
        user: User,
        *,
        review_id: int,
        approve: bool,
    ) -> dict[str, Any]:
        """审核上供（掌门/太上/创派）。"""
        from app.services.technique_craft_service import TechniqueCraftService

        require_sect_system_enabled()
        character, sect, member = await self._ctx(user)
        cfg = self._cfg()
        rank = self._rank(member)
        if rank not in ("leader", "supreme_elder", "founder"):
            raise AppError(code=40000, message="无权审核上供", http_status=403)
        review = await self._session.get(SectDonationReview, int(review_id))
        if review is None or review.sect_id != sect.id or review.status != "pending":
            raise AppError(code=40000, message="审核单无效", http_status=400)
        review.reviewer_character_id = character.id
        review.resolved_at = now_utc()
        payload = json.loads(review.payload_json or "{}")
        if not isinstance(payload, dict):
            payload = {}

        if review.kind == "scripture":
            if not approve:
                review.status = "rejected"
                snapshot = TechniqueCraftService._require_manual_snapshot(payload)
                snapshot_dict = {
                    "manual_kind": "technique",
                    "origin_technique_id": snapshot["origin_technique_id"],
                    "author_character_id": snapshot["author_character_id"],
                    "label_zh": snapshot["label_zh"],
                    "major_rank": snapshot["major_rank"],
                    "payload": snapshot["payload"],
                    "stats": snapshot["stats"],
                    "affix_ids": list(snapshot["affix_ids"]),
                }
                raw_specialty = payload.get("specialty_tag")
                if isinstance(raw_specialty, str) and raw_specialty.strip():
                    snapshot_dict["specialty_tag"] = raw_specialty.strip()
                await InventoryService(self._session).add_item(
                    review.character_id,
                    item_type="manual",
                    item_id=CARD_MANUAL_ID,
                    quantity=1,
                    meta=snapshot_dict,
                )
                await self._session.flush()
                return {"message": "已拒绝上供"}

            review.status = "approved"
            scripture = dict(cfg.scripture or {})
            origin = str(payload.get("origin_technique_id") or "").strip()
            if not origin:
                raise AppError(code=40000, message="审核单无效", http_status=400)
            technique_id = origin
            raw_specialty = payload.get("specialty_tag")
            specialty_tag = (
                str(raw_specialty) or None if raw_specialty is not None else None
            )
            learn_cost = int(scripture.get("learn_cost_contrib") or 0)
            label_zh = str(payload.get("label_zh") or technique_id)
            major_rank = str(payload.get("major_rank") or "") or None
            author_id = payload.get("author_character_id")
            try:
                author_character_id = int(author_id) if author_id is not None else None
            except (TypeError, ValueError):
                author_character_id = None
            payload_json = json.dumps(
                payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
                ensure_ascii=False,
            )
            stats_json = json.dumps(
                payload.get("stats") if isinstance(payload.get("stats"), dict) else {},
                ensure_ascii=False,
            )
            affix_raw = payload.get("affix_ids")
            affix_ids_json = json.dumps(
                list(affix_raw) if isinstance(affix_raw, list) else [],
                ensure_ascii=False,
            )
            exist = (
                await self._session.execute(
                    select(SectScriptureEntry).where(
                        SectScriptureEntry.sect_id == sect.id,
                        SectScriptureEntry.technique_id == technique_id,
                    ),
                )
            ).scalar_one_or_none()
            if exist is None:
                self._session.add(
                    SectScriptureEntry(
                        sect_id=sect.id,
                        technique_id=technique_id,
                        label_zh=label_zh,
                        specialty_tag=specialty_tag,
                        source="self_research",
                        origin_technique_id=origin,
                        author_character_id=author_character_id,
                        major_rank=major_rank,
                        payload_json=payload_json,
                        stats_json=stats_json,
                        affix_ids_json=affix_ids_json,
                        cost_contribution=learn_cost,
                    ),
                )
            else:
                exist.label_zh = label_zh
                exist.major_rank = major_rank
                exist.author_character_id = author_character_id
                exist.origin_technique_id = origin
                exist.payload_json = payload_json
                exist.stats_json = stats_json
                exist.affix_ids_json = affix_ids_json
                exist.cost_contribution = learn_cost
                exist.source = "self_research"
                exist.specialty_tag = specialty_tag

            donor = (
                await self._session.execute(
                    select(SectMember).where(
                        SectMember.sect_id == sect.id,
                        SectMember.character_id == int(review.character_id),
                    ),
                )
            ).scalar_one_or_none()
            # Donor left the sect: entry still stocks; skip contribution grant.
            if donor is not None:
                reward = int(scripture.get("donate_reward_contrib") or 0)
                bonus = 0
                if specialty_tag and str(specialty_tag) == str(
                    getattr(sect, "specialty", None) or ""
                ):
                    bonus = int(scripture.get("specialty_match_bonus_contrib") or 0)
                delta = reward + bonus
                if delta:
                    await self._apply_contrib(
                        donor,
                        delta=delta,
                        reason="scripture_donate",
                        note_zh="藏经阁上供通过",
                    )
            await self._session.flush()
            return {"message": "已通过上供审核"}

        if not approve:
            review.status = "rejected"
            await self._session.flush()
            return {"message": "已拒绝上供"}
        review.status = "approved"
        if review.kind == "blueprint":
            branch = str(payload.get("branch") or "")
            recipe_id = str(payload.get("recipe_id") or "")
            if branch and recipe_id:
                exist_bp = (
                    await self._session.execute(
                        select(SectWorkshopBlueprint).where(
                            SectWorkshopBlueprint.sect_id == sect.id,
                            SectWorkshopBlueprint.branch == branch,
                            SectWorkshopBlueprint.recipe_id == recipe_id,
                        ),
                    )
                ).scalar_one_or_none()
                if exist_bp is None:
                    self._session.add(
                        SectWorkshopBlueprint(
                            sect_id=sect.id,
                            branch=branch,
                            recipe_id=recipe_id,
                            label_zh=str(payload.get("label_zh") or recipe_id),
                            cost_contribution=int(payload.get("cost_contribution") or 40),
                            source="self_research",
                            sellable=True,
                            deposited_by=review.character_id,
                        ),
                    )
        elif review.kind == "formation":
            state = await self._get_or_create_formation(sect.id)
            learned = []
            try:
                learned = json.loads(state.learned_json or "[]")
            except json.JSONDecodeError:
                learned = []
            fid = str(payload.get("formation_id") or "")
            if fid and fid not in learned:
                learned.append(fid)
            state.learned_json = json.dumps(learned, ensure_ascii=False)
        await self._session.flush()
        return {"message": "已通过上供审核"}

    # ----- 工坊 -----

    def _workshop_gate(self, branch: str) -> str:
        """分支 → 设施闸 id。"""
        gate = {
            "smithing": "forge_workshop",
            "alchemy": "alchemy_workshop",
            "talisman": "talisman_workshop",
        }.get(branch)
        if not gate:
            raise AppError(code=40000, message="未知工坊分支", http_status=400)
        return gate

    def _workshop_label_zh(self, branch: str) -> str:
        """工坊中文名。"""
        return {
            "smithing": "锻造工坊",
            "alchemy": "炼丹阁",
            "talisman": "服务工坊",
        }.get(branch, branch)

    async def _merged_blueprints(
        self,
        *,
        sect_id: int,
        branch: str,
    ) -> list[dict[str, Any]]:
        """合并 YAML 目录与本宗已上缴图纸。"""
        cfg = self._cfg()
        by_recipe: dict[str, dict[str, Any]] = {}
        for row in list((cfg.workshop_blueprints or {}).get(branch) or []):
            rid = str(row.get("recipe_id") or "")
            if not rid:
                continue
            by_recipe[rid] = {
                "recipe_id": rid,
                "label_zh": str(row.get("label_zh") or rid),
                "cost_contribution": int(row.get("cost_contribution") or 40),
                "sellable": bool(row.get("sellable", True)),
                "source": "catalog",
            }
        donated = (
            await self._session.execute(
                select(SectWorkshopBlueprint).where(
                    SectWorkshopBlueprint.sect_id == sect_id,
                    SectWorkshopBlueprint.branch == branch,
                ),
            )
        ).scalars().all()
        for d in donated:
            by_recipe[str(d.recipe_id)] = {
                "recipe_id": d.recipe_id,
                "label_zh": d.label_zh,
                "cost_contribution": int(d.cost_contribution),
                "sellable": bool(d.sellable),
                "source": d.source,
            }
        return list(by_recipe.values())

    async def workshop_catalog(self, user: User, *, branch: str) -> dict[str, Any]:
        """工坊图纸与工匠目录。"""
        require_sect_system_enabled()
        gate = self._workshop_gate(branch)
        self._require_facility_gate(gate)
        character, sect, member = await self._ctx(user)
        await self._org.ensure_sect_org_fields(sect)
        cfg = self._cfg()
        bps = await self._merged_blueprints(sect_id=sect.id, branch=branch)
        craftsmen = [
            {
                "craftsman_id": cid,
                "label_zh": str(body.get("label_zh") or cid),
                "grade": int(body.get("grade") or 1),
                "quality_chance": float(body.get("quality_chance") or 0),
                "cost_contribution": int(body.get("cost_contribution") or 0),
            }
            for cid, body in cfg.craftsmen.items()
            if str(body.get("branch")) == branch
        ]
        inv_cfg = get_game_config().inventory
        bag_rows = (
            await self._session.execute(
                select(InventoryItem).where(
                    InventoryItem.character_id == character.id,
                    InventoryItem.item_type == ItemType.MANUAL,
                ),
            )
        ).scalars().all()
        bag_blueprints: list[dict[str, Any]] = []
        for row in bag_rows:
            meta: dict[str, Any] = {}
            if row.meta_json:
                try:
                    parsed = json.loads(row.meta_json)
                    if isinstance(parsed, dict):
                        meta = parsed
                except json.JSONDecodeError:
                    meta = {}
            defn = inv_cfg.items.get(str(row.item_id))
            kind = str(
                meta.get("manual_kind")
                or (defn.manual_kind if defn is not None else "")
                or "",
            )
            if not manual_kind_matches_workshop(kind, branch):
                continue
            bag_blueprints.append(
                {
                    "inventory_item_id": row.id,
                    "item_id": row.item_id,
                    "quantity": int(row.quantity),
                    "label_zh": str(
                        meta.get("label_zh")
                        or (defn.name if defn is not None else row.item_id),
                    ),
                    "manual_kind": kind,
                    "unlock_recipe_id": str(
                        meta.get("unlock_recipe_id")
                        or (defn.unlock_recipe_id if defn is not None else "")
                        or "",
                    ),
                },
            )
        jobs = (
            await self._session.execute(
                select(SectCraftJob)
                .where(
                    SectCraftJob.character_id == character.id,
                    SectCraftJob.branch == branch,
                    SectCraftJob.status == "running",
                )
                .order_by(SectCraftJob.id),
            )
        ).scalars().all()
        now = now_utc()
        my_jobs = [
            {
                "job_id": j.id,
                "recipe_id": j.recipe_id,
                "finish_at": j.finish_at.isoformat() if j.finish_at else None,
                "ready": bool(j.finish_at and now >= j.finish_at),
                "quality": bool(j.quality),
            }
            for j in jobs
        ]
        return {
            "branch": branch,
            "branch_label_zh": self._workshop_label_zh(branch),
            "blueprints": bps,
            "craftsmen": craftsmen,
            "bag_blueprints": bag_blueprints,
            "my_jobs": my_jobs,
            "contrib": int(member.contribution),
        }

    async def workshop_exchange_blueprint(
        self,
        user: User,
        *,
        branch: str,
        recipe_id: str,
    ) -> dict[str, Any]:
        """贡献兑换工坊图纸（须在目录且可售）；图纸入背包 ``item_type=manual``。"""
        require_sect_system_enabled()
        self._require_facility_gate(self._workshop_gate(branch))
        character, sect, member = await self._ctx(user)
        bps = await self._merged_blueprints(sect_id=sect.id, branch=branch)
        hit = next((x for x in bps if str(x.get("recipe_id")) == recipe_id), None)
        if hit is None:
            raise AppError(code=40000, message="图纸未收录", http_status=400)
        if not bool(hit.get("sellable", True)):
            raise AppError(code=40000, message="该图纸不可兑换", http_status=400)
        kind = workshop_manual_kind(branch)
        if kind is None:
            raise AppError(code=40000, message="未知工坊分支", http_status=400)
        cost = int(hit.get("cost_contribution") or 0)
        await self._apply_contrib(
            member,
            delta=-cost,
            reason="workshop_blueprint_exchange",
            note_zh=f"{self._workshop_label_zh(branch)}兑换 {hit.get('label_zh')}",
        )
        item_id = blueprint_catalog_item_id(recipe_id)
        inv_cfg = get_game_config().inventory
        defn = inv_cfg.items.get(item_id)
        label = str(hit.get("label_zh") or (defn.name if defn else recipe_id))
        await InventoryService(self._session).add_item(
            character.id,
            item_type=ItemType.MANUAL,
            item_id=item_id if defn is not None else item_id,
            quantity=1,
            meta={
                "manual_kind": kind if defn is None else (defn.manual_kind or kind),
                "unlock_recipe_id": recipe_id,
                "label_zh": label,
                "source": "sect_exchange",
            },
        )
        await self._session.flush()
        return {
            "message": f"已兑换「{label}」入背包",
            "recipe_id": recipe_id,
            "item_id": item_id,
            "contrib": int(member.contribution),
        }

    async def workshop_donate_blueprint(
        self,
        user: User,
        *,
        branch: str,
        recipe_id: str,
        label_zh: str,
        cost_contribution: int = 40,
        self_research: bool = False,
        inventory_item_id: int | None = None,
    ) -> dict[str, Any]:
        """
        上缴图纸：非自研须消耗背包 ``manual`` 行并校验 ``manual_kind``；
        未收录可获贡献；已收录拒绝；自创须审核。
        """
        require_sect_system_enabled()
        self._require_facility_gate(self._workshop_gate(branch))
        character, sect, member = await self._ctx(user)
        recipes = get_game_config().craft_recipes.recipes
        resolved_recipe = str(recipe_id or "").strip()
        cleaned_label = (label_zh or resolved_recipe).strip() or resolved_recipe

        if self_research:
            if not resolved_recipe:
                raise AppError(code=40000, message="请填写自创图纸配方 id", http_status=400)
            review = SectDonationReview(
                sect_id=sect.id,
                character_id=character.id,
                kind="blueprint",
                payload_json=json.dumps(
                    {
                        "branch": branch,
                        "recipe_id": resolved_recipe,
                        "label_zh": cleaned_label,
                        "cost_contribution": int(cost_contribution),
                    },
                    ensure_ascii=False,
                ),
                status="pending",
            )
            self._session.add(review)
            await self._session.flush()
            return {
                "message": "自创图纸已提交审核（须掌门/太上/创派同意）",
                "review_id": review.id,
            }

        if inventory_item_id is None:
            raise AppError(code=40000, message="请选择背包中的图纸再上缴", http_status=400)
        inv_row = await self._session.get(InventoryItem, int(inventory_item_id))
        if inv_row is None or int(inv_row.character_id) != int(character.id):
            raise AppError(code=40055, message="图纸不存在", http_status=400)
        if str(inv_row.item_type) != ItemType.MANUAL:
            raise AppError(
                ERR_BLUEPRINT_TYPE_MISMATCH,
                "只能上缴秘籍类图纸",
                http_status=400,
            )
        if int(inv_row.quantity) < 1:
            raise AppError(code=40055, message="图纸数量不足", http_status=400)
        meta: dict[str, Any] = {}
        if inv_row.meta_json:
            try:
                parsed = json.loads(inv_row.meta_json)
                if isinstance(parsed, dict):
                    meta = parsed
            except json.JSONDecodeError:
                meta = {}
        inv_cfg = get_game_config().inventory
        defn = inv_cfg.items.get(str(inv_row.item_id))
        manual_kind = str(
            meta.get("manual_kind")
            or (defn.manual_kind if defn is not None else "")
            or "",
        ).strip()
        if not manual_kind_matches_workshop(manual_kind, branch):
            raise AppError(
                ERR_BLUEPRINT_TYPE_MISMATCH,
                f"该图纸不属于{self._workshop_label_zh(branch)}",
                http_status=400,
            )
        unlock = str(
            meta.get("unlock_recipe_id")
            or (defn.unlock_recipe_id if defn is not None else "")
            or resolved_recipe
            or "",
        ).strip()
        if not unlock:
            raise AppError(code=40000, message="图纸缺少配方引用", http_status=400)
        if unlock in recipes:
            recipe_branch = str(getattr(recipes[unlock], "branch", "") or "")
            if recipe_branch and not recipe_branch_matches_workshop(recipe_branch, branch):
                raise AppError(
                    ERR_BLUEPRINT_TYPE_MISMATCH,
                    f"该图纸不属于{self._workshop_label_zh(branch)}",
                    http_status=400,
                )
        elif not resolved_recipe:
            # 允许未在 craft_recipes 的捐赠 id（来自 meta），仍须已收录校验
            pass
        resolved_recipe = unlock
        cleaned_label = (
            (label_zh or "").strip()
            or str(meta.get("label_zh") or "")
            or (defn.name if defn is not None else "")
            or resolved_recipe
        )

        existing = await self._merged_blueprints(sect_id=sect.id, branch=branch)
        if any(str(x.get("recipe_id")) == resolved_recipe for x in existing):
            raise AppError(code=40000, message="该图纸已收录，无法再上缴", http_status=400)

        qty = int(inv_row.quantity) - 1
        if qty <= 0:
            await self._session.delete(inv_row)
        else:
            inv_row.quantity = qty

        self._session.add(
            SectWorkshopBlueprint(
                sect_id=sect.id,
                branch=branch,
                recipe_id=resolved_recipe,
                label_zh=cleaned_label,
                cost_contribution=int(cost_contribution),
                source="donated",
                sellable=True,
                deposited_by=character.id,
            ),
        )
        bonus = 20
        await self._apply_contrib(
            member,
            delta=bonus,
            reason="workshop_blueprint_donate",
            note_zh=f"上缴图纸 {cleaned_label}",
        )
        await self._session.flush()
        return {
            "message": f"已上缴「{cleaned_label}」，贡献 +{bonus}",
            "contrib_gain": bonus,
            "contrib": int(member.contribution),
            "recipe_id": resolved_recipe,
        }

    async def workshop_hire(
        self,
        user: User,
        *,
        branch: str,
        craftsman_id: str,
        recipe_id: str,
    ) -> dict[str, Any]:
        """聘工匠代工（扣贡献 + **真扣材料**）。"""
        require_sect_system_enabled()
        self._require_facility_gate(self._workshop_gate(branch))
        character, sect, member = await self._ctx(user)
        cfg = self._cfg()
        craftsman = cfg.craftsmen.get(craftsman_id)
        if not craftsman or str(craftsman.get("branch")) != branch:
            raise AppError(code=40000, message="未知工匠", http_status=400)
        allowed = {
            str(x.get("recipe_id"))
            for x in await self._merged_blueprints(sect_id=sect.id, branch=branch)
        }
        if recipe_id not in allowed:
            raise AppError(code=40000, message="工坊未收录该图纸，工匠不可制作", http_status=400)
        recipes = get_game_config().craft_recipes.recipes
        recipe = recipes.get(recipe_id)
        if recipe is None:
            raise AppError(code=40000, message="配方不存在", http_status=400)
        materials = [
            {
                "item_id": str(mat.item_id),
                "quantity": int(mat.quantity),
            }
            for mat in (recipe.materials or ())
            if str(mat.item_id) and int(mat.quantity) > 0
        ]
        try:
            await InventoryService(self._session).remove_materials(character.id, materials)
        except AppError as exc:
            if exc.code == 40055:
                raise AppError(code=40055, message=exc.message or "材料不足", http_status=400) from exc
            raise
        cost = int(craftsman.get("cost_contribution") or 0)
        await self._apply_contrib(
            member,
            delta=-cost,
            reason="sect_craft_hire",
            note_zh=f"聘{craftsman.get('label_zh')}代工",
        )
        q_chance = float(craftsman.get("quality_chance") or 0)
        buffs = []
        try:
            buffs = json.loads(sect.buffs_json or "[]")
        except json.JSONDecodeError:
            buffs = []
        if "craft_boost" in buffs:
            q_chance += float(
                (cfg.sect_buffs.get("craft_boost") or {}).get("craft_quality_bonus") or 0,
            )
        is_quality = chance(min(0.95, max(0.0, q_chance)))
        finish = now_utc() + timedelta(seconds=30)
        job = SectCraftJob(
            sect_id=sect.id,
            character_id=character.id,
            branch=branch,
            craftsman_id=craftsman_id,
            recipe_id=recipe_id,
            status="running",
            quality=bool(is_quality),
            finish_at=finish,
        )
        self._session.add(job)
        await self._session.flush()
        return {
            "message": "工匠已接单（已扣除材料）",
            "job_id": job.id,
            "finish_at": finish.isoformat(),
            "quality": bool(is_quality),
            "contrib": int(member.contribution),
        }

    async def workshop_claim(self, user: User, *, job_id: int) -> dict[str, Any]:
        """领取代工成品入背包。"""
        require_sect_system_enabled()
        character, _sect, _member = await self._ctx(user)
        job = await self._session.get(SectCraftJob, int(job_id))
        if job is None or job.character_id != character.id:
            raise AppError(code=40000, message="代工单不存在", http_status=400)
        if job.status != "running":
            raise AppError(code=40000, message="代工单已结束", http_status=400)
        if now_utc() < job.finish_at:
            raise AppError(code=40000, message="尚未完工", http_status=400)
        recipe = get_game_config().craft_recipes.recipes.get(str(job.recipe_id))
        if recipe is None:
            raise AppError(code=40000, message="配方不存在", http_status=400)
        inv = InventoryService(self._session)
        granted: list[dict[str, Any]] = []
        for out in recipe.outputs or ():
            if int(out.grant_array_craft_level or 0) > 0:
                character.array_craft_level = max(
                    int(character.array_craft_level or 0),
                    int(out.grant_array_craft_level),
                )
                granted.append({"grant_array_craft_level": int(out.grant_array_craft_level)})
                continue
            if not out.item_type or not out.item_id:
                continue
            qty = int(out.quantity or 1) * (2 if job.quality else 1)
            await inv.add_item(
                character.id,
                item_type=str(out.item_type),
                item_id=str(out.item_id),
                quantity=qty,
            )
            granted.append(
                {
                    "item_type": str(out.item_type),
                    "item_id": str(out.item_id),
                    "quantity": qty,
                },
            )
        job.status = "claimed"
        job.claimed_at = now_utc()
        await self._session.flush()
        return {
            "message": "已领取成品" + ("（精品）" if job.quality else ""),
            "recipe_id": job.recipe_id,
            "quality": job.quality,
            "outputs": granted,
        }

    # ----- 大阵 -----

    async def _get_or_create_formation(self, sect_id: int) -> SectFormationState:
        """阵法状态行。"""
        row = (
            await self._session.execute(
                select(SectFormationState).where(SectFormationState.sect_id == sect_id),
            )
        ).scalar_one_or_none()
        if row is None:
            row = SectFormationState(sect_id=sect_id, level=1, active=False)
            self._session.add(row)
            await self._session.flush()
        return row

    async def formation_status(self, user: User) -> dict[str, Any]:
        """宗门大阵状态（无管理权仅见兑换/上缴；有权者可选阵/启停/加点）。"""
        require_sect_system_enabled()
        self._require_facility_gate("formation_array")
        _c, sect, member = await self._ctx(user)
        cfg = self._cfg()
        state = await self._get_or_create_formation(sect.id)
        learned = self._parse_learned(state)
        attrs = self._parse_formation_attrs(state)
        can_manage = council_action_allowed(
            rank=self._rank(member),
            action="upgrade_facility",
            disciple_ranks=cfg.disciple_ranks,
        )
        attr_keys = cfg.formation_attr_keys or {
            "attack": {"label_zh": "攻击"},
            "defense": {"label_zh": "防御"},
            "resistance": {"label_zh": "抗性"},
        }
        return {
            "formation_id": state.formation_id,
            "level": int(state.level or 1),
            "active": bool(state.active),
            "learned": learned,
            "attrs": attrs,
            "attr_spent": sum(int(v) for v in attrs.values()),
            "attr_catalog": [
                {
                    "attr_key": key,
                    "label_zh": str((body or {}).get("label_zh") or key),
                    "points": int(attrs.get(key) or 0),
                }
                for key, body in attr_keys.items()
            ],
            "catalog": [
                {
                    "formation_id": fid,
                    "label_zh": str(body.get("label_zh") or fid),
                    "summary": str(body.get("summary") or ""),
                    "max_level": int(body.get("max_level") or 5),
                    "max_attr_points": int(body.get("max_attr_points") or 10),
                    "activate_cost_spirit_stones": int(
                        body.get("activate_cost_spirit_stones") or 0,
                    ),
                    "attr_point_cost_spirit_stones": int(
                        body.get("attr_point_cost_spirit_stones")
                        or body.get("upgrade_cost_spirit_stones")
                        or 120,
                    ),
                    "exchange_cost_contribution": int(
                        body.get("exchange_cost_contribution") or 0,
                    ),
                    "learned": fid in learned,
                }
                for fid, body in cfg.formations.items()
            ],
            "spirit_stone_pool": int(sect.spirit_stone_pool or 0),
            "contrib": int(member.contribution),
            "can_manage": can_manage,
        }

    @staticmethod
    def _parse_learned(state: SectFormationState) -> list[str]:
        """解析已学阵法列表。"""
        try:
            raw = json.loads(state.learned_json or "[]")
        except json.JSONDecodeError:
            return []
        return [str(x) for x in raw] if isinstance(raw, list) else []

    @staticmethod
    def _parse_formation_attrs(state: SectFormationState) -> dict[str, int]:
        """解析阵法加点。"""
        try:
            raw = json.loads(state.attr_json or "{}")
        except json.JSONDecodeError:
            raw = {}
        if not isinstance(raw, dict):
            return {}
        return {str(k): int(v or 0) for k, v in raw.items()}

    async def formation_select(self, user: User, *, formation_id: str) -> dict[str, Any]:
        """选择阵法（须已学会且有管理权）。"""
        require_sect_system_enabled()
        self._require_facility_gate("formation_array")
        _c, sect, member = await self._ctx(user)
        cfg = self._cfg()
        if not council_action_allowed(
            rank=self._rank(member),
            action="upgrade_facility",
            disciple_ranks=cfg.disciple_ranks,
        ):
            raise AppError(code=40000, message="无权管理阵法", http_status=403)
        if formation_id not in cfg.formations:
            raise AppError(code=40000, message="未知阵法", http_status=400)
        state = await self._get_or_create_formation(sect.id)
        learned = self._parse_learned(state)
        if formation_id not in learned:
            raise AppError(code=40000, message="尚未学会该阵法（请先兑换或上缴）", http_status=400)
        state.formation_id = formation_id
        state.active = False
        await self._session.flush()
        return {"message": "已选择阵法", "formation_id": formation_id}

    async def formation_set_active(self, user: User, *, active: bool) -> dict[str, Any]:
        """开启/关闭阵法（扣宗门灵石）。"""
        require_sect_system_enabled()
        self._require_facility_gate("formation_array")
        _c, sect, member = await self._ctx(user)
        cfg = self._cfg()
        if not council_action_allowed(
            rank=self._rank(member),
            action="upgrade_facility",
            disciple_ranks=cfg.disciple_ranks,
        ):
            raise AppError(code=40000, message="无权管理阵法", http_status=403)
        state = await self._get_or_create_formation(sect.id)
        if not state.formation_id:
            raise AppError(code=40000, message="尚未选择阵法", http_status=400)
        if active and not state.active:
            cost = int(
                (cfg.formations.get(state.formation_id) or {}).get(
                    "activate_cost_spirit_stones",
                )
                or 0,
            )
            pool = int(sect.spirit_stone_pool or 0)
            if pool < cost:
                raise AppError(code=40102, message=f"宗门灵石不足：开启需 {cost}", http_status=400)
            sect.spirit_stone_pool = pool - cost
        state.active = bool(active)
        await self._session.flush()
        return {
            "message": "阵法已" + ("开启" if active else "关闭"),
            "active": state.active,
            "spirit_stone_pool": int(sect.spirit_stone_pool or 0),
        }

    async def formation_allocate_attr(
        self,
        user: User,
        *,
        attr_key: str,
    ) -> dict[str, Any]:
        """给当前阵法加点（攻击/防御/抗性等；扣宗门灵石）。"""
        require_sect_system_enabled()
        self._require_facility_gate("formation_array")
        _c, sect, member = await self._ctx(user)
        cfg = self._cfg()
        if not council_action_allowed(
            rank=self._rank(member),
            action="upgrade_facility",
            disciple_ranks=cfg.disciple_ranks,
        ):
            raise AppError(code=40000, message="无权升级阵法", http_status=403)
        attr_keys = cfg.formation_attr_keys or {}
        if attr_key not in attr_keys and attr_key not in ("attack", "defense", "resistance"):
            raise AppError(code=40000, message="未知阵法属性", http_status=400)
        state = await self._get_or_create_formation(sect.id)
        if not state.formation_id:
            raise AppError(code=40000, message="尚未选择阵法", http_status=400)
        body = cfg.formations.get(state.formation_id) or {}
        max_pts = int(body.get("max_attr_points") or body.get("max_level") or 10)
        attrs = self._parse_formation_attrs(state)
        spent = sum(int(v) for v in attrs.values())
        if spent >= max_pts:
            raise AppError(code=40000, message="阵法属性点已达上限", http_status=400)
        cost = int(
            body.get("attr_point_cost_spirit_stones")
            or body.get("upgrade_cost_spirit_stones")
            or 120,
        )
        pool = int(sect.spirit_stone_pool or 0)
        if pool < cost:
            raise AppError(code=40102, message=f"宗门灵石不足：加点需 {cost}", http_status=400)
        sect.spirit_stone_pool = pool - cost
        attrs[attr_key] = int(attrs.get(attr_key) or 0) + 1
        state.attr_json = json.dumps(attrs, ensure_ascii=False)
        state.level = 1 + sum(int(v) for v in attrs.values())
        await self._session.flush()
        label = str((attr_keys.get(attr_key) or {}).get("label_zh") or attr_key)
        return {
            "message": f"已为阵法强化「{label}」",
            "attrs": attrs,
            "level": state.level,
            "spirit_stone_pool": int(sect.spirit_stone_pool or 0),
        }

    async def formation_upgrade(self, user: User) -> dict[str, Any]:
        """兼容旧接口：默认给「防御」加点。"""
        return await self.formation_allocate_attr(user, attr_key="defense")

    async def formation_exchange(
        self,
        user: User,
        *,
        formation_id: str,
    ) -> dict[str, Any]:
        """用贡献兑换阵法（加入已学列表；无管理权亦可）。"""
        require_sect_system_enabled()
        self._require_facility_gate("formation_array")
        _c, sect, member = await self._ctx(user)
        body = self._cfg().formations.get(formation_id)
        if not body:
            raise AppError(code=40000, message="未知阵法", http_status=400)
        cost = int(body.get("exchange_cost_contribution") or 0)
        if cost <= 0:
            raise AppError(code=40000, message="该阵法不可兑换", http_status=400)
        state = await self._get_or_create_formation(sect.id)
        learned = self._parse_learned(state)
        if formation_id in learned:
            raise AppError(code=40000, message="已学会该阵法", http_status=400)
        await self._apply_contrib(
            member,
            delta=-cost,
            reason="formation_exchange",
            note_zh=f"兑换阵法 {body.get('label_zh') or formation_id}",
        )
        learned.append(formation_id)
        state.learned_json = json.dumps(learned, ensure_ascii=False)
        await self._session.flush()
        return {
            "message": f"已兑换「{body.get('label_zh') or formation_id}」",
            "learned": learned,
            "contrib": int(member.contribution),
        }

    async def formation_donate(
        self,
        user: User,
        *,
        formation_id: str,
        need_review: bool = True,
    ) -> dict[str, Any]:
        """上缴阵法功法（默认审核；无管理权亦可）。"""
        require_sect_system_enabled()
        self._require_facility_gate("formation_array")
        character, sect, _member = await self._ctx(user)
        if formation_id not in self._cfg().formations:
            raise AppError(code=40000, message="未知阵法", http_status=400)
        if need_review:
            review = SectDonationReview(
                sect_id=sect.id,
                character_id=character.id,
                kind="formation",
                payload_json=json.dumps({"formation_id": formation_id}, ensure_ascii=False),
                status="pending",
            )
            self._session.add(review)
            await self._session.flush()
            return {"message": "阵法上缴已提交审核", "review_id": review.id}
        state = await self._get_or_create_formation(sect.id)
        learned = self._parse_learned(state)
        if formation_id not in learned:
            learned.append(formation_id)
        state.learned_json = json.dumps(learned, ensure_ascii=False)
        await self._session.flush()
        return {"message": "已上缴并学会阵法", "learned": learned}

    # ----- 矿脉 -----

    async def _get_or_create_mine_state(self, sect_id: int) -> SectMineState:
        """矿脉被动产出锚点。"""
        row = (
            await self._session.execute(
                select(SectMineState).where(SectMineState.sect_id == sect_id),
            )
        ).scalar_one_or_none()
        if row is None:
            row = SectMineState(sect_id=sect_id, last_accrued_at=now_utc())
            self._session.add(row)
            await self._session.flush()
        return row

    async def _miner_count(self, sect_id: int) -> int:
        """当前采矿人数（本体席位 + 化身采矿）。"""
        rows = (
            await self._session.execute(
                select(SectMineMiner).where(SectMineMiner.sect_id == sect_id),
            )
        ).scalars().all()
        body = len(rows)
        from app.db.models.avatar import Avatar
        from app.db.models.character import Character as CharModel

        avatar_miners = (
            await self._session.execute(
                select(Avatar.id)
                .join(CharModel, CharModel.id == Avatar.character_id)
                .where(
                    CharModel.sect_id == sect_id,
                    Avatar.idle_direction == "sect_mining",
                ),
            )
        ).all()
        return body + len(avatar_miners)

    async def _accrue_mine_pool(self, sect: Sect) -> int:
        """
        将矿脉被动产出按整分钟结算入宗门灵石库。

        未满 ``tick_seconds`` 的零头不入账（自锚点起算，与点击开始后的个人 tick 同节奏）。

        Returns:
            本次入账灵石数。
        """
        await self._org.ensure_sect_org_fields(sect)
        cfg = self._cfg()
        my = cfg.mine_yield or {}
        state = await self._get_or_create_mine_state(sect.id)
        now = now_utc()
        last = state.last_accrued_at
        if last.tzinfo is None:
            from datetime import timezone

            last = last.replace(tzinfo=timezone.utc)
        tick_sec = int(my.get("tick_seconds") or get_game_config().idle.tick_seconds or 60)
        elapsed = max(0.0, (now - last).total_seconds())
        ticks = int(elapsed // tick_sec)
        if ticks <= 0:
            return 0
        fl = await self._facility_level(sect.id, "spirit_mine")
        grade_order = int((cfg.sect_grades.get(str(sect.grade or "hut")) or {}).get("order") or 1)
        miners = await self._miner_count(sect.id)
        rate = mine_pool_rate_per_hour(
            grade_order=grade_order,
            facility_level=fl,
            miner_count=miners,
            mine_yield=my,
        )
        amount = int(rate * (ticks * tick_sec / 3600.0))
        if amount > 0:
            sect.spirit_stone_pool = int(sect.spirit_stone_pool or 0) + amount
        state.last_accrued_at = last + timedelta(seconds=ticks * tick_sec)
        await self._session.flush()
        return amount

    async def settle_mining_character(
        self,
        character: Character,
        now: Any | None = None,
    ) -> dict[str, Any]:
        """
        结算角色采矿挂机（体力→个人灵石；并顺带结算宗门矿脉入库）。

        供 IdleService.settle_dual_async / 矿脉启停调用。
        """
        from datetime import timezone

        from app.services.stamina_service import StaminaService

        miner = (
            await self._session.execute(
                select(SectMineMiner).where(SectMineMiner.character_id == character.id),
            )
        ).scalar_one_or_none()
        if miner is None:
            if character.idle_direction == "sect_mining":
                character.idle_direction = "none"
            return {"ticks": 0, "personal_stones": 0, "stopped": False}

        sect = await self._session.get(Sect, miner.sect_id)
        if sect is None:
            await self._session.delete(miner)
            character.idle_direction = "none"
            return {"ticks": 0, "personal_stones": 0, "stopped": True}

        cfg = self._cfg()
        my = cfg.mine_yield or {}
        tick_sec = int(my.get("tick_seconds") or get_game_config().idle.tick_seconds or 60)
        personal_per = int(my.get("personal_stones_per_tick") or 5)
        stamina_per = int(my.get("stamina_per_tick") or 2)
        now_aware = now_utc(now)
        last = miner.last_settled_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        # 未满自开始起的一整段 tick：不发个人灵石、不扣体力；宗门库按自身锚点满 tick 入账
        max_ticks = int(max(0.0, (now_aware - last).total_seconds()) // tick_sec)
        if max_ticks <= 0:
            pool_gained = await self._accrue_mine_pool(sect)
            return {
                "ticks": 0,
                "personal_stones": 0,
                "pool_stones": pool_gained,
                "stopped": False,
            }

        stamina = StaminaService(self._session)
        # 个人灵石受时辰/天气/通道加成（与修灵同式）
        from app.services.env_preview_service import build_character_idle_env

        idle_env = await build_character_idle_env(self._session, character, now=now_aware)
        mining_preview = dict(idle_env.get("sect_mining") or {})
        personal_effective = max(
            0,
            int(mining_preview.get("effective_per_tick") or personal_per),
        )

        used = 0
        gained = 0
        spent_stamina = 0
        stopped = False
        for _ in range(max_ticks):
            # 结算灵石与扣体力同步：体力不足则本 tick 不入账并停采
            try:
                stamina.spend_amount(
                    character,
                    stamina_per,
                    reason="sect_mining",
                    now=now_aware,
                )
            except AppError:
                stopped = True
                break
            character.spirit_stones = int(character.spirit_stones or 0) + personal_effective
            gained += personal_effective
            spent_stamina += stamina_per
            used += 1

        miner.last_settled_at = last + timedelta(seconds=used * tick_sec)
        if used > 0:
            character.last_settled_at = miner.last_settled_at
        if stopped:
            await self._session.delete(miner)
            character.idle_direction = "none"
        # 宗门库按 tick_seconds 自锚点满段入账（含采矿加速）
        pool_gained = await self._accrue_mine_pool(sect)
        await self._session.flush()
        return {
            "ticks": used,
            "personal_stones": gained,
            "pool_stones": pool_gained,
            "spent_stamina": spent_stamina,
            "personal_per_tick": personal_effective,
            "stopped": stopped,
            "spirit_stones": int(character.spirit_stones or 0),
        }

    async def settle_avatar_mining(
        self,
        character: Character,
        avatar: Any,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        结算化身采矿：个人灵石入本体钱包、扣本体体力；不写 SectMineMiner 行。

        Args:
            character: 本体。
            avatar: 化身 ORM。
            now: 结算时刻。

        Returns:
            dict: ticks / personal_stones / spent_stamina / stopped。
        """
        from datetime import timedelta, timezone

        from app.db.models.avatar import Avatar
        from app.services.stamina_service import StaminaService

        if not isinstance(avatar, Avatar):
            return {"ticks": 0, "personal_stones": 0, "spent_stamina": 0, "stopped": False}
        if str(avatar.idle_direction or "") != "sect_mining":
            return {"ticks": 0, "personal_stones": 0, "spent_stamina": 0, "stopped": False}
        if not character.sect_id:
            avatar.idle_direction = "none"
            await self._session.flush()
            return {"ticks": 0, "personal_stones": 0, "spent_stamina": 0, "stopped": True}

        sect = await self._session.get(Sect, int(character.sect_id))
        if sect is None:
            avatar.idle_direction = "none"
            await self._session.flush()
            return {"ticks": 0, "personal_stones": 0, "spent_stamina": 0, "stopped": True}

        cfg = self._cfg()
        my = cfg.mine_yield or {}
        tick_sec = int(my.get("tick_seconds") or get_game_config().idle.tick_seconds or 60)
        personal_per = int(my.get("personal_stones_per_tick") or 5)
        stamina_per = int(my.get("stamina_per_tick") or 2)
        now_aware = now_utc(now)
        last = avatar.last_settled_at
        if last is None:
            last = now_aware
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        max_ticks = int(max(0.0, (now_aware - last).total_seconds()) // tick_sec)
        if max_ticks <= 0:
            pool_gained = await self._accrue_mine_pool(sect)
            return {
                "ticks": 0,
                "personal_stones": 0,
                "pool_stones": pool_gained,
                "spent_stamina": 0,
                "stopped": False,
            }

        from app.services.env_preview_service import build_character_idle_env

        idle_env = await build_character_idle_env(self._session, character, now=now_aware)
        mining_preview = dict(idle_env.get("sect_mining") or {})
        personal_effective = max(
            0,
            int(mining_preview.get("effective_per_tick") or personal_per),
        )
        # 化身采矿个人收益按 0.8 折
        personal_effective = max(1, int(personal_effective * 0.8)) if personal_effective > 0 else 0

        stamina = StaminaService(self._session)
        used = 0
        gained = 0
        spent_stamina = 0
        stopped = False
        for _ in range(max_ticks):
            try:
                stamina.spend_amount(
                    character,
                    stamina_per,
                    reason="avatar_sect_mining",
                    now=now_aware,
                )
            except AppError:
                stopped = True
                break
            character.spirit_stones = int(character.spirit_stones or 0) + personal_effective
            gained += personal_effective
            spent_stamina += stamina_per
            used += 1

        avatar.last_settled_at = last + timedelta(seconds=used * tick_sec)
        if stopped:
            avatar.idle_direction = "none"
        pool_gained = await self._accrue_mine_pool(sect)
        await self._session.flush()
        return {
            "ticks": used,
            "personal_stones": gained,
            "pool_stones": pool_gained,
            "spent_stamina": spent_stamina,
            "stopped": stopped,
            "spirit_stones": int(character.spirit_stones or 0),
        }

    async def start_avatar_mining(self, character: Character, avatar: Any) -> None:
        """化身开始采矿：校验入宗与名额，重置结算锚点。"""
        from app.db.models.avatar import Avatar

        if not isinstance(avatar, Avatar):
            raise AppError(code=40051, message="尚未凝练化身", http_status=400)
        if not character.sect_id:
            raise AppError(code=40000, message="散修不可采矿，请先入宗", http_status=400)
        self._require_facility_gate("spirit_mine")
        sect = await self._session.get(Sect, int(character.sect_id))
        if sect is None:
            raise AppError(code=40000, message="宗门不存在", http_status=404)
        await self._org.ensure_sect_org_fields(sect)
        await self.settle_avatar_mining(character, avatar)
        cfg = self._cfg()
        my = cfg.mine_yield or {}
        fl = await self._facility_level(sect.id, "spirit_mine")
        grade_order = int((cfg.sect_grades.get(str(sect.grade or "hut")) or {}).get("order") or 1)
        cap = mine_max_miners(
            grade_order=grade_order,
            facility_level=fl,
            mine_yield=my,
        )
        already = str(avatar.idle_direction or "") == "sect_mining"
        count = await self._miner_count(sect.id)
        if not already and count >= cap:
            raise AppError(code=40000, message=f"采矿名额已满（上限 {cap}）", http_status=400)
        now = now_utc()
        avatar.idle_direction = "sect_mining"
        avatar.last_settled_at = now
        await self._session.flush()

    async def stop_avatar_mining(self, character: Character, avatar: Any) -> dict[str, Any]:
        """化身停止采矿并结算。"""
        settled = await self.settle_avatar_mining(character, avatar)
        if str(getattr(avatar, "idle_direction", "") or "") == "sect_mining":
            avatar.idle_direction = "none"
            await self._session.flush()
        return settled

    async def release_miner_slot(self, character: Character) -> None:
        """离开采矿时释放席位。"""
        miner = (
            await self._session.execute(
                select(SectMineMiner).where(SectMineMiner.character_id == character.id),
            )
        ).scalar_one_or_none()
        if miner is None:
            return
        sect = await self._session.get(Sect, miner.sect_id)
        if sect is not None:
            await self._accrue_mine_pool(sect)
        await self._session.delete(miner)
        if character.idle_direction == "sect_mining":
            character.idle_direction = "none"
        await self._session.flush()

    async def mine_status(self, user: User) -> dict[str, Any]:
        """矿脉状态（被动入库 + 采矿席位）。"""
        require_sect_system_enabled()
        self._require_facility_gate("spirit_mine")
        character, sect, _m = await self._ctx(user)
        await self._org.ensure_sect_org_fields(sect)
        await self.settle_mining_character(character)
        accrued = await self._accrue_mine_pool(sect)
        cfg = self._cfg()
        my = cfg.mine_yield or {}
        fl = await self._facility_level(sect.id, "spirit_mine")
        grade_order = int((cfg.sect_grades.get(str(sect.grade or "hut")) or {}).get("order") or 1)
        miners = await self._miner_count(sect.id)
        cap = mine_max_miners(
            grade_order=grade_order,
            facility_level=fl,
            mine_yield=my,
        )
        rate = mine_pool_rate_per_hour(
            grade_order=grade_order,
            facility_level=fl,
            miner_count=miners,
            mine_yield=my,
        )
        my_miner = (
            await self._session.execute(
                select(SectMineMiner).where(SectMineMiner.character_id == character.id),
            )
        ).scalar_one_or_none()
        return {
            "facility_level": fl,
            "grade_order": grade_order,
            "spirit_stone_pool": int(sect.spirit_stone_pool or 0),
            "pool_rate_per_hour": round(rate, 2),
            "accrued_just_now": accrued,
            "miners": miners,
            "max_miners": cap,
            "mining": my_miner is not None,
            "personal_stones_per_tick": int(my.get("personal_stones_per_tick") or 5),
            "stamina_per_tick": int(my.get("stamina_per_tick") or 2),
            "tick_seconds": int(my.get("tick_seconds") or 60),
            "note_zh": str(my.get("note_zh") or ""),
            "idle_direction": character.idle_direction,
        }

    async def mine_start(self, user: User) -> dict[str, Any]:
        """开始采矿挂机（占名额、切 idle_direction=sect_mining）。"""
        require_sect_system_enabled()
        self._require_facility_gate("spirit_mine")
        character, sect, _m = await self._ctx(user)
        await self._org.ensure_sect_org_fields(sect)
        await self._gate.prepare_for_play(user, settle=True)
        character, sect, _m = await self._ctx(user)
        await self.settle_mining_character(character)
        await self._accrue_mine_pool(sect)

        existing = (
            await self._session.execute(
                select(SectMineMiner).where(SectMineMiner.character_id == character.id),
            )
        ).scalar_one_or_none()
        if existing is not None:
            return {"message": "已在采矿中", "mining": True}

        cfg = self._cfg()
        my = cfg.mine_yield or {}
        fl = await self._facility_level(sect.id, "spirit_mine")
        grade_order = int((cfg.sect_grades.get(str(sect.grade or "hut")) or {}).get("order") or 1)
        cap = mine_max_miners(
            grade_order=grade_order,
            facility_level=fl,
            mine_yield=my,
        )
        if await self._miner_count(sect.id) >= cap:
            raise AppError(code=40000, message=f"采矿名额已满（上限 {cap}）", http_status=400)

        from app.domain.activity_mutex import Activity
        from app.services.craft_service import CraftService

        now = now_utc()
        await CraftService(self._session).settle_jobs_async(character, now=now)
        await self._gate.assert_activity(character, Activity.ENTER_IDLE)
        if character.idle_direction == "sect_mining":
            # 残留方向无席位时清理
            character.idle_direction = "none"

        row = SectMineMiner(
            sect_id=sect.id,
            character_id=character.id,
            started_at=now,
            last_settled_at=now,
        )
        self._session.add(row)
        character.idle_direction = "sect_mining"
        character.last_settled_at = now
        await self._session.flush()
        return {
            "message": "已开始采矿挂机",
            "mining": True,
            "miners": await self._miner_count(sect.id),
            "max_miners": cap,
        }

    async def mine_stop(self, user: User) -> dict[str, Any]:
        """停止采矿挂机。"""
        require_sect_system_enabled()
        self._require_facility_gate("spirit_mine")
        character, sect, _m = await self._ctx(user)
        settled = await self.settle_mining_character(character)
        await self.release_miner_slot(character)
        await self._accrue_mine_pool(sect)
        return {
            "message": "已停止采矿",
            "mining": False,
            "settled": settled,
            "spirit_stone_pool": int(sect.spirit_stone_pool or 0),
        }

    # ----- 灵药园 -----

    async def herb_status(self, user: User) -> dict[str, Any]:
        """灵药园状态。"""
        require_sect_system_enabled()
        self._require_facility_gate("herb_garden")
        character, sect, member = await self._ctx(user)
        await self._org.ensure_sect_org_fields(sect)
        cfg = self._cfg()
        hg = cfg.herb_garden or {}
        fl = await self._facility_level(sect.id, "herb_garden")
        cap = herb_plot_capacity(
            rank=self._rank(member),
            facility_level=fl,
            herb_garden=hg,
        )
        plots = (
            await self._session.execute(
                select(SectHerbPlot).where(
                    SectHerbPlot.sect_id == sect.id,
                    SectHerbPlot.character_id == character.id,
                    SectHerbPlot.status == "growing",
                ),
            )
        ).scalars().all()
        day = self._game_day()
        return {
            "capacity": cap,
            "growing": len(plots),
            "plots": [
                {
                    "id": p.id,
                    "plant_id": p.plant_id,
                    "hosted": bool(getattr(p, "hosted", False)),
                    "herbalist_id": p.herbalist_id,
                    "ready_game_day": p.ready_game_day,
                    "ready": int(p.ready_game_day) <= day,
                }
                for p in plots
            ],
            "plants": [
                {
                    "plant_id": pid,
                    "label_zh": str(body.get("label_zh") or pid),
                    "summary": str(body.get("summary") or ""),
                    "exchange_cost_contribution": int(
                        body.get("exchange_cost_contribution") or 0,
                    ),
                    "plant_cost_contribution": int(
                        body.get("plant_cost_contribution")
                        or body.get("cost_contribution")
                        or 0,
                    ),
                    "grow_game_days": int(body.get("grow_game_days") or 1),
                    "yield_qty": int(body.get("yield_qty") or 1),
                }
                for pid, body in dict(hg.get("plants") or {}).items()
            ],
            "herbalists": [
                {
                    "herbalist_id": hid,
                    "label_zh": str(body.get("label_zh") or hid),
                    "cost_contribution": int(body.get("cost_contribution") or 0),
                }
                for hid, body in dict(hg.get("herbalists") or {}).items()
            ],
            "contrib": int(member.contribution),
            "game_day": day,
        }

    async def herb_exchange(self, user: User, *, plant_id: str) -> dict[str, Any]:
        """直接兑换灵植（贡献换占位产物，不占种植地块）。"""
        require_sect_system_enabled()
        self._require_facility_gate("herb_garden")
        _c, _sect, member = await self._ctx(user)
        plants = dict((self._cfg().herb_garden or {}).get("plants") or {})
        body = plants.get(plant_id)
        if not body:
            raise AppError(code=40000, message="未知灵植", http_status=400)
        cost = int(body.get("exchange_cost_contribution") or 0)
        if cost <= 0:
            raise AppError(code=40000, message="该灵植不可直接兑换", http_status=400)
        await self._apply_contrib(
            member,
            delta=-cost,
            reason="herb_exchange",
            note_zh=f"兑换灵植 {body.get('label_zh') or plant_id}",
        )
        return {
            "message": f"已兑换「{body.get('label_zh') or plant_id}」×{int(body.get('yield_qty') or 1)}",
            "yield_item_id": body.get("yield_item_id"),
            "yield_qty": int(body.get("yield_qty") or 1),
            "contrib": int(member.contribution),
        }

    async def herb_plant(
        self,
        user: User,
        *,
        plant_id: str,
        herbalist_id: str | None = None,
        hosted: bool = False,
    ) -> dict[str, Any]:
        """种植灵植；托管种植须指定灵植师。"""
        require_sect_system_enabled()
        self._require_facility_gate("herb_garden")
        character, sect, member = await self._ctx(user)
        await self._org.ensure_sect_org_fields(sect)
        cfg = self._cfg()
        hg = cfg.herb_garden or {}
        plants = dict(hg.get("plants") or {})
        body = plants.get(plant_id)
        if not body:
            raise AppError(code=40000, message="未知灵植", http_status=400)
        if hosted and not herbalist_id:
            raise AppError(code=40000, message="托管种植须聘请灵植师", http_status=400)
        fl = await self._facility_level(sect.id, "herb_garden")
        cap = herb_plot_capacity(
            rank=self._rank(member),
            facility_level=fl,
            herb_garden=hg,
        )
        growing = (
            await self._session.execute(
                select(SectHerbPlot).where(
                    SectHerbPlot.sect_id == sect.id,
                    SectHerbPlot.character_id == character.id,
                    SectHerbPlot.status == "growing",
                ),
            )
        ).scalars().all()
        if len(growing) >= cap:
            raise AppError(code=40000, message=f"地块已满（上限 {cap}）", http_status=400)
        cost = int(
            body.get("plant_cost_contribution")
            or body.get("cost_contribution")
            or 0,
        )
        if herbalist_id:
            hb = dict(hg.get("herbalists") or {}).get(herbalist_id)
            if not hb:
                raise AppError(code=40000, message="未知灵植师", http_status=400)
            cost += int(hb.get("cost_contribution") or 0)
        await self._apply_contrib(
            member,
            delta=-cost,
            reason="herb_plant_hosted" if hosted else "herb_plant",
            note_zh=(
                f"灵药园{'托管' if hosted else ''}种植 "
                f"{body.get('label_zh') or plant_id}"
            ),
        )
        day = self._game_day()
        grow_days = int(body.get("grow_game_days") or 1)
        plot = SectHerbPlot(
            sect_id=sect.id,
            character_id=character.id,
            plant_id=plant_id,
            herbalist_id=herbalist_id,
            hosted=bool(hosted),
            plant_game_day=day,
            ready_game_day=day + grow_days,
            status="growing",
        )
        self._session.add(plot)
        await self._session.flush()
        return {
            "message": "已开始托管种植" if hosted else "已开始种植",
            "plot_id": plot.id,
            "hosted": bool(hosted),
            "ready_game_day": plot.ready_game_day,
            "contrib": int(member.contribution),
        }

    async def herb_harvest(self, user: User, *, plot_id: int) -> dict[str, Any]:
        """收获灵植。"""
        require_sect_system_enabled()
        self._require_facility_gate("herb_garden")
        character, _sect, _m = await self._ctx(user)
        plot = await self._session.get(SectHerbPlot, int(plot_id))
        if plot is None or plot.character_id != character.id or plot.status != "growing":
            raise AppError(code=40000, message="地块无效", http_status=400)
        day = self._game_day()
        if int(plot.ready_game_day) > day:
            raise AppError(code=40000, message="尚未成熟", http_status=400)
        plot.status = "harvested"
        await self._session.flush()
        plant = dict((self._cfg().herb_garden or {}).get("plants") or {}).get(plot.plant_id) or {}
        return {
            "message": f"已收获「{plant.get('label_zh') or plot.plant_id}」",
            "yield_qty": int(plant.get("yield_qty") or 1),
            "yield_item_id": plant.get("yield_item_id"),
            "hosted": bool(getattr(plot, "hosted", False)),
        }
