"""
Research session service (formation / talisman; technique uses TechniqueCraftService).
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.research import (
    DICE_PURPOSE_RESEARCH_FORMATION,
    DICE_PURPOSE_RESEARCH_TALISMAN,
    DICE_PURPOSE_RESEARCH_TECHNIQUE,
    ERR_RESEARCH_MATERIALS,
    ERR_RESEARCH_FROZEN,
    ERR_RESEARCH_OWNER,
    ERR_RESEARCH_REVIEW_CLOSED,
    ERR_RESEARCH_SESSION,
    ERR_RESEARCH_THRESHOLD,
    ERR_RESEARCH_VALIDATE,
    ERR_RESEARCH_WHITELIST,
    PRIVATE_ID_PREFIX,
    RESEARCH_KIND_FORMATION,
    RESEARCH_KIND_LABELS_ZH,
    RESEARCH_KIND_TALISMAN,
    RESEARCH_KIND_TECHNIQUE,
    RESEARCH_PHASE_DRAFTING,
    RESEARCH_PHASE_EXPIRED,
    RESEARCH_PHASE_FINALIZED,
    RESEARCH_PHASE_LABELS_ZH,
    RESEARCH_PHASE_PREVIEWED,
    RESEARCH_SOURCE_CUSTOM,
    SOURCE_LABEL_CUSTOM_ZH,
)
from app.constants.technique import (
    normalize_technique_source,
    technique_source_label_zh,
)
from app.core.time_utils import ensure_aware_utc, now_utc
from app.db.models.character import Character
from app.db.models.research import (
    PrivateFormation,
    PrivateTalisman,
    PrivateTechnique,
    ResearchSession,
)
from app.db.models.technique import CharacterTechnique
from app.domain.formation_blueprint import (
    parse_deploy_config,
    parse_force_shifts,
    parse_terrain_layout,
    validate_blueprint,
)
from app.domain.research_schema import is_valid_zh_label
from app.domain.technique_craft import (
    enrich_affix_slots_public,
    major_rank_label_zh,
    next_rank_id,
    payload_attr_grants,
)
from app.schemas.common import AppError
from app.services.inventory_service import InventoryService
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)


class ResearchService:
    """Create / preview / finalize research sessions (formation R3, talisman R4)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def get_catalog(self) -> dict[str, Any]:
        """Public catalog: materials, affixes, spends, Chinese help."""
        cfg = get_game_config()
        tech = cfg.research.technique
        form = cfg.research.formation
        tal = cfg.research.talisman
        affixes = [
            {
                "id": affix_id,
                "label_zh": affix.label_zh,
                "help_zh": affix.help_zh,
                "stats": affix.stats,
            }
            for affix_id, affix in cfg.research.affixes.items()
        ]
        return {
            "schema_version": cfg.research.schema_version,
            "kinds": [
                {"id": "technique", "label_zh": "功法", "open": True},
                {"id": "formation", "label_zh": "阵法", "open": True},
                {"id": "talisman", "label_zh": "符箓", "open": True},
            ],
            "technique": {
                "label_zh": tech.label_zh,
                "help_zh": tech.help_zh,
                "allowed_materials": list(tech.allowed_materials),
                "min_materials": tech.min_materials,
                "spend": dict(tech.spend),
                "reroll": {
                    "max_rerolls": tech.max_rerolls,
                    "extra_materials": list(tech.reroll_materials),
                },
                "affix_slots": tech.affix_slots,
            },
            "formation": {
                "label_zh": form.label_zh,
                "help_zh": form.help_zh,
                "allowed_materials": list(form.allowed_materials),
                "min_materials": form.min_materials,
                "spend": dict(form.spend),
                "required_array_level": form.required_array_level,
                "allowed_deploy_modes": list(form.allowed_deploy_modes),
                "default_deploy_mode": form.default_deploy_mode,
                "terrain_layout": dict(form.terrain_layout),
                "max_force_shifts": form.max_force_shifts,
            },
            "talisman": {
                "label_zh": tal.label_zh,
                "help_zh": tal.help_zh,
                "allowed_materials": list(tal.allowed_materials),
                "min_materials": tal.min_materials,
                "spend": dict(tal.spend),
                "scribe": {
                    "paper_item_id": tal.paper_item_id,
                    "paper_per_copy": tal.paper_per_copy,
                    "max_batch": tal.max_batch,
                },
                "preload_slots": tal.preload_slots,
                "battle_enabled": tal.battle_enabled,
                "effects": [
                    {
                        "id": effect.effect_id,
                        "label_zh": effect.label_zh,
                        "help_zh": effect.help_zh,
                        "trigger": effect.trigger,
                    }
                    for effect in get_game_config().talisman_effects.values()
                ],
            },
            "affixes": affixes,
            "technique_craft": {
                "help_zh": cfg.research.technique_craft.help_zh,
                "affix_rarities": [
                    {
                        "id": rid,
                        "label_zh": rare.label_zh,
                        "weight": rare.weight,
                        "base_mult": rare.base_mult,
                        "upgrade_mult": rare.upgrade_mult,
                        "cost_mult": rare.cost_mult,
                        "color": rare.color,
                    }
                    for rid, rare in cfg.research.technique_craft.affix_rarities.items()
                ],
                "affixes": [
                    {
                        "id": aid,
                        "label_zh": body.label_zh,
                        "rarity": body.rarity,
                        "efficacy_allow": list(body.efficacy_allow),
                        "role": body.role,
                        "stats": dict(body.stats),
                    }
                    for aid, body in cfg.research.technique_craft.affixes.items()
                ],
            },
        }

    async def list_mine(self, character: Character) -> list[dict[str, Any]]:
        """Finalized private techniques and formations for the character."""
        result = await self._session.execute(
            select(PrivateTechnique)
            .where(PrivateTechnique.character_id == character.id)
            .order_by(PrivateTechnique.id),
        )
        private_rows = list(result.scalars().all())
        tech_ids = [row.technique_id for row in private_rows]
        learned_sources: dict[str, str] = {}
        if tech_ids:
            learned = await self._session.execute(
                select(CharacterTechnique).where(
                    CharacterTechnique.character_id == character.id,
                    CharacterTechnique.technique_id.in_(tech_ids),
                ),
            )
            learned_sources = {
                str(row.technique_id): normalize_technique_source(
                    getattr(row, "source", None),
                )
                for row in learned.scalars().all()
            }
        items: list[dict[str, Any]] = []
        for row in private_rows:
            public = self._private_public(row)
            source = learned_sources.get(str(row.technique_id))
            if source:
                public["source"] = source
                public["source_label_zh"] = technique_source_label_zh(source)
            items.append(public)
        form_result = await self._session.execute(
            select(PrivateFormation)
            .where(PrivateFormation.character_id == character.id)
            .order_by(PrivateFormation.id),
        )
        for row in form_result.scalars().all():
            items.append(self._private_formation_public(row))
        tal_result = await self._session.execute(
            select(PrivateTalisman)
            .where(PrivateTalisman.character_id == character.id)
            .order_by(PrivateTalisman.id),
        )
        for row in tal_result.scalars().all():
            items.append(self._private_talisman_public(row))
        return items

    async def list_open_sessions(self, character: Character) -> list[dict[str, Any]]:
        """In-progress formation/talisman sessions; leftover technique rows are omitted."""
        result = await self._session.execute(
            select(ResearchSession)
            .where(
                ResearchSession.character_id == character.id,
                ResearchSession.phase.in_(
                    (RESEARCH_PHASE_DRAFTING, RESEARCH_PHASE_PREVIEWED),
                ),
            )
            .order_by(ResearchSession.id.desc()),
        )
        items: list[dict[str, Any]] = []
        for row in result.scalars().all():
            if row.kind == RESEARCH_KIND_TECHNIQUE:
                continue
            if row.expires_at is not None and now_utc() > ensure_aware_utc(row.expires_at):
                row.phase = RESEARCH_PHASE_EXPIRED
                continue
            items.append(self._session_public(row))
        return items

    async def get_private_by_ids(
        self,
        character_id: int,
        technique_ids: list[str],
    ) -> dict[str, PrivateTechnique]:
        """Map technique_id → PrivateTechnique for combat listing."""
        if not technique_ids:
            return {}
        result = await self._session.execute(
            select(PrivateTechnique).where(
                PrivateTechnique.character_id == character_id,
                PrivateTechnique.technique_id.in_(technique_ids),
            ),
        )
        return {str(row.technique_id): row for row in result.scalars().all()}

    async def create_session(
        self,
        character: Character,
        *,
        kind: str,
        materials: list[dict[str, Any]],
        spends: dict[str, int],
        effect_id: str | None = None,
    ) -> dict[str, Any]:
        """Start a formation/talisman session. Technique kind is rejected (40201)."""
        if kind == RESEARCH_KIND_FORMATION:
            return await self._create_formation_session(
                character,
                materials=materials,
                spends=spends,
            )
        if kind == RESEARCH_KIND_TALISMAN:
            return await self._create_talisman_session(
                character,
                materials=materials,
                spends=spends,
                effect_id=effect_id,
            )
        if kind == RESEARCH_KIND_TECHNIQUE:
            raise AppError(
                ERR_RESEARCH_SESSION,
                "请改用功法自研草稿接口",
                http_status=400,
            )
        raise AppError(ERR_RESEARCH_VALIDATE, "本期仅开放功法、阵法与符箓自研", http_status=400)

    async def get_session(self, character: Character, session_id: int) -> dict[str, Any]:
        """Load one session owned by the character."""
        row = await self._require_session(character, session_id)
        return self._session_public(row)

    async def reroll_session(self, character: Character, session_id: int) -> dict[str, Any]:
        """Reroll affixes, consuming extra materials. Technique leftover sessions raise 40201."""
        row = await self._require_session(character, session_id, writable=True)
        if row.kind == RESEARCH_KIND_TECHNIQUE:
            raise AppError(
                ERR_RESEARCH_SESSION,
                "请改用功法自研草稿接口",
                http_status=400,
            )
        if row.kind == RESEARCH_KIND_FORMATION:
            raise AppError(ERR_RESEARCH_VALIDATE, "阵法草案请保存设计，无需重投", http_status=400)
        if row.kind == RESEARCH_KIND_TALISMAN:
            raise AppError(ERR_RESEARCH_VALIDATE, "符箓草案请改效果后定稿，无需重投", http_status=400)
        raise AppError(ERR_RESEARCH_VALIDATE, "本期仅开放功法、阵法与符箓自研", http_status=400)

    async def finalize_session(
        self,
        character: Character,
        *,
        session_id: int,
        label_zh: str,
    ) -> dict[str, Any]:
        """Freeze preview into a private formation/talisman. Technique leftover sessions raise 40201."""
        row = await self._require_session(character, session_id, writable=True)
        if row.kind == RESEARCH_KIND_TECHNIQUE:
            raise AppError(
                ERR_RESEARCH_SESSION,
                "请改用功法自研草稿接口",
                http_status=400,
            )
        if row.kind == RESEARCH_KIND_FORMATION:
            return await self._finalize_formation(character, row, label_zh)
        if row.kind == RESEARCH_KIND_TALISMAN:
            return await self._finalize_talisman(character, row, label_zh)
        raise AppError(ERR_RESEARCH_VALIDATE, "本期仅开放功法、阵法与符箓自研", http_status=400)

    def default_formation_blueprint(self) -> dict[str, Any]:
        """Empty free_own + brush draft matching research.yaml."""
        form = get_game_config().research.formation
        return {
            "deploy": {
                "mode": form.default_deploy_mode,
                "cells": [],
                "add_cells": [],
                "exclude_cells": [],
                "allow_neutral": False,
            },
            "terrain_layout": dict(form.terrain_layout),
            "terrain": [],
            "force_shifts": [],
            "environment": None,
            "weather": None,
            "effect": None,
        }

    async def _create_formation_session(
        self,
        character: Character,
        *,
        materials: list[dict[str, Any]],
        spends: dict[str, int],
    ) -> dict[str, Any]:
        """Deduct costs and open a formation draft session."""
        form = get_game_config().research.formation
        if int(character.array_craft_level or 0) < int(form.required_array_level):
            raise AppError(ERR_RESEARCH_THRESHOLD, "阵法钻研等级不足，无法自研", http_status=400)
        self._validate_materials(materials, form.allowed_materials, form.min_materials)
        cult_need = int(form.spend.get("cultivation_points", 0) or 0)
        body_need = int(form.spend.get("body_tempering_points", 0) or 0)
        cult_got = int(spends.get("cultivation_points", cult_need) or 0)
        body_got = int(spends.get("body_tempering_points", body_need) or 0)
        if cult_got < cult_need or body_got < body_need:
            raise AppError(ERR_RESEARCH_MATERIALS, "投入修为或炼体不足", http_status=400)
        if int(character.cultivation_points or 0) < cult_need:
            raise AppError(ERR_RESEARCH_MATERIALS, "投入修为或炼体不足", http_status=400)
        if int(character.body_tempering_points or 0) < body_need:
            raise AppError(ERR_RESEARCH_MATERIALS, "投入修为或炼体不足", http_status=400)

        inv = InventoryService(self._session)
        try:
            await inv.remove_materials(character.id, materials)
        except AppError as exc:
            if exc.code == 40055:
                raise AppError(ERR_RESEARCH_MATERIALS, "非法材料或投入不足", http_status=400) from exc
            raise

        character.cultivation_points = int(character.cultivation_points or 0) - cult_need
        character.body_tempering_points = int(character.body_tempering_points or 0) - body_need

        ttl = int(form.session_ttl_seconds)
        expires = now_utc() + timedelta(seconds=ttl) if ttl > 0 else None
        blueprint = self.default_formation_blueprint()
        row = ResearchSession(
            character_id=character.id,
            kind=RESEARCH_KIND_FORMATION,
            phase=RESEARCH_PHASE_DRAFTING,
            materials_json=json.dumps(materials, ensure_ascii=False),
            spends_json=json.dumps(
                {"cultivation_points": cult_need, "body_tempering_points": body_need},
                ensure_ascii=False,
            ),
            seed=secrets.randbelow(2_147_483_647),
            affix_preview_json=json.dumps(blueprint, ensure_ascii=False),
            reroll_count=0,
            expires_at=expires,
        )
        self._session.add(row)
        await self._session.flush()
        logger.info(
            "research formation session created character_id=%s session_id=%s",
            character.id,
            row.id,
        )
        return self._session_public(row)

    async def _create_talisman_session(
        self,
        character: Character,
        *,
        materials: list[dict[str, Any]],
        spends: dict[str, int],
        effect_id: str | None,
    ) -> dict[str, Any]:
        """Deduct costs and open a talisman draft session."""
        tal = get_game_config().research.talisman
        self._validate_materials(materials, tal.allowed_materials, tal.min_materials)
        cult_need = int(tal.spend.get("cultivation_points", 0) or 0)
        body_need = int(tal.spend.get("body_tempering_points", 0) or 0)
        cult_got = int(spends.get("cultivation_points", cult_need) or 0)
        body_got = int(spends.get("body_tempering_points", body_need) or 0)
        if cult_got < cult_need or body_got < body_need:
            raise AppError(ERR_RESEARCH_MATERIALS, "投入修为或炼体不足", http_status=400)
        if int(character.cultivation_points or 0) < cult_need:
            raise AppError(ERR_RESEARCH_MATERIALS, "投入修为或炼体不足", http_status=400)
        if int(character.body_tempering_points or 0) < body_need:
            raise AppError(ERR_RESEARCH_MATERIALS, "投入修为或炼体不足", http_status=400)

        inv = InventoryService(self._session)
        try:
            await inv.remove_materials(character.id, materials)
        except AppError as exc:
            if exc.code == 40055:
                raise AppError(ERR_RESEARCH_MATERIALS, "非法材料或投入不足", http_status=400) from exc
            raise

        character.cultivation_points = int(character.cultivation_points or 0) - cult_need
        character.body_tempering_points = int(character.body_tempering_points or 0) - body_need

        ttl = int(tal.session_ttl_seconds)
        expires = now_utc() + timedelta(seconds=ttl) if ttl > 0 else None
        draft = {"effect_id": str(effect_id or "").strip()}
        row = ResearchSession(
            character_id=character.id,
            kind=RESEARCH_KIND_TALISMAN,
            phase=RESEARCH_PHASE_DRAFTING,
            materials_json=json.dumps(materials, ensure_ascii=False),
            spends_json=json.dumps(
                {"cultivation_points": cult_need, "body_tempering_points": body_need},
                ensure_ascii=False,
            ),
            seed=secrets.randbelow(2_147_483_647),
            affix_preview_json=json.dumps(draft, ensure_ascii=False),
            reroll_count=0,
            expires_at=expires,
        )
        self._session.add(row)
        await self._session.flush()
        logger.info(
            "research talisman session created character_id=%s session_id=%s",
            character.id,
            row.id,
        )
        return self._session_public(row)

    def _normalize_formation_blueprint(self, blueprint: dict[str, Any]) -> dict[str, Any]:
        """Parse + re-serialize a player blueprint; raise AppError on illegal fields."""
        form = get_game_config().research.formation
        catalogs = get_game_config().formations
        try:
            deploy = parse_deploy_config(blueprint.get("deploy"))
        except ValueError as exc:
            raise AppError(ERR_RESEARCH_VALIDATE, str(exc), http_status=400) from exc
        if deploy.mode not in form.allowed_deploy_modes:
            raise AppError(ERR_RESEARCH_VALIDATE, "部署模式不在白名单", http_status=400)
        terrain = list(blueprint.get("terrain") or [])
        try:
            layout = parse_terrain_layout(
                blueprint.get("terrain_layout") or form.terrain_layout,
                has_terrain=bool(terrain),
            )
            shifts = parse_force_shifts(blueprint.get("force_shifts"))
        except ValueError as exc:
            raise AppError(ERR_RESEARCH_VALIDATE, str(exc), http_status=400) from exc
        if len(shifts) > int(form.max_force_shifts):
            raise AppError(ERR_RESEARCH_VALIDATE, "强制移位条数超过上限", http_status=400)

        def _layer(raw: Any, allowed: tuple[str, ...], catalog: dict, label: str) -> dict[str, Any] | None:
            if not raw:
                return None
            if not isinstance(raw, dict):
                raise AppError(ERR_RESEARCH_WHITELIST, f"{label}非法", http_status=400)
            layer_id = str(raw.get("id") or raw.get("layer_id") or "")
            if not layer_id:
                return None
            if allowed and layer_id not in allowed:
                raise AppError(ERR_RESEARCH_WHITELIST, f"{label}不在白名单", http_status=400)
            if layer_id not in catalog:
                raise AppError(ERR_RESEARCH_WHITELIST, f"{label}不在目录", http_status=400)
            return {"id": layer_id, "force_apply": bool(raw.get("force_apply", False))}

        env = _layer(
            blueprint.get("environment"),
            form.allowed_environment_ids,
            catalogs.environment_catalog,
            "环境层",
        )
        weather = _layer(
            blueprint.get("weather"),
            form.allowed_weather_ids,
            catalogs.weather_catalog,
            "天气层",
        )
        effect = _layer(
            blueprint.get("effect"),
            form.allowed_effect_ids,
            catalogs.effect_catalog,
            "效果层",
        )
        from app.domain.formation_blueprint import deploy_config_to_dict, force_shifts_to_dict

        return {
            "deploy": deploy_config_to_dict(deploy),
            "terrain_layout": blueprint.get("terrain_layout") or form.terrain_layout,
            "terrain": terrain,
            "force_shifts": force_shifts_to_dict(shifts),
            "environment": env,
            "weather": weather,
            "effect": effect,
            "_parsed": {
                "deploy": deploy,
                "layout": layout,
                "shifts": shifts,
            },
        }

    async def save_formation_draft(
        self,
        character: Character,
        session_id: int,
        blueprint: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist a formation designer draft (not yet frozen)."""
        row = await self._require_session(character, session_id, writable=True)
        if row.kind != RESEARCH_KIND_FORMATION:
            raise AppError(ERR_RESEARCH_VALIDATE, "当前会话不是阵法草案", http_status=400)
        normalized = self._normalize_formation_blueprint(blueprint)
        normalized.pop("_parsed", None)
        row.affix_preview_json = json.dumps(normalized, ensure_ascii=False)
        row.phase = RESEARCH_PHASE_DRAFTING
        await self._session.flush()
        return self._session_public(row)

    async def save_talisman_draft(
        self,
        character: Character,
        session_id: int,
        effect_id: str,
    ) -> dict[str, Any]:
        """Persist the chosen whitelist effect on a talisman session."""
        row = await self._require_session(character, session_id, writable=True)
        if row.kind != RESEARCH_KIND_TALISMAN:
            raise AppError(ERR_RESEARCH_VALIDATE, "当前会话不是符箓草案", http_status=400)
        row.affix_preview_json = json.dumps(
            {"effect_id": str(effect_id or "").strip()},
            ensure_ascii=False,
        )
        row.phase = RESEARCH_PHASE_DRAFTING
        await self._session.flush()
        return self._session_public(row)

    async def _finalize_talisman(
        self,
        character: Character,
        row: ResearchSession,
        label_zh: str,
    ) -> dict[str, Any]:
        """Freeze a private talisman template if the effect is on the whitelist."""
        if not is_valid_zh_label(label_zh):
            raise AppError(ERR_RESEARCH_VALIDATE, "请使用二至十六字中文名称", http_status=400)
        raw = json.loads(row.affix_preview_json or "{}")
        effect_id = str(raw.get("effect_id") or "").strip() if isinstance(raw, dict) else ""
        effects = get_game_config().talisman_effects
        if not effect_id or effect_id not in effects:
            raise AppError(ERR_RESEARCH_WHITELIST, "符箓效果不在白名单", http_status=400)
        slug = secrets.token_hex(4)
        template_id = f"{PRIVATE_ID_PREFIX}:talisman:{character.id}:{slug}"
        private = PrivateTalisman(
            character_id=character.id,
            template_id=template_id,
            label_zh=label_zh.strip(),
            effect_id=effect_id,
            revision=1,
            schema_version=get_game_config().research.schema_version,
            source=RESEARCH_SOURCE_CUSTOM,
        )
        self._session.add(private)
        row.phase = RESEARCH_PHASE_FINALIZED
        row.private_content_id = template_id
        await self._session.flush()
        logger.info(
            "research talisman finalized character_id=%s session_id=%s template_id=%s",
            character.id,
            row.id,
            template_id,
        )
        payload = self._session_public(row)
        payload["private"] = self._private_talisman_public(private)
        return payload

    async def _finalize_formation(
        self,
        character: Character,
        row: ResearchSession,
        label_zh: str,
    ) -> dict[str, Any]:
        """Validate blueprint and freeze a private formation id."""
        if not is_valid_zh_label(label_zh):
            raise AppError(ERR_RESEARCH_VALIDATE, "请使用二至十六字中文名称", http_status=400)
        form = get_game_config().research.formation
        if int(character.array_craft_level or 0) < int(form.required_array_level):
            raise AppError(ERR_RESEARCH_THRESHOLD, "阵法钻研等级不足，无法定稿", http_status=400)
        raw = json.loads(row.affix_preview_json or "{}")
        normalized = self._normalize_formation_blueprint(raw)
        parsed = normalized.pop("_parsed")
        board = get_game_config().board
        slug = secrets.token_hex(4)
        formation_id = f"{PRIVATE_ID_PREFIX}:formation:{character.id}:{slug}"
        try:
            validate_blueprint(
                board,
                formation_id=formation_id,
                deploy=parsed["deploy"],
                terrain_layout=parsed["layout"],
                terrain=normalized["terrain"],
                force_shifts=parsed["shifts"],
            )
        except ValueError as exc:
            raise AppError(ERR_RESEARCH_VALIDATE, str(exc), http_status=400) from exc
        private = PrivateFormation(
            character_id=character.id,
            formation_id=formation_id,
            label_zh=label_zh.strip(),
            revision=1,
            schema_version=get_game_config().research.schema_version,
            blueprint_json=json.dumps(normalized, ensure_ascii=False),
            source=RESEARCH_SOURCE_CUSTOM,
        )
        self._session.add(private)
        row.phase = RESEARCH_PHASE_FINALIZED
        row.private_content_id = formation_id
        await self._session.flush()
        logger.info(
            "research formation finalized character_id=%s session_id=%s formation_id=%s",
            character.id,
            row.id,
            formation_id,
        )
        payload = self._session_public(row)
        payload["private"] = self._private_formation_public(private)
        return payload

    async def submit_review(self, character: Character, *, session_id: int) -> dict[str, Any]:
        """Placeholder review pool — always closed in R2."""
        await self._require_session(character, session_id)
        raise AppError(ERR_RESEARCH_REVIEW_CLOSED, "审核池尚未开放", http_status=400)

    async def _require_session(
        self,
        character: Character,
        session_id: int,
        *,
        writable: bool = False,
    ) -> ResearchSession:
        result = await self._session.execute(
            select(ResearchSession).where(ResearchSession.id == session_id).limit(1),
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise AppError(ERR_RESEARCH_SESSION, "自研会话不存在或已过期", http_status=404)
        if int(row.character_id) != int(character.id):
            raise AppError(ERR_RESEARCH_OWNER, "私有内容不属于当前角色", http_status=403)
        if row.expires_at is not None and now_utc() > ensure_aware_utc(row.expires_at):
            row.phase = RESEARCH_PHASE_EXPIRED
            await self._session.flush()
            raise AppError(ERR_RESEARCH_SESSION, "自研会话不存在或已过期", http_status=400)
        if writable and row.phase == RESEARCH_PHASE_FINALIZED:
            raise AppError(ERR_RESEARCH_FROZEN, "已定稿不可改，只能另开新研", http_status=400)
        if writable and row.phase not in {
            RESEARCH_PHASE_PREVIEWED,
            RESEARCH_PHASE_DRAFTING,
            "drafting",
        }:
            raise AppError(ERR_RESEARCH_SESSION, "自研会话不存在或已过期", http_status=400)
        return row

    @staticmethod
    def _validate_materials(
        materials: list[dict[str, Any]],
        allowed: tuple[str, ...],
        min_materials: int,
    ) -> None:
        if not materials or sum(int(m.get("quantity") or 0) for m in materials) < min_materials:
            raise AppError(ERR_RESEARCH_MATERIALS, "非法材料或投入不足", http_status=400)
        allowed_set = set(allowed)
        for mat in materials:
            item_id = str(mat.get("item_id") or "")
            qty = int(mat.get("quantity") or 0)
            if item_id not in allowed_set or qty <= 0:
                raise AppError(ERR_RESEARCH_MATERIALS, "非法材料或投入不足", http_status=400)

    def _session_public(self, row: ResearchSession) -> dict[str, Any]:
        previews = json.loads(row.affix_preview_json or "[]")
        blueprint = None
        effect_id = None
        if row.kind == RESEARCH_KIND_FORMATION:
            blueprint = previews if isinstance(previews, dict) else {}
            previews = []
        elif row.kind == RESEARCH_KIND_TALISMAN:
            draft = previews if isinstance(previews, dict) else {}
            effect_id = str(draft.get("effect_id") or "") or None
            previews = []
        purpose = DICE_PURPOSE_RESEARCH_TECHNIQUE
        if row.kind == RESEARCH_KIND_FORMATION:
            purpose = DICE_PURPOSE_RESEARCH_FORMATION
        elif row.kind == RESEARCH_KIND_TALISMAN:
            purpose = DICE_PURPOSE_RESEARCH_TALISMAN
        return {
            "id": row.id,
            "kind": row.kind,
            "kind_label_zh": RESEARCH_KIND_LABELS_ZH.get(row.kind, row.kind),
            "phase": row.phase,
            "phase_label_zh": RESEARCH_PHASE_LABELS_ZH.get(row.phase, row.phase),
            "reroll_count": int(row.reroll_count),
            "dice": {
                "purpose": purpose,
                "roll": row.dice_roll,
                "label_zh": f"出目 {row.dice_roll}" if row.dice_roll is not None else "未掷",
            },
            "affix_previews": previews,
            "blueprint": blueprint,
            "effect_id": effect_id,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "private_content_id": row.private_content_id,
        }

    @staticmethod
    def _private_payload(row: PrivateTechnique) -> dict[str, Any]:
        """Parse ``payload_json``; invalid or non-object values become {}."""
        try:
            raw = json.loads(getattr(row, "payload_json", None) or "{}")
        except json.JSONDecodeError:
            return {}
        return dict(raw) if isinstance(raw, dict) else {}

    @staticmethod
    def _private_public(row: PrivateTechnique) -> dict[str, Any]:
        payload = ResearchService._private_payload(row)
        author_id = getattr(row, "author_character_id", None)
        if author_id is None:
            author_id = row.character_id
        if payload.get("efficacy"):
            stats = payload_attr_grants(payload)
        else:
            stats = json.loads(row.stats_json or "{}")
        craft = get_game_config().research.technique_craft
        major_rank = str(getattr(row, "major_rank", None) or "body_tempering")
        upgrade_points = int(payload.get("upgrade_points") or 0)
        base_raw = payload.get("base") or {}
        base = dict(base_raw) if isinstance(base_raw, dict) else {}
        elements_raw = payload.get("elements") or []
        elements = list(elements_raw) if isinstance(elements_raw, list) else []
        element_limit = payload.get("element_limit") or None
        weapon_limit = payload.get("weapon_limit") or None
        if element_limit is not None:
            element_limit = str(element_limit) or None
        if weapon_limit is not None:
            weapon_limit = str(weapon_limit) or None

        next_rank = next_rank_id(major_rank)
        breakthrough_points_required: int | None = None
        if next_rank and next_rank in craft.ranks:
            rank_body = craft.ranks[next_rank]
            breakthrough_points_required = int(
                getattr(rank_body, "upgrade_points_required", 0) or 0
            )

        # 发动条件加成预览（现读 weapon_bonus；属性限制加成/词条目录后续走后台）
        condition_bonus: dict[str, Any] = {
            "element_limit": element_limit,
            "weapon_limit": weapon_limit,
            "weapon_bonus": {},
            "element_bonus": {},
            "help_zh": "发动条件满足时可获得配置加成；可用词条/加成/属性后续由运营后台配置。",
        }
        if weapon_limit and weapon_limit in craft.weapon_bonus:
            condition_bonus["weapon_bonus"] = {
                str(k): float(v) for k, v in craft.weapon_bonus[weapon_limit].items()
            }

        # Pad empty breakthrough slots the same way cultivate does.
        from app.services.technique_craft_service import TechniqueCraftService

        return {
            "id": row.technique_id,
            "source": row.source,
            "source_label_zh": SOURCE_LABEL_CUSTOM_ZH,
            "label_zh": row.label_zh,
            "revision": row.revision,
            "kind": RESEARCH_KIND_TECHNIQUE,
            "track": row.track,
            "stats": stats,
            "affix_ids": json.loads(row.affix_ids_json or "[]"),
            "efficacy": payload.get("efficacy") or None,
            "author_character_id": int(author_id) if author_id is not None else None,
            "cultivable": int(author_id or 0) == int(row.character_id),
            "major_rank": major_rank,
            "major_rank_label_zh": major_rank_label_zh(major_rank),
            "upgrade_points": upgrade_points,
            "base": base,
            "affixes": enrich_affix_slots_public(
                TechniqueCraftService._payload_affix_slots(payload, major_rank)
            ),
            "elements": elements,
            "element_limit": element_limit,
            "weapon_limit": weapon_limit,
            "next_rank": next_rank,
            "next_rank_label_zh": major_rank_label_zh(next_rank) if next_rank else None,
            "breakthrough_points_required": breakthrough_points_required,
            "condition_bonus": condition_bonus,
        }

    @staticmethod
    def _private_formation_public(row: PrivateFormation) -> dict[str, Any]:
        return {
            "id": row.formation_id,
            "source": row.source,
            "source_label_zh": SOURCE_LABEL_CUSTOM_ZH,
            "label_zh": row.label_zh,
            "revision": row.revision,
            "kind": RESEARCH_KIND_FORMATION,
            "blueprint": json.loads(row.blueprint_json or "{}"),
        }

    @staticmethod
    def _private_talisman_public(row: PrivateTalisman) -> dict[str, Any]:
        effect = get_game_config().talisman_effects.get(row.effect_id)
        return {
            "id": row.template_id,
            "source": row.source,
            "source_label_zh": SOURCE_LABEL_CUSTOM_ZH,
            "label_zh": row.label_zh,
            "revision": row.revision,
            "kind": RESEARCH_KIND_TALISMAN,
            "effect_id": row.effect_id,
            "effect_label_zh": effect.label_zh if effect else row.effect_id,
        }
