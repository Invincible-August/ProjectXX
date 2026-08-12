"""
后台配置域服务：草稿、校验、发布、回滚、审计（ADM-2～8 核心）。

玩家服经 OverlayStore + realm_config 读取合并后 Bundle。
"""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config_source.merge import deep_merge
from app.config_source.overlay_store import OverlayStore
from app.config_source.registry import (
    DomainMeta,
    get_domain_meta,
    list_domains,
)
from app.config_source.runtime import RuntimeConfigReloader
from app.config_source.yaml_source import get_shared_yaml_source
from app.core.time_utils import now_utc, to_utc_iso
from app.db.models import (
    AdminAuditLog,
    AdminUser,
    ConfigDraft,
    ConfigPublished,
    ConfigRevision,
)
from app.schemas.common import AppError
from app.services.admin_entry_editor import AdminEntryEditor
from app.services.admin_rbac import can_edit_domain, can_publish, can_view, parse_roles
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)

# 摘要 diff 时最多列出的顶层键数量
_DIFF_KEY_LIMIT = 40


class AdminConfigService:
    """内容域 CRUD / 发布用例（组合条目编辑器）。"""

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: 异步 DB 会话。
        """
        self._session = session
        # 与玩家服共用 YAML 缓存源，减少重复读盘
        self._yaml = get_shared_yaml_source()
        self._entries = AdminEntryEditor(self)

    async def load_published_into_store(self) -> None:
        """
        启动时把 ``config_published`` 灌入 OverlayStore。

        须在首次 ``get_game_config()`` 之前调用。
        """
        rows = (
            await self._session.scalars(select(ConfigPublished))
        ).all()
        overlays: dict[str, dict[str, Any]] = {}
        versions: dict[str, int] = {}
        for row in rows:
            try:
                payload = json.loads(row.payload_json or "{}")
            except json.JSONDecodeError:
                logger.error("corrupt published overlay domain=%s", row.domain_id)
                continue
            if not isinstance(payload, dict):
                continue
            overlays[row.domain_id] = payload
            versions[row.domain_id] = int(row.version)
        OverlayStore.replace_all(overlays, versions)

    def list_domain_summaries(self) -> list[dict[str, Any]]:
        """域清单 + 发布版本摘要（只读）。"""
        from app.services.admin_field_schema import get_domain_edit_schema
        from app.services.admin_sheet_codec import supports_structured_sheets

        result: list[dict[str, Any]] = []
        for meta in list_domains(include_disabled=True):
            edit = get_domain_edit_schema(meta.domain_id)
            has_sheets = supports_structured_sheets(meta.domain_id)
            has_entries = bool(edit and edit.entry_path)
            modes: list[str] = []
            if has_sheets:
                modes.append("table")
            if has_entries:
                modes.append("entries")
            modes.append("json")
            if edit:
                for mode in edit.edit_modes:
                    if mode not in modes and mode != "table":
                        modes.append(mode)
            result.append(
                {
                    "domain_id": meta.domain_id,
                    "title": meta.title,
                    "filename": meta.filename,
                    "risk": meta.risk,
                    "description": meta.description,
                    "enabled": meta.enabled,
                    "category_id": meta.category_id,
                    "category_title_zh": meta.category_title_zh,
                    "category_order": meta.category_order,
                    "published_version": OverlayStore.get_version(meta.domain_id),
                    "has_published_overlay": OverlayStore.has(meta.domain_id),
                    "edit_modes": modes,
                    "supports_sheets": has_sheets,
                    "supports_entries": has_entries,
                },
            )
        return result

    def get_yaml_base(self, domain_id: str) -> dict[str, Any]:
        """读取 YAML 底表（无覆盖；对外返回拷贝）。"""
        meta = self._require_enabled_meta(domain_id)
        return self._yaml.load_raw(meta.filename, copy=True)

    def get_effective(self, domain_id: str) -> dict[str, Any]:
        """YAML ∪ 已发布覆盖（当前玩家服所见）。"""
        meta = self._require_enabled_meta(domain_id)
        # copy=False + get_ref：deep_merge 内部会拷贝
        base = self._yaml.load_raw(meta.filename, copy=False)
        overlay = OverlayStore.get_ref(domain_id)
        if overlay:
            return deep_merge(base, overlay)
        # 无覆盖时仅拷贝底表，避免无意义的 empty merge
        return deepcopy(base)

    async def get_draft(self, domain_id: str) -> dict[str, Any]:
        """
        当前草稿；无草稿时返回空 overlay ``{}``。

        Returns:
            dict: 含 domain / payload / updated_at 等。
        """
        self._require_enabled_meta(domain_id)
        row = await self._session.scalar(
            select(ConfigDraft).where(ConfigDraft.domain_id == domain_id),
        )
        payload: dict[str, Any] = {}
        updated_at = None
        updated_by = None
        if row is not None:
            payload = self._loads_payload(row.payload_json)
            updated_at = to_utc_iso(row.updated_at) if row.updated_at else None
            updated_by = row.updated_by
        return {
            "domain_id": domain_id,
            "payload": payload,
            "updated_at": updated_at,
            "updated_by": updated_by,
            "preview_effective": deep_merge(self.get_yaml_base(domain_id), payload),
        }

    async def save_draft(
        self,
        domain_id: str,
        payload: dict[str, Any],
        *,
        admin: AdminUser,
    ) -> dict[str, Any]:
        """
        保存草稿覆盖层（不立即影响玩家服）。

        Args:
            domain_id: 域 ID。
            payload: partial overlay。
            admin: 操作者。

        Returns:
            dict: 最新草稿视图。
        """
        meta = self._require_enabled_meta(domain_id)
        roles = parse_roles(admin.roles)
        if not can_edit_domain(roles, risk=meta.risk):
            raise AppError(code=40320, message="无该域编辑权限", http_status=403)
        if not isinstance(payload, dict):
            raise AppError(code=40000, message="payload 须为 JSON object", http_status=400)

        # 先用草稿预览校验能否被 Bundle 解析
        self.validate_overlay(domain_id, payload)

        row = await self._session.scalar(
            select(ConfigDraft).where(ConfigDraft.domain_id == domain_id),
        )
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if row is None:
            row = ConfigDraft(
                domain_id=domain_id,
                payload_json=text,
                updated_by=admin.id,
            )
            self._session.add(row)
        else:
            row.payload_json = text
            row.updated_by = admin.id
            row.updated_at = now_utc()

        await self._write_audit(
            admin,
            action="draft_save",
            domain_id=domain_id,
            summary=f"保存草稿 {domain_id} keys={list(payload.keys())[:_DIFF_KEY_LIMIT]}",
            detail={"keys": list(payload.keys())},
        )
        await self._session.commit()
        return await self.get_draft(domain_id)

    def validate_overlay(self, domain_id: str, overlay: dict[str, Any]) -> dict[str, Any]:
        """
        将 YAML∪overlay 送入 ``load_game_config`` 同款解析路径做硬校验。

        为避免污染全局 OverlayStore / lru_cache，使用临时合并 raw + 域解析探测。

        Returns:
            dict: ``{\"ok\": true, \"message\": ...}``。

        Raises:
            AppError: 40050 校验失败。
        """
        meta = self._require_enabled_meta(domain_id)
        if not isinstance(overlay, dict):
            raise AppError(code=40000, message="overlay 须为 object", http_status=400)
        try:
            merged = deep_merge(self._yaml.load_raw(meta.filename, copy=False), overlay)
            self._probe_parse_domain(meta, merged)
        except Exception as exc:  # noqa: BLE001 — 配置错误统一映射
            logger.warning("config validate failed domain=%s err=%s", domain_id, exc)
            raise AppError(
                code=40050,
                message=f"配置校验失败: {exc}",
                http_status=400,
            ) from exc
        return {"ok": True, "message": "校验通过", "domain_id": domain_id}

    async def publish(
        self,
        domain_id: str,
        *,
        admin: AdminUser,
        note: str = "",
        confirm_high_risk: bool = False,
    ) -> dict[str, Any]:
        """
        将当前草稿发布为覆盖层并刷新玩家服 Bundle 缓存。

        Args:
            domain_id: 域。
            admin: 操作者（需 publisher）。
            note: 发布说明。
            confirm_high_risk: 高危域须 True。

        Returns:
            dict: 发布结果含 version。
        """
        meta = self._require_enabled_meta(domain_id)
        roles = parse_roles(admin.roles)
        if not can_publish(roles):
            raise AppError(code=40321, message="无发布权限", http_status=403)
        if meta.risk == "balance" and not confirm_high_risk:
            raise AppError(
                code=40051,
                message="高危域发布须 confirm_high_risk=true",
                http_status=400,
            )

        draft = await self._session.scalar(
            select(ConfigDraft).where(ConfigDraft.domain_id == domain_id),
        )
        if draft is None:
            raise AppError(code=40052, message="无草稿可发布", http_status=400)
        overlay = self._loads_payload(draft.payload_json)
        self.validate_overlay(domain_id, overlay)

        published = await self._session.scalar(
            select(ConfigPublished).where(ConfigPublished.domain_id == domain_id),
        )
        next_version = 1 if published is None else int(published.version) + 1
        text = json.dumps(overlay, ensure_ascii=False, sort_keys=True)
        now = now_utc()
        if published is None:
            published = ConfigPublished(
                domain_id=domain_id,
                payload_json=text,
                version=next_version,
                published_by=admin.id,
                published_at=now,
                note=note or "",
            )
            self._session.add(published)
        else:
            published.payload_json = text
            published.version = next_version
            published.published_by = admin.id
            published.published_at = now
            published.note = note or ""

        self._session.add(
            ConfigRevision(
                domain_id=domain_id,
                version=next_version,
                payload_json=text,
                published_by=admin.id,
                published_at=now,
                note=note or "",
                action="publish",
            ),
        )
        await self._write_audit(
            admin,
            action="publish",
            domain_id=domain_id,
            summary=f"发布 {domain_id} v{next_version}",
            detail={"version": next_version, "note": note},
        )
        await self._session.commit()

        # 热更：更新内存覆盖 → 统一重载 Bundle
        OverlayStore.set(domain_id, overlay, version=next_version)
        RuntimeConfigReloader.reload(reason=f"publish:{domain_id}:v{next_version}")
        logger.info("config published domain=%s version=%s", domain_id, next_version)
        return {
            "domain_id": domain_id,
            "version": next_version,
            "published_at": to_utc_iso(now),
            "note": note or "",
        }

    async def rollback(
        self,
        domain_id: str,
        *,
        admin: AdminUser,
        target_version: int | None = None,
        confirm_high_risk: bool = False,
    ) -> dict[str, Any]:
        """
        回滚到历史版本；``target_version=None`` 或 ``0`` 表示清除覆盖回到纯 YAML。

        Args:
            domain_id: 域。
            admin: 操作者。
            target_version: 目标历史 version；0/None=清覆盖。
            confirm_high_risk: 高危确认。
        """
        meta = self._require_enabled_meta(domain_id)
        roles = parse_roles(admin.roles)
        if not can_publish(roles):
            raise AppError(code=40321, message="无发布权限", http_status=403)
        if meta.risk == "balance" and not confirm_high_risk:
            raise AppError(
                code=40051,
                message="高危域回滚须 confirm_high_risk=true",
                http_status=400,
            )

        now = now_utc()
        if target_version is None or target_version <= 0:
            overlay: dict[str, Any] = {}
            action = "clear"
            note = "rollback to yaml-only"
        else:
            rev = await self._session.scalar(
                select(ConfigRevision).where(
                    ConfigRevision.domain_id == domain_id,
                    ConfigRevision.version == target_version,
                ),
            )
            if rev is None:
                raise AppError(code=40053, message="目标版本不存在", http_status=404)
            overlay = self._loads_payload(rev.payload_json)
            action = "rollback"
            note = f"rollback to v{target_version}"
            if overlay:
                self.validate_overlay(domain_id, overlay)

        published = await self._session.scalar(
            select(ConfigPublished).where(ConfigPublished.domain_id == domain_id),
        )
        next_version = 1 if published is None else int(published.version) + 1
        text = json.dumps(overlay, ensure_ascii=False, sort_keys=True)

        if not overlay:
            # 清覆盖：删除 published 行
            if published is not None:
                await self._session.delete(published)
            OverlayStore.remove(domain_id)
        else:
            if published is None:
                self._session.add(
                    ConfigPublished(
                        domain_id=domain_id,
                        payload_json=text,
                        version=next_version,
                        published_by=admin.id,
                        published_at=now,
                        note=note,
                    ),
                )
            else:
                published.payload_json = text
                published.version = next_version
                published.published_by = admin.id
                published.published_at = now
                published.note = note
            OverlayStore.set(domain_id, overlay, version=next_version)

        self._session.add(
            ConfigRevision(
                domain_id=domain_id,
                version=next_version,
                payload_json=text,
                published_by=admin.id,
                published_at=now,
                note=note,
                action=action,
            ),
        )
        await self._write_audit(
            admin,
            action=action,
            domain_id=domain_id,
            summary=f"{action} {domain_id} → store_v{next_version}",
            detail={"target_version": target_version, "new_version": next_version},
        )
        await self._session.commit()
        RuntimeConfigReloader.reload(reason=f"{action}:{domain_id}:v{next_version}")
        return {
            "domain_id": domain_id,
            "version": next_version,
            "action": action,
            "overlay_cleared": not bool(overlay),
        }

    async def list_revisions(self, domain_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """发布历史（新→旧）。"""
        self._require_enabled_meta(domain_id)
        rows = (
            await self._session.scalars(
                select(ConfigRevision)
                .where(ConfigRevision.domain_id == domain_id)
                .order_by(desc(ConfigRevision.id))
                .limit(max(1, min(limit, 100))),
            )
        ).all()
        return [
            {
                "id": row.id,
                "domain_id": row.domain_id,
                "version": row.version,
                "action": row.action,
                "note": row.note,
                "published_by": row.published_by,
                "published_at": to_utc_iso(row.published_at) if row.published_at else None,
            }
            for row in rows
        ]

    async def list_audit_logs(
        self,
        *,
        domain_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """审计日志。"""
        stmt = select(AdminAuditLog).order_by(desc(AdminAuditLog.id)).limit(
            max(1, min(limit, 200)),
        )
        if domain_id:
            stmt = stmt.where(AdminAuditLog.domain_id == domain_id)
        rows = (await self._session.scalars(stmt)).all()
        return [
            {
                "id": row.id,
                "admin_user_id": row.admin_user_id,
                "username": row.username,
                "action": row.action,
                "domain_id": row.domain_id,
                "summary": row.summary,
                "created_at": to_utc_iso(row.created_at) if row.created_at else None,
            }
            for row in rows
        ]

    def bundle_summary(self) -> dict[str, Any]:
        """玩家服当前 Bundle 摘要（只读；用于 ADM-2 验收）。"""
        cfg = get_game_config()
        # 仅取域 ID / 版本表，避免 snapshot() 双次深拷贝全量覆盖
        overlay_versions = OverlayStore.versions_map()
        return {
            "pets_species": list(cfg.pets.species.keys()),
            "techniques": list(cfg.techniques.keys()),
            "inventory_items": list(cfg.inventory.items.keys()),
            "weather_regions": list(cfg.weather.regions.keys()),
            "calendar_shichen": list(cfg.calendar.shichen_order),
            "monsters": list(cfg.monsters.keys()),
            "facilities": {
                key: bool(body.get("enabled"))
                for key, body in cfg.sects.facilities.items()
            },
            "map_regions": list(cfg.map.regions.keys()),
            "activities": {
                key: bool(body.get("enabled"))
                for key, body in cfg.activity.activities.items()
            },
            "overlay_domains": list(overlay_versions.keys()),
            "overlay_versions": overlay_versions,
        }

    def diff_preview(self, domain_id: str, overlay: dict[str, Any]) -> dict[str, Any]:
        """
        草稿相对当前 effective 的粗粒度 diff（顶层键增减）。

        Args:
            domain_id: 域。
            overlay: 候选覆盖。
        """
        current = self.get_effective(domain_id)
        preview = deep_merge(self.get_yaml_base(domain_id), overlay)
        return {
            "domain_id": domain_id,
            "added_or_changed_top_keys": sorted(
                set(preview.keys()) | set(current.keys()),
            )[:_DIFF_KEY_LIMIT],
            "overlay_top_keys": list(overlay.keys())[:_DIFF_KEY_LIMIT],
            "preview_size_hint": {
                "current_json_len": len(json.dumps(current, ensure_ascii=False)),
                "preview_json_len": len(json.dumps(preview, ensure_ascii=False)),
            },
        }

    def assert_can_view(self, admin: AdminUser) -> None:
        """无只读权则 403。"""
        if not can_view(parse_roles(admin.roles)):
            raise AppError(code=40320, message="无只读权限", http_status=403)

    @staticmethod
    def _require_enabled_meta(domain_id: str) -> DomainMeta:
        meta = get_domain_meta(domain_id)
        if meta is None:
            raise AppError(code=40410, message=f"未知内容域: {domain_id}", http_status=404)
        if not meta.enabled:
            raise AppError(
                code=40054,
                message=f"域 {domain_id} 尚未落地（占位），不可编辑",
                http_status=400,
            )
        return meta

    @staticmethod
    def _loads_payload(text: str) -> dict[str, Any]:
        try:
            data = json.loads(text or "{}")
        except json.JSONDecodeError as exc:
            raise AppError(code=50010, message="草稿 JSON 损坏", http_status=500) from exc
        if not isinstance(data, dict):
            raise AppError(code=50010, message="草稿根须为 object", http_status=500)
        return data

    async def _write_audit(
        self,
        admin: AdminUser,
        *,
        action: str,
        domain_id: str | None,
        summary: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self._session.add(
            AdminAuditLog(
                admin_user_id=admin.id,
                username=admin.username,
                action=action,
                domain_id=domain_id,
                summary=summary[:1024],
                detail_json=json.dumps(detail or {}, ensure_ascii=False),
            ),
        )

    def _probe_parse_domain(self, meta: DomainMeta, merged: dict[str, Any]) -> None:
        """
        用与 ``load_game_config`` 相同的解析函数探测单域合法性。

        不写 OverlayStore；直接对 merged raw 调私有 parse。
        """
        from app.core.config import get_settings
        from app.services import realm_config as rc

        settings = get_settings()
        domain = meta.domain_id
        # 按域分发；与 load_game_config 保持同步
        if domain == "pets":
            rc._parse_pets(merged)
        elif domain == "pet_affixes":
            rc._parse_pet_affixes(merged)
        elif domain == "pet_skills":
            rc._parse_pet_skills(merged)
        elif domain == "pet_skill_books":
            # 技能书外键依赖 skills/races：用当前 Bundle 快照补全
            cfg = rc.get_game_config()
            rc._parse_pet_skill_books(
                merged,
                skills=cfg.pet_skills.skills,
                races=cfg.pets.races,
            )
        elif domain == "pet_duel":
            rc._parse_pet_duel(merged)
        elif domain == "pet_eggs":
            rc._parse_pet_eggs(merged)
        elif domain == "pet_passives":
            rc._parse_pet_passives(merged)
        elif domain == "pet_feed":
            rc._parse_pet_feed(merged)
        elif domain == "pet_encounter":
            rc._parse_pet_encounter(merged)
        elif domain == "pet_capture":
            rc._parse_pet_capture(merged)
        elif domain == "items":
            rc._parse_inventory(merged)
        elif domain == "techniques":
            rc._parse_techniques(merged)
        elif domain == "weather":
            rc._parse_weather(merged)
        elif domain == "calendar":
            rc._parse_calendar(merged, settings)
        elif domain == "monsters":
            rc._parse_monsters(merged)
        elif domain == "formations":
            parsed = rc._parse_formations(merged)
            # 相对现行棋盘做蓝图硬校验（部署/地形/移位）
            from app.domain.formation_blueprint import validate_formation_def

            board = rc.get_game_config().board
            for fdef in parsed.formations.values():
                validate_formation_def(board, fdef)
        elif domain == "realms":
            rc._parse_realms(merged)
        elif domain == "idle":
            rc._parse_idle(merged, settings.idle_tick_seconds)
        elif domain == "dice":
            rc._parse_dice(merged)
        elif domain == "combat_attrs":
            rc._parse_combat_attrs(merged)
        elif domain == "sects":
            rc._parse_sects(merged)
        elif domain == "friends":
            rc._parse_friends(merged)
        elif domain == "trade":
            rc._parse_trade(merged)
        elif domain == "mail":
            rc._parse_mail(merged)
        elif domain == "chat":
            rc._parse_chat(merged)
        elif domain == "chat_heritage":
            rc._parse_chat_heritage(merged)
        elif domain == "mentor":
            rc._parse_mentor(merged)
        elif domain == "dual_cultivation":
            rc._parse_dual_cultivation(merged)
        elif domain == "currencies":
            rc._parse_currencies(merged)
        elif domain == "commerce":
            rc._parse_commerce(merged)
        elif domain == "map":
            rc._parse_map(merged)
        elif domain == "activity":
            rc._parse_activity(merged)
        elif domain == "taunt_auras":
            rc._parse_taunt_auras(merged)
        elif domain == "avatar":
            from app.domain.avatar_capability import AvatarCapabilityIndex
            from dataclasses import replace as dc_replace

            parsed = rc._parse_avatar(merged)
            realms = rc.get_game_config().realms
            for fid, funlock in parsed.feature_unlocks.items():
                if funlock.min_major not in realms:
                    raise ValueError(
                        f"avatar.feature_unlocks.{fid}.min_major="
                        f"{funlock.min_major!r} 不在 realms",
                    )
            # 探测构建索引（与 load_game_config 一致）
            dc_replace(
                parsed,
                capability=AvatarCapabilityIndex.from_config(parsed, realms),
            )
        elif domain == "breakthrough":
            rc._parse_breakthrough(merged)
        elif domain == "dao":
            rc._parse_dao(merged)
        elif domain == "dao_restraint":
            rc._parse_dao_restraint(merged)
        elif domain == "dao_lord":
            rc._parse_dao_lord(merged)
        elif domain == "world_events":
            rc._parse_world_events(merged)
        else:
            raise ValueError(f"no parser probe for domain={domain}")

    def export_payload(
        self,
        domain_id: str,
        *,
        source: str = "effective",
        fmt: str = "json",
    ) -> dict[str, Any]:
        """
        导出域配置正文。

        Args:
            domain_id: 域。
            source: ``effective`` / ``yaml`` / ``draft``（draft 仅已保存草稿）。
            fmt: ``json`` / ``yaml``。
        """
        from app.services.admin_io import dump_export

        self._require_enabled_meta(domain_id)
        if source == "yaml":
            payload = self.get_yaml_base(domain_id)
        elif source == "effective":
            payload = self.get_effective(domain_id)
        elif source == "draft":
            # 同步路径：仅读库外调用方应 await get_draft；此处给路由用 async 版
            raise AppError(code=40000, message="draft 导出请用 export_draft", http_status=400)
        else:
            raise AppError(code=40000, message="source 非法", http_status=400)
        media, text = dump_export(payload, fmt=fmt)
        return {
            "domain_id": domain_id,
            "source": source,
            "format": media,
            "content": text,
        }

    async def export_draft(
        self,
        domain_id: str,
        *,
        fmt: str = "json",
    ) -> dict[str, Any]:
        """导出当前草稿 overlay（可能为空）。"""
        from app.services.admin_io import dump_export

        draft = await self.get_draft(domain_id)
        media, text = dump_export(draft["payload"], fmt=fmt)
        return {
            "domain_id": domain_id,
            "source": "draft",
            "format": media,
            "content": text,
        }

    async def import_to_draft(
        self,
        domain_id: str,
        *,
        admin: AdminUser,
        raw_text: str,
        fmt: str = "json",
        mode: str = "merge",
    ) -> dict[str, Any]:
        """
        将导入正文写入草稿。

        Args:
            mode: ``merge``=deep_merge 到当前草稿；``replace``=整段替换草稿。
        """
        from app.config_source.merge import deep_merge as merge_dicts
        from app.services.admin_io import parse_import_text

        incoming = parse_import_text(raw_text, fmt=fmt)
        draft_view = await self.get_draft(domain_id)
        current = draft_view["payload"] if isinstance(draft_view.get("payload"), dict) else {}
        if mode == "replace":
            payload = incoming
        elif mode == "merge":
            payload = merge_dicts(current, incoming)
        else:
            raise AppError(code=40000, message="mode 仅支持 merge / replace", http_status=400)
        return await self.save_draft(domain_id, payload, admin=admin)

    # --- 条目表：委托 AdminEntryEditor（组合而非膨胀本类）---

    async def list_entries(self, domain_id: str) -> dict[str, Any]:
        """列出域条目表。"""
        return await self._entries.list_entries(domain_id)

    async def upsert_entry(
        self,
        domain_id: str,
        entry_id: str,
        body: dict[str, Any],
        *,
        admin: AdminUser,
    ) -> dict[str, Any]:
        """增改一条到草稿。"""
        return await self._entries.upsert_entry(
            domain_id,
            entry_id,
            body,
            admin=admin,
        )

    async def delete_entry(
        self,
        domain_id: str,
        entry_id: str,
        *,
        admin: AdminUser,
    ) -> dict[str, Any]:
        """删除草稿中该条目覆盖。"""
        return await self._entries.delete_entry(domain_id, entry_id, admin=admin)

    def export_entries_csv(self, domain_id: str) -> dict[str, Any]:
        """导出条目 CSV。"""
        return self._entries.export_csv(domain_id)

    async def import_entries_csv(
        self,
        domain_id: str,
        *,
        admin: AdminUser,
        raw_text: str,
        mode: str = "merge",
    ) -> dict[str, Any]:
        """导入条目 CSV。"""
        return await self._entries.import_csv(
            domain_id,
            admin=admin,
            raw_text=raw_text,
            mode=mode,
        )

    # --- 双写：字段 schema + 嵌套表格（realms/idle/dice）---

    def get_edit_schema(self, domain_id: str) -> dict[str, Any]:
        """
        返回域编辑契约（中文字段说明 + 双写模式 + 全路径目录）。

        Raises:
            AppError: 404 未知域。
        """
        from app.services.admin_field_catalog import build_field_catalog, catalog_coverage
        from app.services.admin_field_schema import get_domain_edit_schema
        from app.services.admin_sheet_codec import supports_structured_sheets

        self._require_enabled_meta(domain_id)
        schema = get_domain_edit_schema(domain_id)
        if schema is None:
            meta = get_domain_meta(domain_id)
            data: dict[str, Any] = {
                "domain_id": domain_id,
                "title_zh": meta.title if meta else domain_id,
                "description_zh": meta.description if meta else "",
                "edit_modes": ["json"],
                "fields": [],
                "sheets": [],
                "entry_path": None,
                "entry_fields": [],
                "dual_write_rule": (
                    "须同时提供表格与 JSON；表格由后端 format 为域 JSON；"
                    "每个字段须有中文 label/help。"
                ),
            }
        else:
            data = schema.to_dict()
            # 嵌套矩阵域以 codec 为准，避免空 sheets 却声明 table
            if supports_structured_sheets(domain_id):
                modes = list(dict.fromkeys([*data.get("edit_modes", []), "table", "json"]))
                data["edit_modes"] = modes
            elif "table" in data.get("edit_modes", []) and not data.get("sheets"):
                data["edit_modes"] = [
                    mode for mode in data["edit_modes"] if mode != "table"
                ] or ["json"]

        # 全量路径中文目录（覆盖当前生效配置里每一个可配置项）
        catalog = build_field_catalog(self.get_effective(domain_id))
        data["field_catalog"] = catalog
        data["field_coverage"] = catalog_coverage(catalog)
        data["supports_sheets"] = supports_structured_sheets(domain_id)
        data["supports_entries"] = bool(data.get("entry_path"))
        return data

    async def get_sheets(self, domain_id: str) -> dict[str, Any]:
        """
        将「草稿预览生效配置」展开为运营表格（含中文列头）。

        预览 = YAML ∪ 已发布 ∪ 当前草稿。
        """
        from app.services.admin_sheet_codec import payload_to_sheets, supports_structured_sheets

        self._require_enabled_meta(domain_id)
        if not supports_structured_sheets(domain_id):
            raise AppError(code=40056, message=f"域 {domain_id} 无结构化表格", http_status=400)
        draft = await self.get_draft(domain_id)
        draft_payload = draft.get("payload") if isinstance(draft.get("payload"), dict) else {}
        # 生效 = YAML∪已发布；再叠草稿，得到运营所见预览
        preview = deep_merge(self.get_effective(domain_id), draft_payload)
        sheets = payload_to_sheets(domain_id, preview)
        return {
            "domain_id": domain_id,
            "source": "draft_preview",
            "sheets": sheets,
            "schema": self.get_edit_schema(domain_id),
        }

    async def save_sheets(
        self,
        domain_id: str,
        sheets: list[dict[str, Any]],
        *,
        admin: AdminUser,
        replace_draft: bool = True,
    ) -> dict[str, Any]:
        """
        表格 → 后端 format 为域 JSON → 写入草稿。

        Args:
            domain_id: realms / idle / dice。
            sheets: 前端表格。
            admin: 操作者。
            replace_draft: True 时草稿整段替换为 format 结果（推荐，避免残缺 merge）。
        """
        from app.config_source.merge import deep_merge as merge_dicts
        from app.services.admin_sheet_codec import sheets_to_payload, supports_structured_sheets

        self._require_enabled_meta(domain_id)
        if not supports_structured_sheets(domain_id):
            raise AppError(code=40056, message=f"域 {domain_id} 无结构化表格", http_status=400)

        formatted = sheets_to_payload(domain_id, sheets)
        if replace_draft:
            payload = formatted
        else:
            draft_view = await self.get_draft(domain_id)
            current = draft_view["payload"] if isinstance(draft_view.get("payload"), dict) else {}
            payload = merge_dicts(current, formatted)

        saved = await self.save_draft(domain_id, payload, admin=admin)
        return {
            **saved,
            "formatted_payload": formatted,
            "message": "表格已 format 为 JSON 并写入草稿",
        }
