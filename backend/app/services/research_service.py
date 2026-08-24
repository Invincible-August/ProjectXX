"""
Research session service (M8 R2 technique path).
"""

from __future__ import annotations

import json
import logging
import secrets
import random
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
from app.domain.research_schema import is_valid_zh_label, pick_affix_ids, sum_affix_stats
from app.schemas.common import AppError
from app.services.dice_service import DiceService
from app.services.inventory_service import InventoryService
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)


class ResearchService:
    """Create / preview / finalize research sessions (technique R2, formation R3)."""

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
        }

    async def list_mine(self, character: Character) -> list[dict[str, Any]]:
        """Finalized private techniques and formations for the character."""
        result = await self._session.execute(
            select(PrivateTechnique)
            .where(PrivateTechnique.character_id == character.id)
            .order_by(PrivateTechnique.id),
        )
        items: list[dict[str, Any]] = []
        for row in result.scalars().all():
            items.append(self._private_public(row))
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
        """In-progress sessions (drafting / previewed) for the hall resume button."""
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
        """Start a research session: deduct costs, then preview (technique) or draft."""
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
        if kind != RESEARCH_KIND_TECHNIQUE:
            raise AppError(ERR_RESEARCH_VALIDATE, "本期仅开放功法、阵法与符箓自研", http_status=400)
        cfg = get_game_config().research
        tech = cfg.technique
        self._validate_materials(materials, tech.allowed_materials, tech.min_materials)
        cult_need = int(tech.spend.get("cultivation_points", 0) or 0)
        body_need = int(tech.spend.get("body_tempering_points", 0) or 0)
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

        ttl = int(tech.session_ttl_seconds)
        expires = now_utc() + timedelta(seconds=ttl) if ttl > 0 else None
        seed = secrets.randbelow(2_147_483_647)
        row = ResearchSession(
            character_id=character.id,
            kind=RESEARCH_KIND_TECHNIQUE,
            phase=RESEARCH_PHASE_PREVIEWED,
            materials_json=json.dumps(materials, ensure_ascii=False),
            spends_json=json.dumps(
                {"cultivation_points": cult_need, "body_tempering_points": body_need},
                ensure_ascii=False,
            ),
            seed=seed,
            reroll_count=0,
            expires_at=expires,
        )
        self._session.add(row)
        await self._session.flush()
        await self._roll_preview(character, row)
        await self._session.flush()
        logger.info(
            "research session created character_id=%s session_id=%s kind=%s",
            character.id,
            row.id,
            kind,
        )
        return self._session_public(row)

    async def get_session(self, character: Character, session_id: int) -> dict[str, Any]:
        """Load one session owned by the character."""
        row = await self._require_session(character, session_id)
        return self._session_public(row)

    async def reroll_session(self, character: Character, session_id: int) -> dict[str, Any]:
        """Reroll affixes, consuming extra materials."""
        row = await self._require_session(character, session_id, writable=True)
        if row.kind == RESEARCH_KIND_FORMATION:
            raise AppError(ERR_RESEARCH_VALIDATE, "阵法草案请保存设计，无需重投", http_status=400)
        if row.kind == RESEARCH_KIND_TALISMAN:
            raise AppError(ERR_RESEARCH_VALIDATE, "符箓草案请改效果后定稿，无需重投", http_status=400)
        cfg = get_game_config().research.technique
        if int(row.reroll_count) >= int(cfg.max_rerolls):
            raise AppError(ERR_RESEARCH_VALIDATE, "重投次数已用尽", http_status=400)
        extra = list(cfg.reroll_materials)
        if extra:
            try:
                await InventoryService(self._session).remove_materials(character.id, extra)
            except AppError as exc:
                if exc.code == 40055:
                    raise AppError(ERR_RESEARCH_MATERIALS, "非法材料或投入不足", http_status=400) from exc
                raise
        row.reroll_count = int(row.reroll_count) + 1
        await self._roll_preview(character, row)
        await self._session.flush()
        return self._session_public(row)

    async def finalize_session(
        self,
        character: Character,
        *,
        session_id: int,
        label_zh: str,
    ) -> dict[str, Any]:
        """Freeze preview into a private technique / formation."""
        row = await self._require_session(character, session_id, writable=True)
        if row.kind == RESEARCH_KIND_FORMATION:
            return await self._finalize_formation(character, row, label_zh)
        if row.kind == RESEARCH_KIND_TALISMAN:
            return await self._finalize_talisman(character, row, label_zh)
        if not is_valid_zh_label(label_zh):
            raise AppError(ERR_RESEARCH_VALIDATE, "请使用二至十六字中文名称", http_status=400)
        affix_ids = [str(x.get("id")) for x in json.loads(row.affix_preview_json or "[]") if x.get("id")]
        if not affix_ids:
            raise AppError(ERR_RESEARCH_VALIDATE, "草稿词条为空，请重投后再定稿", http_status=400)
        cfg = get_game_config()
        stats = sum_affix_stats(affix_ids, cfg.research.affixes)
        slug = secrets.token_hex(4)
        technique_id = f"{PRIVATE_ID_PREFIX}:technique:{character.id}:{slug}"
        private = PrivateTechnique(
            character_id=character.id,
            technique_id=technique_id,
            label_zh=label_zh.strip(),
            revision=1,
            schema_version=cfg.research.schema_version,
            affix_ids_json=json.dumps(affix_ids, ensure_ascii=False),
            stats_json=json.dumps(stats, ensure_ascii=False),
            track=cfg.research.technique.track,
            max_level=cfg.research.technique.max_level,
            source=RESEARCH_SOURCE_CUSTOM,
        )
        self._session.add(private)
        existing = await self._session.execute(
            select(CharacterTechnique.id).where(
                CharacterTechnique.character_id == character.id,
                CharacterTechnique.technique_id == technique_id,
            ).limit(1),
        )
        if existing.scalar_one_or_none() is None:
            self._session.add(
                CharacterTechnique(
                    character_id=character.id,
                    technique_id=technique_id,
                    level=1,
                    source="research",
                ),
            )
        row.phase = RESEARCH_PHASE_FINALIZED
        row.private_content_id = technique_id
        await self._session.flush()
        logger.info(
            "research finalized character_id=%s session_id=%s technique_id=%s",
            character.id,
            row.id,
            technique_id,
        )
        payload = self._session_public(row)
        payload["private"] = self._private_public(private)
        return payload

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

    async def _roll_preview(self, character: Character, row: ResearchSession) -> None:
        dice = DiceService(self._session)
        rng = random.Random(int(row.seed) + int(row.reroll_count) * 17)
        value, bounds = await dice.roll_for_character(
            character,
            purpose=DICE_PURPOSE_RESEARCH_TECHNIQUE,
            rng=rng,
        )
        cfg = get_game_config().research
        pool = list(cfg.affixes.keys())
        picked = pick_affix_ids(
            pool,
            roll=int(value),
            slots=cfg.technique.affix_slots,
            extra_affix_roll=cfg.technique.extra_affix_roll,
        )
        previews = []
        for affix_id in picked:
            affix = cfg.affixes[affix_id]
            previews.append({"id": affix_id, "label_zh": affix.label_zh, "stats": affix.stats})
        row.dice_roll = int(value)
        row.affix_preview_json = json.dumps(previews, ensure_ascii=False)
        row.phase = RESEARCH_PHASE_PREVIEWED
        _ = bounds

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
    def _private_public(row: PrivateTechnique) -> dict[str, Any]:
        return {
            "id": row.technique_id,
            "source": row.source,
            "source_label_zh": SOURCE_LABEL_CUSTOM_ZH,
            "label_zh": row.label_zh,
            "revision": row.revision,
            "kind": RESEARCH_KIND_TECHNIQUE,
            "track": row.track,
            "stats": json.loads(row.stats_json or "{}"),
            "affix_ids": json.loads(row.affix_ids_json or "[]"),
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
