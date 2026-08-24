"""
后台「玩家管理」协议常量（开发计划 §0.6.3）。

仅放运营不变量与枚举；账号流水字段中文说明见 ``PLAYER_OPS_SCHEMA``。
"""

from __future__ import annotations

from typing import Any

from app.services.admin_field_schema import FieldMeta, SheetMeta

# 运营重置玩家密码的固定明文（落库前须哈希）
DEFAULT_RESET_PASSWORD = "12345678"

# 账号列表 / 流水分页允许的每页条数
PLAYER_PAGE_SIZES: tuple[int, ...] = (10, 20, 50, 100)

# 默认每页条数
PLAYER_DEFAULT_PAGE_SIZE = 20

# 打赏路径预设：微信
TIP_CHANNEL_WECHAT = "微信"
# 打赏路径预设：支付宝
TIP_CHANNEL_ALIPAY = "支付宝"
# 打赏路径预设集合（另可自填）
TIP_CHANNEL_PRESETS: tuple[str, ...] = (TIP_CHANNEL_WECHAT, TIP_CHANNEL_ALIPAY)

# 审计 domain_id：玩家账号运营
AUDIT_DOMAIN_PLAYER_ACCOUNTS = "player_accounts"

# 账号列表网格列（中文）
ACCOUNT_LIST_COLUMNS: tuple[FieldMeta, ...] = (
    FieldMeta("id", "数据库ID", "users 表自增主键（库内唯一，类似 ObjectId）", "int"),
    FieldMeta(
        "user_id",
        "user_id",
        "对外账号号：邮箱M/手机P/测试T/GM为G + 7位数字",
        "string",
    ),
    FieldMeta("email", "邮箱", "注册/登录邮箱，可空", "null_str"),
    FieldMeta("phone", "手机号", "注册/登录手机号，可空", "null_str"),
    FieldMeta("fate_luck", "剩余仙缘", "绑定角色 characters.fate_luck；未创角为 0", "int"),
    FieldMeta(
        "total_recharge_amount",
        "总打赏金额",
        "users.total_recharge_amount；由打赏流水累加",
        "int",
    ),
    FieldMeta("is_banned", "是否封号", "True=已封/已删（is_active=False）", "bool"),
    FieldMeta("is_gm", "是否GM", "运营可设；GM 功能暂未开放", "bool"),
    FieldMeta("character_name", "道号", "绑定角色道号；未创角为空", "null_str"),
)

# 记录打赏表单字段
TIP_CREATE_FIELDS: tuple[FieldMeta, ...] = (
    FieldMeta(
        "paid_at",
        "打赏时间",
        "年月日时分秒，格式 YYYY-MM-DD HH:MM:SS",
        "string",
    ),
    FieldMeta(
        "channel",
        "路径",
        "支付路径：微信 / 支付宝 / 运营自填",
        "string",
    ),
    FieldMeta("order_no", "订单号", "支付平台订单号；同账号不可重复", "string"),
    FieldMeta("amount", "金额", "正整数；写入后累加总打赏金额", "int"),
    FieldMeta("note", "备注", "可选运营备注", "null_str"),
)

# 打赏流水表列
TIP_LIST_COLUMNS: tuple[FieldMeta, ...] = (
    FieldMeta("id", "ID", "流水主键", "int"),
    FieldMeta("paid_at", "打赏时间", "运营录入的支付时刻", "string"),
    FieldMeta("channel", "路径", "微信 / 支付宝 / 自填", "string"),
    FieldMeta("order_no", "订单号", "支付订单号", "string"),
    FieldMeta("amount", "金额", "本笔打赏金额", "int"),
    FieldMeta("created_by_admin_name", "录入人", "后台操作账号", "null_str"),
)

