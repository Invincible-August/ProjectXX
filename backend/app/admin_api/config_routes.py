"""后台配置域路由：``/admin/config/*`` 与审计。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.admin_api.deps import get_admin_config_service, get_current_admin
from app.db.models import AdminUser
from app.schemas.admin import (
    AdminCsvImportRequest,
    AdminDraftSaveRequest,
    AdminEntryUpsertRequest,
    AdminImportRequest,
    AdminPublishRequest,
    AdminRollbackRequest,
    AdminSheetsSaveRequest,
    AdminValidateRequest,
)
from app.schemas.common import success
from app.services.admin_config_service import AdminConfigService

router = APIRouter(tags=["admin-config"])


@router.get("/config/domains", response_model=None)
async def list_domains(
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminConfigService = Depends(get_admin_config_service),
) -> dict:
    """内容域清单。"""
    svc.assert_can_view(admin)
    return success({"domains": svc.list_domain_summaries()})


@router.get("/config/bundle/summary", response_model=None)
async def bundle_summary(
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminConfigService = Depends(get_admin_config_service),
) -> dict:
    """玩家服当前 GameConfigBundle 摘要（验收热更用）。"""
    svc.assert_can_view(admin)
    return success(svc.bundle_summary())


@router.get("/config/{domain_id}/effective", response_model=None)
async def get_effective(
    domain_id: str,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminConfigService = Depends(get_admin_config_service),
) -> dict:
    """YAML ∪ 已发布覆盖。"""
    svc.assert_can_view(admin)
    return success(
        {
            "domain_id": domain_id,
            "payload": svc.get_effective(domain_id),
            "yaml_base": svc.get_yaml_base(domain_id),
        },
    )


@router.get("/config/{domain_id}/draft", response_model=None)
async def get_draft(
    domain_id: str,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminConfigService = Depends(get_admin_config_service),
) -> dict:
    """当前草稿。"""
    svc.assert_can_view(admin)
    return success(await svc.get_draft(domain_id))


@router.put("/config/{domain_id}/draft", response_model=None)
async def save_draft(
    domain_id: str,
    body: AdminDraftSaveRequest,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminConfigService = Depends(get_admin_config_service),
) -> dict:
    """保存草稿（校验通过才落库）。"""
    data = await svc.save_draft(domain_id, body.payload, admin=admin)
    return success(data)


@router.post("/config/{domain_id}/validate", response_model=None)
async def validate_domain(
    domain_id: str,
    body: AdminValidateRequest,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminConfigService = Depends(get_admin_config_service),
) -> dict:
    """校验候选覆盖（不落库）。"""
    svc.assert_can_view(admin)
    return success(svc.validate_overlay(domain_id, body.payload))


@router.post("/config/{domain_id}/diff", response_model=None)
async def diff_domain(
    domain_id: str,
    body: AdminValidateRequest,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminConfigService = Depends(get_admin_config_service),
) -> dict:
    """粗粒度 diff 预览。"""
    svc.assert_can_view(admin)
    return success(svc.diff_preview(domain_id, body.payload))


@router.post("/config/{domain_id}/publish", response_model=None)
async def publish_domain(
    domain_id: str,
    body: AdminPublishRequest,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminConfigService = Depends(get_admin_config_service),
) -> dict:
    """发布草稿 → 玩家服热更。"""
    data = await svc.publish(
        domain_id,
        admin=admin,
        note=body.note,
        confirm_high_risk=body.confirm_high_risk,
    )
    return success(data)


@router.post("/config/{domain_id}/rollback", response_model=None)
async def rollback_domain(
    domain_id: str,
    body: AdminRollbackRequest,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminConfigService = Depends(get_admin_config_service),
) -> dict:
    """回滚或清除覆盖。"""
    data = await svc.rollback(
        domain_id,
        admin=admin,
        target_version=body.target_version,
        confirm_high_risk=body.confirm_high_risk,
    )
    return success(data)


@router.get("/config/{domain_id}/revisions", response_model=None)
async def list_revisions(
    domain_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminConfigService = Depends(get_admin_config_service),
) -> dict:
    """发布历史。"""
    svc.assert_can_view(admin)
    return success({"revisions": await svc.list_revisions(domain_id, limit=limit)})


@router.get("/config/{domain_id}/export", response_model=None)
async def export_domain(
    domain_id: str,
    source: str = Query(default="effective", pattern="^(effective|yaml|draft)$"),
    format: str = Query(default="json", pattern="^(json|yaml)$"),
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminConfigService = Depends(get_admin_config_service),
) -> dict:
    """导出域配置（JSON/YAML 正文）。"""
    svc.assert_can_view(admin)
    if source == "draft":
        return success(await svc.export_draft(domain_id, fmt=format))
    return success(svc.export_payload(domain_id, source=source, fmt=format))


@router.post("/config/{domain_id}/import", response_model=None)
async def import_domain(
    domain_id: str,
    body: AdminImportRequest,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminConfigService = Depends(get_admin_config_service),
) -> dict:
    """导入 JSON/YAML 到草稿。"""
    data = await svc.import_to_draft(
        domain_id,
        admin=admin,
        raw_text=body.content,
        fmt=body.format,
        mode=body.mode,
    )
    return success(data)


@router.get("/config/{domain_id}/schema", response_model=None)
async def get_domain_schema(
    domain_id: str,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminConfigService = Depends(get_admin_config_service),
) -> dict:
    """域编辑契约：双写模式 + 字段中文说明。"""
    svc.assert_can_view(admin)
    return success(svc.get_edit_schema(domain_id))


@router.get("/config/{domain_id}/sheets", response_model=None)
async def get_domain_sheets(
    domain_id: str,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminConfigService = Depends(get_admin_config_service),
) -> dict:
    """嵌套域运营表格（realms/idle/dice）。"""
    svc.assert_can_view(admin)
    return success(await svc.get_sheets(domain_id))


@router.put("/config/{domain_id}/sheets", response_model=None)
async def save_domain_sheets(
    domain_id: str,
    body: AdminSheetsSaveRequest,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminConfigService = Depends(get_admin_config_service),
) -> dict:
    """表格写入：后端 format 成 JSON 后进草稿。"""
    data = await svc.save_sheets(
        domain_id,
        body.sheets,
        admin=admin,
        replace_draft=body.replace_draft,
    )
    return success(data)


@router.get("/config/{domain_id}/entries", response_model=None)
async def list_entries(
    domain_id: str,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminConfigService = Depends(get_admin_config_service),
) -> dict:
    """结构化条目表。"""
    svc.assert_can_view(admin)
    return success(await svc.list_entries(domain_id))


@router.get("/config/{domain_id}/entries/export.csv", response_model=None)
async def export_entries_csv(
    domain_id: str,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminConfigService = Depends(get_admin_config_service),
) -> dict:
    """导出条目 CSV。"""
    svc.assert_can_view(admin)
    return success(svc.export_entries_csv(domain_id))


@router.post("/config/{domain_id}/entries/import.csv", response_model=None)
async def import_entries_csv(
    domain_id: str,
    body: AdminCsvImportRequest,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminConfigService = Depends(get_admin_config_service),
) -> dict:
    """导入条目 CSV 到草稿。"""
    data = await svc.import_entries_csv(
        domain_id,
        admin=admin,
        raw_text=body.content,
        mode=body.mode,
    )
    return success(data)


@router.put("/config/{domain_id}/entries/{entry_id}", response_model=None)
async def upsert_entry(
    domain_id: str,
    entry_id: str,
    body: AdminEntryUpsertRequest,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminConfigService = Depends(get_admin_config_service),
) -> dict:
    """增改一条（写入草稿覆盖）。"""
    data = await svc.upsert_entry(domain_id, entry_id, body.body, admin=admin)
    return success(data)


@router.delete("/config/{domain_id}/entries/{entry_id}", response_model=None)
async def delete_entry(
    domain_id: str,
    entry_id: str,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminConfigService = Depends(get_admin_config_service),
) -> dict:
    """删除草稿中该条目覆盖。"""
    data = await svc.delete_entry(domain_id, entry_id, admin=admin)
    return success(data)


@router.get("/audit/logs", response_model=None)
async def list_audit(
    domain_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminConfigService = Depends(get_admin_config_service),
) -> dict:
    """审计日志。"""
    svc.assert_can_view(admin)
    return success({"logs": await svc.list_audit_logs(domain_id=domain_id, limit=limit)})
