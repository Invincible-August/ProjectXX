"""后台鉴权 / 配置 HTTP DTO。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AdminLoginRequest(BaseModel):
    """后台登录请求。"""

    username: str = Field(min_length=1, max_length=64, description="管理员用户名")
    password: str = Field(min_length=1, max_length=128, description="明文密码")


class AdminDraftSaveRequest(BaseModel):
    """保存域草稿。"""

    payload: dict[str, Any] = Field(description="partial overlay JSON object")


class AdminValidateRequest(BaseModel):
    """校验候选覆盖层。"""

    payload: dict[str, Any] = Field(description="待校验 overlay")


class AdminPublishRequest(BaseModel):
    """发布草稿。"""

    note: str = Field(default="", max_length=512, description="发布说明")
    confirm_high_risk: bool = Field(
        default=False,
        description="高危域（balance）须显式确认",
    )


class AdminRollbackRequest(BaseModel):
    """回滚。"""

    target_version: int | None = Field(
        default=None,
        description="历史 version；0 或 null 表示清除覆盖回 YAML",
    )
    confirm_high_risk: bool = Field(default=False, description="高危确认")


class AdminImportRequest(BaseModel):
    """导入 JSON/YAML 正文到草稿。"""

    content: str = Field(description="文件或粘贴正文")
    format: str = Field(default="json", description="json / yaml")
    mode: str = Field(default="merge", description="merge / replace")


class AdminEntryUpsertRequest(BaseModel):
    """条目表增改。"""

    body: dict[str, Any] = Field(description="条目定义 object")


class AdminCsvImportRequest(BaseModel):
    """CSV 条目导入。"""

    content: str = Field(description="CSV 正文")
    mode: str = Field(default="merge", description="merge / replace")


class AdminSheetsSaveRequest(BaseModel):
    """结构化表格写入（后端 format 为域 JSON 后进草稿）。"""

    sheets: list[dict[str, Any]] = Field(description="sheet_id + rows 列表")
    replace_draft: bool = Field(
        default=True,
        description="true=草稿整段替换为表格生成的 JSON（推荐）",
    )
