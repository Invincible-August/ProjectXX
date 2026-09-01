"""Admin character operations: list/detail/soft-delete/kill/reincarnate/breakthrough/grant/etc."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.admin_character import (
    AUDIT_DOMAIN_PLAYER_CHARACTERS,
    BASE_ATTR_EDIT_KEYS,
    BASE_ATTR_LABEL_ZH,
    CHARACTER_CURRENCY_DEFS,
    CHARACTER_DEFAULT_PAGE_SIZE,
    CHARACTER_PAGE_SIZES,
    CURRENCY_REINCARNATION_POINTS,
    CURRENCY_SPIRIT_STONES,
    CURRENCY_TIANDAO_POINTS,
    build_character_ops_schema,
)
from app.constants.character import (
    CHARACTER_STATUS_ADMIN_CHOICES,
    CHARACTER_STATUS_AWAITING_FERRY,
    CHARACTER_STATUS_LABEL_ZH,
    CRAFT_BRANCH_ARRAY,
    CRAFT_BRANCH_LABEL_ZH,
    CRAFT_BRANCHES,
    GROWTH_ATTR_CRAFT_LEVELS_KEY,
)
from app.core.time_utils import to_utc_iso
from app.db.models import (
    AdminAuditLog,
    AdminUser,
    Character,
    CharacterCraftKnowledge,
    CharacterTechnique,
    ConstitutionItem,
    ConstitutionSlot,
    InventoryItem,
    User,
)
from app.domain.body_temper import build_body_temper_public
from app.domain.reincarnation_rules import parse_growth_attrs
from app.schemas.common import AppError
from app.services.admin_rbac import can_publish, can_view, parse_roles
from app.services.currency_ledger_service import CurrencyLedgerService
from app.services.ferry_service import FerryService
from app.services.inventory_service import InventoryService
from app.services.mail_service import MailService
from app.services.realm_config import (
    build_realm_display,
    get_current_stage,
    get_game_config,
    get_major_realm,
)
from app.services.reincarnation_service import ReincarnationService
from app.services.technique_service import TechniqueService

logger = logging.getLogger(__name__)


class AdminCharacterService:
    """Runtime character ops for the admin console (not config overlay)."""

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: Async SQLAlchemy session (caller owns commit).
        """
        self._session = session
        self._inv = InventoryService(session)
        self._ledger = CurrencyLedgerService(session)
        self._mail = MailService(session)
        self._ferry = FerryService(session)
        self._reinc = ReincarnationService(session)
        self._tech = TechniqueService(session)

    def assert_can_view(self, admin: AdminUser) -> None:
        """Require view permission for character ops."""
        if not can_view(parse_roles(admin.roles)):
            raise AppError(code=40300, message="forbidden", http_status=403)

    def assert_can_ops(self, admin: AdminUser) -> None:
        """Require publisher/admin for mutating character ops."""
        if not can_publish(parse_roles(admin.roles)):
            raise AppError(
                code=40300,
                message="forbidden: publisher/admin required",
                http_status=403,
            )

    def get_ops_schema(self, admin: AdminUser) -> dict[str, Any]:
        """Return field schema for the character ops UI."""
        self.assert_can_view(admin)
        return build_character_ops_schema()

    async def _audit(
        self,
        admin: AdminUser,
        *,
        action: str,
        character_id: int,
        detail: dict[str, Any] | None = None,
    ) -> None:
        """Append an admin_audit_logs row (no target_id column)."""
        summary = f"character_id={character_id}"
        if detail:
            summary = f"{summary} {json.dumps(detail, ensure_ascii=False)}"[:1024]
        self._session.add(
            AdminAuditLog(
                admin_user_id=admin.id,
                username=admin.username,
                action=action,
                domain_id=AUDIT_DOMAIN_PLAYER_CHARACTERS,
                summary=summary,
                detail_json=json.dumps(
                    {"character_id": character_id, **(detail or {})},
                    ensure_ascii=False,
                ),
            ),
        )

    def _status_label(self, status: str) -> str:
        """Map status key to display label."""
        return CHARACTER_STATUS_LABEL_ZH.get(status, status)

    def _serialize_list_row(
        self,
        character: Character,
        user: User | None,
    ) -> dict[str, Any]:
        """Serialize one list-grid row DTO."""
        status = str(character.status or "normal")
        return {
            "id": int(character.id),
            "name": character.name,
            "user_db_id": int(character.user_id),
            "user_id": (user.public_uid if user else None) or "",
            "major_realm": character.major_realm,
            "major_realm_name": (
                get_major_realm(character.major_realm).name
                if get_major_realm(character.major_realm)
                else character.major_realm
            ),
            "realm_stage": int(character.realm_stage),
            "realm_stage_label": character.realm_stage_label,
            "realm_display": build_realm_display(
                character.major_realm,
                character.realm_stage_label,
            ),
            "body_temper_stage": character.body_temper_stage,
            "body_temper_layer": int(character.body_temper_layer),
            "status": status,
            "status_label_zh": self._status_label(status),
            "spirit_stones": int(character.spirit_stones),
            "cultivation_points": int(character.cultivation_points),
            "is_active": bool(getattr(character, "is_active", True)),
            "created_at": to_utc_iso(character.created_at),
        }

    def _craft_levels(self, character: Character) -> dict[str, int]:
        """Read craft branch levels; array uses character.array_craft_level."""
        from app.domain.craft_rules import read_craft_levels

        return read_craft_levels(
            growth_attrs=parse_growth_attrs(character.growth_attrs_json),
            array_craft_level=int(getattr(character, "array_craft_level", 0) or 0),
        )

    def _write_craft_levels(self, character: Character, levels: dict[str, int]) -> None:
        """Persist craft levels into growth_attrs_json and array column."""
        growth = parse_growth_attrs(character.growth_attrs_json)
        cleaned: dict[str, int] = {}
        for branch in CRAFT_BRANCHES:
            val = max(0, int(levels.get(branch, 0)))
            cleaned[branch] = val
            if branch == CRAFT_BRANCH_ARRAY:
                character.array_craft_level = val
        growth[GROWTH_ATTR_CRAFT_LEVELS_KEY] = cleaned
        character.growth_attrs_json = json.dumps(growth, ensure_ascii=False)

    def _base_attrs(self, character: Character) -> list[dict[str, Any]]:
        """Read editable base attrs from growth_attrs_json."""
        growth = parse_growth_attrs(character.growth_attrs_json)
        cfg = get_game_config().combat_attrs
        rows: list[dict[str, Any]] = []
        for key in BASE_ATTR_EDIT_KEYS:
            default = 0
            if key in cfg.attrs:
                default = cfg.attrs[key].default
            raw = growth.get(key, default)
            try:
                if key == "breath_efficiency":
                    value: float | int = float(raw)
                else:
                    value = int(raw)
            except (TypeError, ValueError):
                value = float(default) if key == "breath_efficiency" else int(default)
            rows.append(
                {
                    "key": key,
                    "label_zh": BASE_ATTR_LABEL_ZH.get(key, key),
                    "value": value,
                },
            )
        return rows

    async def _get_character(self, character_id: int) -> Character:
        """
        Load character by id and refresh to avoid MissingGreenlet after flush
        when accessing updated_at / lazy attrs.
        """
        row = (
            await self._session.execute(
                select(Character).where(Character.id == int(character_id)),
            )
        ).scalar_one_or_none()
        if row is None:
            raise AppError(code=40400, message="character not found", http_status=404)
        await self._session.refresh(row)
        return row

    async def list_characters(
        self,
        admin: AdminUser,
        *,
        q: str | None = None,
        page: int = 1,
        page_size: int = 20,
        user_db_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Paginated character search.

        Args:
            admin: Admin actor.
            q: Name / user_id / email / phone / numeric id.
            page: 1-based page.
            page_size: Page size from allowed set.
            user_db_id: Optional filter by users.id.
        """
        self.assert_can_view(admin)
        page = max(1, int(page))
        page_size = int(page_size) if page_size else CHARACTER_DEFAULT_PAGE_SIZE
        if page_size not in CHARACTER_PAGE_SIZES:
            raise AppError(
                code=40000,
                message=f"page_size must be one of {'/'.join(str(n) for n in CHARACTER_PAGE_SIZES)}",
                http_status=400,
            )

        filters: list[Any] = []
        if user_db_id is not None:
            filters.append(Character.user_id == int(user_db_id))
        keyword = (q or "").strip()
        if keyword:
            like = f"%{keyword.lower()}%"
            or_parts: list[Any] = [
                func.lower(Character.name).like(like),
                func.lower(User.public_uid).like(like),
                func.lower(User.email).like(like),
                func.lower(User.phone).like(like),
            ]
            if keyword.isdigit():
                or_parts.append(Character.id == int(keyword))
                or_parts.append(User.id == int(keyword))
            filters.append(or_(*or_parts))

        count_stmt = (
            select(func.count())
            .select_from(Character)
            .outerjoin(User, User.id == Character.user_id)
        )
        list_stmt = (
            select(Character, User)
            .outerjoin(User, User.id == Character.user_id)
            .order_by(Character.id.desc())
        )
        if filters:
            count_stmt = count_stmt.where(*filters)
            list_stmt = list_stmt.where(*filters)

        total = int((await self._session.execute(count_stmt)).scalar_one())
        rows = (
            await self._session.execute(
                list_stmt.offset((page - 1) * page_size).limit(page_size),
            )
        ).all()
        items = [self._serialize_list_row(ch, user) for ch, user in rows]
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def get_detail(self, admin: AdminUser, character_id: int) -> dict[str, Any]:
        """Full character detail for the ops console."""
        self.assert_can_view(admin)
        character = await self._get_character(character_id)
        user = await self._session.get(User, character.user_id)
        base = self._serialize_list_row(character, user)
        body = build_body_temper_public(character)
        growth = parse_growth_attrs(character.growth_attrs_json)

        techniques = await self._list_techniques(character)
        bags = await self._inv.list_bags(character)
        recipes = await self._list_recipes(character)
        constitutions = await self._list_constitutions(character)
        craft_levels = self._craft_levels(character)
        currencies = []
        for cur in CHARACTER_CURRENCY_DEFS:
            key = cur["key"]
            if key == CURRENCY_SPIRIT_STONES:
                amount = int(character.spirit_stones)
            elif key == CURRENCY_TIANDAO_POINTS:
                amount = int(character.tiandao_points)
            else:
                amount = int(character.reincarnation_points)
            currencies.append(
                {
                    "key": key,
                    "label_zh": cur["label_zh"],
                    "help_zh": cur["help_zh"],
                    "amount": amount,
                },
            )

        return {
            **base,
            "email": user.email if user else None,
            "phone": user.phone if user else None,
            "realm_progress": int(character.realm_progress),
            "body_tempering_points": int(character.body_tempering_points),
            "body_temper_progress": int(character.body_temper_progress),
            "body_temper_display": body.get("body_temper_display"),
            "crafting_exp": int(character.crafting_exp),
            "stamina": int(character.stamina),
            "breakthrough_grade": character.breakthrough_grade,
            "idle_direction": character.idle_direction,
            "reincarnation_count": int(character.reincarnation_count),
            "peak_major_realm": character.peak_major_realm,
            "ferry_deadline_at": to_utc_iso(character.ferry_deadline_at)
            if character.ferry_deadline_at
            else None,
            "fate_luck_readonly": int(character.fate_luck),
            "demonic_nature": int(character.demonic_nature),
            "base_attrs": self._base_attrs(character),
            "growth_attrs": growth,
            "craft_levels": [
                {
                    "branch": b,
                    "label_zh": CRAFT_BRANCH_LABEL_ZH.get(b, b),
                    "level": craft_levels[b],
                }
                for b in CRAFT_BRANCHES
            ],
            "currencies": currencies,
            "techniques": techniques,
            "inventory": bags,
            "recipes_by_branch": recipes,
            "constitution": constitutions,
            "updated_at": to_utc_iso(character.updated_at),
        }

    async def _list_techniques(self, character: Character) -> list[dict[str, Any]]:
        """List learned techniques for the character."""
        rows = (
            await self._session.execute(
                select(CharacterTechnique)
                .where(CharacterTechnique.character_id == character.id)
                .order_by(CharacterTechnique.technique_id),
            )
        ).scalars().all()
        cfg = get_game_config().techniques
        out: list[dict[str, Any]] = []
        for row in rows:
            tech = cfg.get(row.technique_id)
            out.append(
                {
                    "id": int(row.id),
                    "technique_id": row.technique_id,
                    "name": tech.name if tech else row.technique_id,
                    "level": int(row.level),
                    "track": getattr(tech, "track", None) if tech else None,
                },
            )
        return out

    async def _list_recipes(self, character: Character) -> dict[str, list[dict[str, Any]]]:
        """List unlocked craft recipes grouped by branch."""
        rows = (
            await self._session.execute(
                select(CharacterCraftKnowledge)
                .where(CharacterCraftKnowledge.character_id == character.id)
                .order_by(CharacterCraftKnowledge.recipe_id),
            )
        ).scalars().all()
        recipes_cfg = get_game_config().craft_recipes.recipes
        by_branch: dict[str, list[dict[str, Any]]] = {b: [] for b in CRAFT_BRANCHES}
        by_branch["other"] = []
        for row in rows:
            recipe = recipes_cfg.get(row.recipe_id)
            branch = str(getattr(recipe, "branch", None) or "other")
            item = {
                "id": int(row.id),
                "recipe_id": row.recipe_id,
                "name": recipe.name if recipe else row.recipe_id,
                "branch": branch,
                "source": row.source,
                "unlocked_at": to_utc_iso(row.unlocked_at),
            }
            if branch in by_branch:
                by_branch[branch].append(item)
            else:
                by_branch["other"].append(item)
        return by_branch

    async def _list_constitutions(self, character: Character) -> dict[str, Any]:
        """List constitution items and slots."""
        items = (
            await self._session.execute(
                select(ConstitutionItem)
                .where(ConstitutionItem.character_id == character.id)
                .order_by(ConstitutionItem.id),
            )
        ).scalars().all()
        slots = (
            await self._session.execute(
                select(ConstitutionSlot)
                .where(ConstitutionSlot.character_id == character.id)
                .order_by(ConstitutionSlot.slot_type, ConstitutionSlot.slot_index),
            )
        ).scalars().all()
        return {
            "items": [
                {
                    "id": int(i.id),
                    "def_id": i.def_id,
                    "quality": i.quality,
                    "grade": i.grade,
                    "kind": i.kind,
                    "is_equipped": bool(i.is_equipped),
                }
                for i in items
            ],
            "slots": [
                {
                    "id": int(s.id),
                    "slot_type": s.slot_type,
                    "slot_index": int(s.slot_index),
                    "item_instance_id": s.item_instance_id,
                }
                for s in slots
            ],
        }

    async def soft_delete(
        self,
        admin: AdminUser,
        character_id: int,
        *,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Soft-delete: set is_active=False."""
        self.assert_can_ops(admin)
        character = await self._get_character(character_id)
        character.is_active = False
        await self._audit(
            admin,
            action="ops.character.soft_delete",
            character_id=character.id,
            detail={"note": note},
        )
        await self._session.flush()
        return await self.get_detail(admin, character.id)

    async def kill_to_ferry(
        self,
        admin: AdminUser,
        character_id: int,
        *,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Force death into awaiting_ferry via FerryService."""
        self.assert_can_ops(admin)
        character = await self._get_character(character_id)
        await self._ferry.enter_awaiting_ferry(character)
        await self._audit(
            admin,
            action="ops.character.kill",
            character_id=character.id,
            detail={"note": note, "status": CHARACTER_STATUS_AWAITING_FERRY},
        )
        await self._session.flush()
        return await self.get_detail(admin, character.id)

    async def force_reincarnation(
        self,
        admin: AdminUser,
        character_id: int,
        *,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Force reincarnation with path=forced."""
        self.assert_can_ops(admin)
        character = await self._get_character(character_id)
        await self._reinc.apply_reincarnation(character, path="forced")
        await self._audit(
            admin,
            action="ops.character.reincarnate",
            character_id=character.id,
            detail={"note": note, "path": "forced"},
        )
        await self._session.flush()
        return await self.get_detail(admin, character.id)

    def _advance_cultivation_minor(self, character: Character) -> None:
        """Advance one cultivation minor stage; zero progress pools."""
        major = get_major_realm(character.major_realm)
        if major is None:
            raise AppError(code=40000, message="invalid major realm", http_status=400)
        next_num = int(character.realm_stage) + 1
        next_stage = major.stage_by_number(next_num)
        if next_stage is not None:
            character.realm_stage = next_stage.stage
            character.realm_stage_label = next_stage.label
        elif major.next_major:
            nxt = get_major_realm(major.next_major)
            if nxt is None or not nxt.stages:
                raise AppError(code=40000, message="next major realm missing", http_status=400)
            first = nxt.stages[0]
            character.major_realm = nxt.key
            character.realm_stage = first.stage
            character.realm_stage_label = first.label
            peak = str(character.peak_major_realm or "")
            order = list(get_game_config().realms.keys())
            if nxt.key in order and (peak not in order or order.index(nxt.key) > order.index(peak)):
                character.peak_major_realm = nxt.key
        else:
            raise AppError(code=40000, message="already at max cultivation", http_status=400)
        character.realm_progress = 0
        character.cultivation_points = 0

    def _advance_body_temper_minor(self, character: Character) -> None:
        """Advance one body-temper minor layer; zero progress pools."""
        cfg = get_game_config().body_temper
        major_id = str(character.body_temper_stage or cfg.default_major_id)
        major = cfg.majors.get(major_id)
        if major is None:
            raise AppError(code=40000, message="invalid body temper major", http_status=400)
        next_num = int(character.body_temper_layer) + 1
        next_layer = major.stage_by_number(next_num)
        if next_layer is not None:
            character.body_temper_layer = next_layer.stage
            character.body_temper_layer_label = next_layer.label
        elif major.next_major:
            nxt = cfg.majors.get(major.next_major)
            if nxt is None or not nxt.stages:
                raise AppError(code=40000, message="next body temper major missing", http_status=400)
            first = nxt.stages[0]
            character.body_temper_stage = nxt.key
            character.body_temper_layer = first.stage
            character.body_temper_layer_label = first.label
        else:
            raise AppError(code=40000, message="already at max body temper", http_status=400)
        character.body_temper_progress = 0
        character.body_tempering_points = 0

    async def breakthrough_cultivation(
        self,
        admin: AdminUser,
        character_id: int,
        *,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Admin force-breakthrough on cultivation track."""
        self.assert_can_ops(admin)
        character = await self._get_character(character_id)
        before = {
            "major_realm": character.major_realm,
            "realm_stage": character.realm_stage,
        }
        self._advance_cultivation_minor(character)
        await self._audit(
            admin,
            action="ops.character.breakthrough_cultivation",
            character_id=character.id,
            detail={"note": note, "before": before},
        )
        await self._session.flush()
        return await self.get_detail(admin, character.id)

    async def breakthrough_body_temper(
        self,
        admin: AdminUser,
        character_id: int,
        *,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Admin force-breakthrough on body temper track."""
        self.assert_can_ops(admin)
        character = await self._get_character(character_id)
        before = {
            "body_temper_stage": character.body_temper_stage,
            "body_temper_layer": character.body_temper_layer,
        }
        self._advance_body_temper_minor(character)
        await self._audit(
            admin,
            action="ops.character.breakthrough_body",
            character_id=character.id,
            detail={"note": note, "before": before},
        )
        await self._session.flush()
        return await self.get_detail(admin, character.id)

    async def grant_item_mail(
        self,
        admin: AdminUser,
        character_id: int,
        *,
        item_id: str,
        quantity: int = 1,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Grant item via system mail (MailService.send_system)."""
        self.assert_can_ops(admin)
        character = await self._get_character(character_id)
        if not bool(getattr(character, "is_active", True)):
            raise AppError(code=40000, message="character is inactive", http_status=400)
        item_id = str(item_id or "").strip()
        if not item_id:
            raise AppError(code=40000, message="item_id required", http_status=400)
        qty = int(quantity)
        if qty < 1:
            raise AppError(code=40000, message="quantity must be >= 1", http_status=400)
        inv_cfg = get_game_config().inventory
        defn = inv_cfg.items.get(item_id)
        if defn is None:
            raise AppError(code=40000, message=f"item not found: {item_id}", http_status=404)
        item_type = str(getattr(defn, "item_type", None) or getattr(defn, "type", "material"))
        if bool(getattr(defn, "unique", False)) and qty != 1:
            raise AppError(code=40000, message="unique item quantity must be 1", http_status=400)
        body = note or f"Admin grant: {getattr(defn, 'name', item_id)} x{qty}"
        await self._mail.send_system(
            to_character_id=character.id,
            subject_zh="Admin Grant",
            body_zh=body,
            reason="admin_grant",
            items=[{"item_id": item_id, "item_type": item_type, "quantity": qty}],
        )
        await self._audit(
            admin,
            action="ops.character.grant_item",
            character_id=character.id,
            detail={"item_id": item_id, "quantity": qty, "note": note},
        )
        await self._session.flush()
        return await self.get_detail(admin, character.id)

    async def grant_technique_craft_test_cards(
        self,
        admin: AdminUser,
        character_id: int,
        *,
        note: str | None = None,
    ) -> dict[str, Any]:
        """
        直接入包发放功法自研联调卡：无限属性正式卡 + 无限效能正式卡各一张。

        不走邮件（正式卡须带 meta）；镶嵌时不消耗。供管理后台「角色管理」使用。

        Args:
            admin: 当前后台账号。
            character_id: 目标角色 id。
            note: 可选审计备注。

        Returns:
            dict[str, Any]: 角色详情。

        Raises:
            AppError: 角色不存在或无权。
        """
        from app.constants.technique_craft import (
            CARD_FORMAL_EFFICACY_INF_ID,
            CARD_FORMAL_ELEMENT_INF_ID,
            INF_EFFICACY_CARD_META,
            INF_ELEMENT_CARD_META,
        )
        from app.services.inventory_service import InventoryService

        self.assert_can_ops(admin)
        character = await self._get_character(character_id)
        if not bool(getattr(character, "is_active", True)):
            raise AppError(code=40000, message="角色已删除", http_status=400)
        inv = InventoryService(self._session)
        await inv.add_item(
            character.id,
            item_type="consumable",
            item_id=CARD_FORMAL_ELEMENT_INF_ID,
            quantity=1,
            meta=dict(INF_ELEMENT_CARD_META),
        )
        await inv.add_item(
            character.id,
            item_type="consumable",
            item_id=CARD_FORMAL_EFFICACY_INF_ID,
            quantity=1,
            meta=dict(INF_EFFICACY_CARD_META),
        )
        await self._audit(
            admin,
            action="ops.character.grant_technique_craft_test_cards",
            character_id=character.id,
            detail={
                "note": note,
                "items": [CARD_FORMAL_ELEMENT_INF_ID, CARD_FORMAL_EFFICACY_INF_ID],
            },
        )
        await self._session.flush()
        return await self.get_detail(admin, character.id)

    async def update_base_attrs(
        self,
        admin: AdminUser,
        character_id: int,
        *,
        attrs: dict[str, Any],
    ) -> dict[str, Any]:
        """Update base attrs stored in growth_attrs_json."""
        self.assert_can_ops(admin)
        character = await self._get_character(character_id)
        growth = parse_growth_attrs(character.growth_attrs_json)
        for key, raw in (attrs or {}).items():
            if key not in BASE_ATTR_EDIT_KEYS:
                raise AppError(code=40000, message=f"invalid attr key: {key}", http_status=400)
            if key == "breath_efficiency":
                growth[key] = float(raw)
            else:
                growth[key] = int(raw)
        character.growth_attrs_json = json.dumps(growth, ensure_ascii=False)
        await self._audit(
            admin,
            action="ops.character.update_base_attrs",
            character_id=character.id,
            detail={"attrs": attrs},
        )
        await self._session.flush()
        return await self.get_detail(admin, character.id)

    async def update_status(
        self,
        admin: AdminUser,
        character_id: int,
        *,
        status: str,
    ) -> dict[str, Any]:
        """Set character status from CHARACTER_STATUS_ADMIN_CHOICES."""
        self.assert_can_ops(admin)
        character = await self._get_character(character_id)
        status = str(status or "").strip()
        if status not in CHARACTER_STATUS_ADMIN_CHOICES:
            raise AppError(code=40000, message="invalid status", http_status=400)
        # Leaving awaiting_ferry clears the ferry deadline.
        if character.status == CHARACTER_STATUS_AWAITING_FERRY:
            character.ferry_deadline_at = None
        character.status = status
        await self._audit(
            admin,
            action="ops.character.update_status",
            character_id=character.id,
            detail={"status": status},
        )
        await self._session.flush()
        return await self.get_detail(admin, character.id)

    async def update_inventory_item(
        self,
        admin: AdminUser,
        character_id: int,
        item_row_id: int,
        *,
        quantity: int | None = None,
        meta: dict[str, Any] | None = None,
        delete: bool = False,
    ) -> dict[str, Any]:
        """Update or delete an inventory row."""
        self.assert_can_ops(admin)
        character = await self._get_character(character_id)
        row = await self._session.get(InventoryItem, int(item_row_id))
        if row is None or int(row.character_id) != int(character.id):
            raise AppError(code=40400, message="inventory item not found", http_status=404)
        if delete:
            await self._session.delete(row)
        else:
            if quantity is not None:
                qty = int(quantity)
                if qty < 1:
                    raise AppError(
                        code=40000,
                        message="quantity must be >= 1; use delete to remove",
                        http_status=400,
                    )
                inv_cfg = get_game_config().inventory
                defn = inv_cfg.items.get(row.item_id)
                unique = bool(getattr(defn, "unique", False)) if defn else False
                max_stack = int(defn.max_stack) if defn else 1
                if unique and qty != 1:
                    raise AppError(code=40000, message="unique item quantity must be 1", http_status=400)
                if max_stack <= 1 and qty != 1:
                    raise AppError(code=40000, message="non-stackable quantity must be 1", http_status=400)
                if qty > max_stack:
                    raise AppError(
                        code=40000,
                        message=f"quantity exceeds max_stack {max_stack}",
                        http_status=400,
                    )
                row.quantity = qty
            if meta is not None:
                row.meta_json = json.dumps(meta, ensure_ascii=False)
        await self._audit(
            admin,
            action="ops.character.update_inventory",
            character_id=character.id,
            detail={
                "item_row_id": item_row_id,
                "quantity": quantity,
                "delete": delete,
                "meta": meta,
            },
        )
        await self._session.flush()
        return await self.get_detail(admin, character.id)

    async def update_technique_level(
        self,
        admin: AdminUser,
        character_id: int,
        technique_id: str,
        *,
        level: int,
    ) -> dict[str, Any]:
        """Set level of an already-learned technique."""
        self.assert_can_ops(admin)
        character = await self._get_character(character_id)
        row = (
            await self._session.execute(
                select(CharacterTechnique).where(
                    CharacterTechnique.character_id == character.id,
                    CharacterTechnique.technique_id == technique_id,
                ),
            )
        ).scalar_one_or_none()
        if row is None:
            raise AppError(code=40400, message="technique not learned", http_status=404)
        if int(level) < 0:
            raise AppError(code=40000, message="level must be >= 0", http_status=400)
        row.level = int(level)
        await self._audit(
            admin,
            action="ops.character.update_technique",
            character_id=character.id,
            detail={"technique_id": technique_id, "level": level},
        )
        await self._session.flush()
        return await self.get_detail(admin, character.id)

    async def learn_technique(
        self,
        admin: AdminUser,
        character_id: int,
        *,
        technique_id: str,
        level: int = 0,
    ) -> dict[str, Any]:
        """Grant a technique to the character."""
        self.assert_can_ops(admin)
        character = await self._get_character(character_id)
        tid = str(technique_id or "").strip()
        if tid not in get_game_config().techniques:
            raise AppError(code=40000, message=f"technique not found: {tid}", http_status=404)
        existing = (
            await self._session.execute(
                select(CharacterTechnique).where(
                    CharacterTechnique.character_id == character.id,
                    CharacterTechnique.technique_id == tid,
                ),
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise AppError(code=40000, message="technique already learned", http_status=400)
        self._session.add(
            CharacterTechnique(
                character_id=character.id,
                technique_id=tid,
                level=max(0, int(level)),
                source="system",
            ),
        )
        await self._audit(
            admin,
            action="ops.character.learn_technique",
            character_id=character.id,
            detail={"technique_id": tid, "level": level},
        )
        await self._session.flush()
        return await self.get_detail(admin, character.id)

    async def forget_technique(
        self,
        admin: AdminUser,
        character_id: int,
        technique_id: str,
    ) -> dict[str, Any]:
        """Remove a learned technique."""
        self.assert_can_ops(admin)
        character = await self._get_character(character_id)
        row = (
            await self._session.execute(
                select(CharacterTechnique).where(
                    CharacterTechnique.character_id == character.id,
                    CharacterTechnique.technique_id == technique_id,
                ),
            )
        ).scalar_one_or_none()
        if row is None:
            raise AppError(code=40400, message="technique not learned", http_status=404)
        await self._session.delete(row)
        await self._audit(
            admin,
            action="ops.character.forget_technique",
            character_id=character.id,
            detail={"technique_id": technique_id},
        )
        await self._session.flush()
        return await self.get_detail(admin, character.id)

    async def update_realm(
        self,
        admin: AdminUser,
        character_id: int,
        *,
        track: str,
        major: str | None = None,
        stage: int | None = None,
        progress: int | None = None,
        pool_points: int | None = None,
    ) -> dict[str, Any]:
        """
        Directly set realm / body temper fields.

        Args:
            track: ``cultivation`` or ``body``.
        """
        self.assert_can_ops(admin)
        character = await self._get_character(character_id)
        track = str(track or "").strip()
        if track == "cultivation":
            if major is not None:
                if get_major_realm(major) is None:
                    raise AppError(
                        code=40000,
                        message=f"invalid major realm: {major}",
                        http_status=400,
                    )
                character.major_realm = major
            if stage is not None:
                st = get_current_stage(character.major_realm, int(stage))
                if st is None:
                    raise AppError(code=40000, message="invalid realm stage", http_status=400)
                character.realm_stage = st.stage
                character.realm_stage_label = st.label
            if progress is not None:
                if int(progress) < 0:
                    raise AppError(code=40000, message="progress must be >= 0", http_status=400)
                character.realm_progress = int(progress)
            if pool_points is not None:
                if int(pool_points) < 0:
                    raise AppError(code=40000, message="pool_points must be >= 0", http_status=400)
                character.cultivation_points = int(pool_points)
        elif track == "body":
            cfg = get_game_config().body_temper
            if major is not None:
                if major not in cfg.majors:
                    raise AppError(
                        code=40000,
                        message=f"invalid body temper major: {major}",
                        http_status=400,
                    )
                character.body_temper_stage = major
            if stage is not None:
                maj = cfg.majors.get(character.body_temper_stage)
                if maj is None:
                    raise AppError(code=40000, message="invalid body temper major", http_status=400)
                layer = maj.stage_by_number(int(stage))
                if layer is None:
                    raise AppError(
                        code=40000,
                        message="invalid body temper layer",
                        http_status=400,
                    )
                character.body_temper_layer = layer.stage
                character.body_temper_layer_label = layer.label
            if progress is not None:
                if int(progress) < 0:
                    raise AppError(
                        code=40000,
                        message="progress must be >= 0",
                        http_status=400,
                    )
                character.body_temper_progress = int(progress)
            if pool_points is not None:
                if int(pool_points) < 0:
                    raise AppError(code=40000, message="pool_points must be >= 0", http_status=400)
                character.body_tempering_points = int(pool_points)
        else:
            raise AppError(code=40000, message="track must be cultivation or body", http_status=400)
        await self._audit(
            admin,
            action="ops.character.update_realm",
            character_id=character.id,
            detail={
                "track": track,
                "major": major,
                "stage": stage,
                "progress": progress,
                "pool_points": pool_points,
            },
        )
        await self._session.flush()
        return await self.get_detail(admin, character.id)

    async def update_craft_levels(
        self,
        admin: AdminUser,
        character_id: int,
        *,
        levels: dict[str, int],
    ) -> dict[str, Any]:
        """Update craft branch levels."""
        self.assert_can_ops(admin)
        character = await self._get_character(character_id)
        current = self._craft_levels(character)
        for branch, val in (levels or {}).items():
            if branch not in CRAFT_BRANCHES:
                raise AppError(
                    code=40000,
                    message=f"invalid craft branch: {branch}",
                    http_status=400,
                )
            if int(val) < 0:
                raise AppError(code=40000, message="craft level must be >= 0", http_status=400)
            current[branch] = int(val)
        self._write_craft_levels(character, current)
        await self._audit(
            admin,
            action="ops.character.update_craft_levels",
            character_id=character.id,
            detail={"levels": current},
        )
        await self._session.flush()
        return await self.get_detail(admin, character.id)

    async def learn_recipe(
        self,
        admin: AdminUser,
        character_id: int,
        *,
        recipe_id: str,
    ) -> dict[str, Any]:
        """Unlock a craft recipe."""
        self.assert_can_ops(admin)
        character = await self._get_character(character_id)
        rid = str(recipe_id or "").strip()
        if rid not in get_game_config().craft_recipes.recipes:
            raise AppError(code=40000, message=f"recipe not found: {rid}", http_status=404)
        existing = (
            await self._session.execute(
                select(CharacterCraftKnowledge.id).where(
                    CharacterCraftKnowledge.character_id == character.id,
                    CharacterCraftKnowledge.recipe_id == rid,
                ),
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise AppError(code=40000, message="recipe already learned", http_status=400)
        self._session.add(
            CharacterCraftKnowledge(
                character_id=character.id,
                recipe_id=rid,
                source="admin",
            ),
        )
        await self._audit(
            admin,
            action="ops.character.learn_recipe",
            character_id=character.id,
            detail={"recipe_id": rid},
        )
        await self._session.flush()
        return await self.get_detail(admin, character.id)

    async def forget_recipe(
        self,
        admin: AdminUser,
        character_id: int,
        recipe_id: str,
    ) -> dict[str, Any]:
        """Remove an unlocked craft recipe."""
        self.assert_can_ops(admin)
        character = await self._get_character(character_id)
        row = (
            await self._session.execute(
                select(CharacterCraftKnowledge).where(
                    CharacterCraftKnowledge.character_id == character.id,
                    CharacterCraftKnowledge.recipe_id == recipe_id,
                ),
            )
        ).scalar_one_or_none()
        if row is None:
            raise AppError(code=40400, message="recipe not found", http_status=404)
        await self._session.delete(row)
        await self._audit(
            admin,
            action="ops.character.forget_recipe",
            character_id=character.id,
            detail={"recipe_id": recipe_id},
        )
        await self._session.flush()
        return await self.get_detail(admin, character.id)

    async def update_currencies(
        self,
        admin: AdminUser,
        character_id: int,
        *,
        amounts: dict[str, int],
    ) -> dict[str, Any]:
        """Set currency amounts (>= 0). fate_luck is not editable here."""
        self.assert_can_ops(admin)
        character = await self._get_character(character_id)
        allowed = {c["key"] for c in CHARACTER_CURRENCY_DEFS}
        for key, raw in (amounts or {}).items():
            if key not in allowed:
                raise AppError(
                    code=40000,
                    message=f"invalid currency key: {key}",
                    http_status=400,
                )
            if isinstance(raw, float) and not float(raw).is_integer():
                raise AppError(code=40000, message="currency must be integer", http_status=400)
            val = int(raw)
            if val < 0:
                raise AppError(code=40000, message="currency must be >= 0", http_status=400)
            if key == CURRENCY_SPIRIT_STONES:
                character.spirit_stones = val
            elif key == CURRENCY_TIANDAO_POINTS:
                character.tiandao_points = val
            elif key == CURRENCY_REINCARNATION_POINTS:
                character.reincarnation_points = val
        await self._audit(
            admin,
            action="ops.character.update_currencies",
            character_id=character.id,
            detail={"amounts": amounts},
        )
        await self._session.flush()
        return await self.get_detail(admin, character.id)