# 仙缘派发流水表列
FATE_LUCK_GRANT_COLUMNS: tuple[FieldMeta, ...] = (
    FieldMeta("id", "ID", "流水主键", "int"),
    FieldMeta("granted_at", "派发时间", "运营派发时刻", "string"),
    FieldMeta("amount", "金额", "本次派发仙缘数量", "int"),
    FieldMeta("before_amount", "派发前", "派发前角色仙缘", "int"),
    FieldMeta("after_amount", "派发后", "派发后角色仙缘", "int"),
    FieldMeta("created_by_admin_name", "操作人", "后台操作账号", "null_str"),
)

# 广告观看流水表列（写入待广告系统接入）
AD_WATCH_COLUMNS: tuple[FieldMeta, ...] = (
    FieldMeta("id", "ID", "流水主键", "int"),
    FieldMeta("watched_at", "时间", "观看广告时刻", "string"),
    FieldMeta("platform", "平台", "广告平台标识（接入后由回调写入）", "string"),
    FieldMeta("ad_unit", "广告位", "可选广告位/创意 id", "null_str"),
)

# 派发仙缘表单
GRANT_FATE_LUCK_FIELDS: tuple[FieldMeta, ...] = (
    FieldMeta("amount", "派发数量", "正整数；累加到角色仙缘并写流水", "int"),
    FieldMeta("note", "备注", "可选", "null_str"),
)

# 改联系方式表单
CONTACTS_FIELDS: tuple[FieldMeta, ...] = (
    FieldMeta("email", "邮箱", "留空可清空；须全局唯一", "null_str"),
    FieldMeta("phone", "手机号", "11 位大陆号；留空可清空；须全局唯一", "null_str"),
)


def build_player_ops_schema() -> dict[str, Any]:
    """
    玩家运营中文字段契约（对齐 §0.0.1：每个可编辑字段有 label_zh/help_zh）。

    Returns:
        dict: 供 ``GET /admin/ops/players/schema`` 返回。
    """
    sheets = (
        SheetMeta(
            sheet_id="accounts",
            title_zh="账号列表",
            description_zh="玩家账号检索网格",
            columns=ACCOUNT_LIST_COLUMNS,
            primary_keys=("id",),
        ),
        SheetMeta(
            sheet_id="tips",
            title_zh="打赏记录",
            description_zh="手工录入与查看打赏流水",
            columns=TIP_LIST_COLUMNS,
            primary_keys=("id",),
        ),
        SheetMeta(
            sheet_id="fate_luck_grants",
            title_zh="仙缘派发记录",
            description_zh="派发仙缘时自动写入",
            columns=FATE_LUCK_GRANT_COLUMNS,
            primary_keys=("id",),
        ),
        SheetMeta(
            sheet_id="ad_watches",
            title_zh="广告观看记录",
            description_zh="广告系统接入前仅可查看；写入待回调",
            columns=AD_WATCH_COLUMNS,
            primary_keys=("id",),
        ),
    )
    return {
        "module_id": "player_accounts",
        "title_zh": "玩家管理 · 账号管理",
        "description_zh": (
            "运行时账号干预与流水（非配置 Overlay 域）。"
            "顶栏可多选批量：封号/重置密码/改联系方式/派发仙缘/软删/设GM；"
            "行内为打赏与流水查看。user号规则：M/P/T/G+7位；数据库ID自增。"
        ),
        "page_sizes": list(PLAYER_PAGE_SIZES),
        "default_page_size": PLAYER_DEFAULT_PAGE_SIZE,
        "tip_channel_presets": list(TIP_CHANNEL_PRESETS),
        "reset_password_plaintext": DEFAULT_RESET_PASSWORD,
        "forms": {
            "tip_create": [f.to_dict() for f in TIP_CREATE_FIELDS],
            "grant_fate_luck": [f.to_dict() for f in GRANT_FATE_LUCK_FIELDS],
            "contacts": [f.to_dict() for f in CONTACTS_FIELDS],
        },
        "sheets": [s.to_dict() for s in sheets],
        "note_zh": (
            "广告观看流水表已建；记录功能待广告系统接入后由回调写入，"
            "运营后台现阶段仅提供查看。"
        ),
    }
