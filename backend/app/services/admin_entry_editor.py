"""
后台配置「条目表」编辑器（结构化 CRUD）。

从 ``AdminConfigService`` 拆出，降低单类体积；通过组合复用草稿保存/校验。
"""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any, Protocol

from app.config_source.merge import deep_merge
from app.schemas.common import AppError
from app.services.admin_io import (
    ENTRY_TABLE_PATHS,
    csv_to_entries,
    entries_to_csv,
    get_entry_table,
    set_entry_table,
)

if TYPE_CHECKING:
    from app.db.models import AdminUser


class _DraftHost(Protocol):
    """条目编辑器依赖的草稿宿主协议。"""

    def get_effective(self, domain_id: str) -> dict[str, Any]:
        ...

    def _require_enabled_meta(self, domain_id: str) -> Any:
        ...

    async def get_draft(self, domain_id: str) -> dict[str, Any]:
        ...

    async def save_draft(
        self,
        domain_id: str,
        payload: dict[str, Any],
        *,
        admin: AdminUser,
    ) -> dict[str, Any]:
        ...


class AdminEntryEditor:
    """域内 id→定义 表的增删改与 CSV 进出。"""

    def __init__(self, host: _DraftHost) -> None:
        """
        Args:
            host: 提供 effective/draft/save 的配置服务实例。
        """
        self._host = host

    def assert_supports_entries(self, domain_id: str) -> None:
        """不支持条目表则抛 40056。"""
        if domain_id not in ENTRY_TABLE_PATHS:
            raise AppError(code=40056, message=f"域 {domain_id} 无条目表", http_status=400)

    async def list_entries(self, domain_id: str) -> dict[str, Any]:
        """列出域条目表（effective + 草稿覆盖 id）。"""
        self._host._require_enabled_meta(domain_id)
        self.assert_supports_entries(domain_id)
        table = get_entry_table(self._host.get_effective(domain_id), domain_id)
        draft = await self._host.get_draft(domain_id)
        draft_table = get_entry_table(draft.get("payload") or {}, domain_id)
        return {
            "domain_id": domain_id,
            "path": list(ENTRY_TABLE_PATHS[domain_id]),
            "entries": table,
            "draft_entry_ids": list(draft_table.keys()),
        }

    async def upsert_entry(
        self,
        domain_id: str,
        entry_id: str,
        body: dict[str, Any],
        *,
        admin: AdminUser,
    ) -> dict[str, Any]:
        """在草稿覆盖层中增改一条。"""
        self.assert_supports_entries(domain_id)
        if not entry_id.strip():
            raise AppError(code=40000, message="entry_id 不能为空", http_status=400)
        if not isinstance(body, dict):
            raise AppError(code=40000, message="条目 body 须为 object", http_status=400)

        draft_view = await self._host.get_draft(domain_id)
        overlay = deepcopy(draft_view.get("payload") or {})
        patch: dict[str, Any] = {}
        set_entry_table(patch, domain_id, {entry_id.strip(): body})
        return await self._host.save_draft(
            domain_id,
            deep_merge(overlay, patch),
            admin=admin,
        )

    async def delete_entry(
        self,
        domain_id: str,
        entry_id: str,
        *,
        admin: AdminUser,
    ) -> dict[str, Any]:
        """删除草稿中该条目覆盖（无法删除 YAML 底表键）。"""
        self.assert_supports_entries(domain_id)
        draft_view = await self._host.get_draft(domain_id)
        overlay = deepcopy(draft_view.get("payload") or {})
        table = get_entry_table(overlay, domain_id)
        if entry_id not in table:
            raise AppError(code=40411, message="草稿中无该条目覆盖", http_status=404)
        del table[entry_id]
        set_entry_table(overlay, domain_id, table)
        return await self._host.save_draft(domain_id, overlay, admin=admin)

    def export_csv(self, domain_id: str) -> dict[str, Any]:
        """导出 effective 条目 CSV。"""
        self._host._require_enabled_meta(domain_id)
        self.assert_supports_entries(domain_id)
        table = get_entry_table(self._host.get_effective(domain_id), domain_id)
        return {
            "domain_id": domain_id,
            "format": "csv",
            "content": entries_to_csv(domain_id, table),
        }

    async def import_csv(
        self,
        domain_id: str,
        *,
        admin: AdminUser,
        raw_text: str,
        mode: str = "merge",
    ) -> dict[str, Any]:
        """CSV 合并进草稿。"""
        self.assert_supports_entries(domain_id)
        incoming = csv_to_entries(raw_text)
        draft_view = await self._host.get_draft(domain_id)
        overlay = deepcopy(draft_view.get("payload") or {})
        if mode == "replace":
            set_entry_table(overlay, domain_id, incoming)
        elif mode == "merge":
            current = get_entry_table(overlay, domain_id)
            set_entry_table(overlay, domain_id, deep_merge(current, incoming))
        else:
            raise AppError(code=40000, message="mode 仅支持 merge / replace", http_status=400)
        return await self._host.save_draft(domain_id, overlay, admin=admin)
