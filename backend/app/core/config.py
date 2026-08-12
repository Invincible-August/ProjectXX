"""
应用配置：从环境变量 / `.env` 加载（M0 §2.4）。

密钥禁止写死在源码中，JWT_SECRET_KEY 必须来自环境变量或 backend/.env。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# app/core/config.py → 上两级为 backend/，避免 PyCharm 工作目录不是 backend 时读不到 .env
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _BACKEND_ROOT / ".env"


def _resolve_sqlite_database_url(database_url: str) -> str:
    """
    将相对路径的 SQLite URL 锚定到 ``backend/``，避免因启动 cwd 不同写出多份库。

    Args:
        database_url: 原始 DATABASE_URL。

    Returns:
        str: 若为相对 SQLite 路径则改为绝对路径 URL；否则原样返回。
    """
    for scheme in ("sqlite+aiosqlite:///", "sqlite:///"):
        if not database_url.startswith(scheme):
            continue
        raw_path = database_url[len(scheme) :]
        # 已是绝对路径（Unix /path 或 Windows C:/path）则不改
        if raw_path.startswith("/") or (len(raw_path) >= 3 and raw_path[1] == ":"):
            return database_url
        absolute = (_BACKEND_ROOT / raw_path).resolve()
        # SQLAlchemy 异步 SQLite：三个斜杠 + 绝对路径（Windows 为 C:/...）
        return f"{scheme}{absolute.as_posix()}"
    return database_url


class Settings(BaseSettings):
    """FastAPI 应用的类型化运行时配置。"""

    model_config = SettingsConfigDict(
        # 使用绝对路径：无论从哪启动 uvicorn，都能找到 backend/.env
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 应用元信息
    app_name: str = Field(default="ProjectXiuXian", alias="APP_NAME")  # 应用名（日志/OpenAPI）
    app_env: str = Field(default="development", alias="APP_ENV")  # 运行环境：development/production
    debug: bool = Field(default=True, alias="DEBUG")  # 调试模式（影响错误细节等）
    api_prefix: str = Field(default="/api/v1", alias="API_PREFIX")  # HTTP API 前缀
    host: str = Field(default="127.0.0.1", alias="HOST")  # 监听地址
    port: int = Field(default=8000, alias="PORT")  # 监听端口

    # 数据库连接串；相对 SQLite 路径会锚定到 backend/
    database_url: str = Field(
        default="sqlite+aiosqlite:///./xiuxian.db",
        alias="DATABASE_URL",
    )

    @model_validator(mode="after")
    def anchor_relative_sqlite_to_backend(self) -> Self:
        """相对 SQLite 路径统一落到 backend 目录，防止多 cwd 多库。"""
        object.__setattr__(
            self,
            "database_url",
            _resolve_sqlite_database_url(self.database_url),
        )
        return self

    # JWT：密钥必须来自环境变量，禁止硬编码
    jwt_secret_key: str = Field(alias="JWT_SECRET_KEY")  # 签名密钥
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")  # 算法
    access_token_expire_minutes: int = Field(
        default=30,
        alias="ACCESS_TOKEN_EXPIRE_MINUTES",
    )  # Access Token 有效分钟数
    refresh_token_expire_days: int = Field(
        default=14,
        alias="REFRESH_TOKEN_EXPIRE_DAYS",
    )  # Refresh Token 有效天数

    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="CORS_ORIGINS",
    )  # 逗号分隔的 CORS 允许源
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")  # 日志级别
    log_file: str = Field(default="logs/app.log", alias="LOG_FILE")  # 日志文件路径
    initial_spirit_stones: int = Field(default=1000, alias="INITIAL_SPIRIT_STONES")  # 创角初始灵石
    redis_url: str = Field(default="", alias="REDIS_URL")  # 非空则世界时钟/天气走 Redis

    # 核验与超级密码（verification / super-password 特性）
    super_password: str = Field(default="", alias="SUPER_PASSWORD")  # 万能登录密码（仅开发）
    id_verify_mode: str = Field(default="format", alias="ID_VERIFY_MODE")  # 身份证核验：format/二要素等
    id_card_hash_salt: str = Field(
        default="dev-id-salt-change-me",
        alias="ID_CARD_HASH_SALT",
    )  # 身份证哈希盐
    sms_provider: str = Field(default="debug", alias="SMS_PROVIDER")  # 短信 Provider
    email_provider: str = Field(default="debug", alias="EMAIL_PROVIDER")  # 邮件 Provider
    id_two_factor_provider: str = Field(
        default="stub",
        alias="ID_TWO_FACTOR_PROVIDER",
    )  # 身份证二要素 Provider
    id_real_person_provider: str = Field(
        default="stub",
        alias="ID_REAL_PERSON_PROVIDER",
    )  # 实人核验 Provider
    verify_code_ttl_seconds: int = Field(
        default=300,
        alias="VERIFY_CODE_TTL_SECONDS",
    )  # 验证码有效秒数
    verify_ticket_ttl_seconds: int = Field(
        default=600,
        alias="VERIFY_TICKET_TTL_SECONDS",
    )  # 核验票据有效秒数
    verify_send_interval_seconds: int = Field(
        default=60,
        alias="VERIFY_SEND_INTERVAL_SECONDS",
    )  # 发送间隔秒数（防刷）
    debug_verify_code: str = Field(default="000000", alias="DEBUG_VERIFY_CODE")  # debug Provider 固定码

    # 注册表单开关：关闭后对应字段可不填；三者皆关则仅邮箱+密码即可注册
    register_require_phone: bool = Field(
        default=False,
        alias="REGISTER_REQUIRE_PHONE",
    )  # 是否强制手机+短信票据
    register_require_real_name: bool = Field(
        default=False,
        alias="REGISTER_REQUIRE_REAL_NAME",
    )  # 是否强制实名+身份证票据
    register_require_email_code: bool = Field(
        default=False,
        alias="REGISTER_REQUIRE_EMAIL_CODE",
    )  # 是否强制邮箱验证码票据

    # --- M1 挂机 / GM / 突破测试 ---
    # 挂机一片时长（秒）；>0 时覆盖 idle.yaml 的 tick_seconds
    idle_tick_seconds: int = Field(default=60, alias="IDLE_TICK_SECONDS")
    # 写入 OpenAPI/前端可读的轮询提示（秒）
    idle_poll_hint_seconds: int = Field(default=5, alias="IDLE_POLL_HINT_SECONDS")
    # GM 开关：development 默认开；显式 false 即使 development 也 40310
    gm_enabled: bool = Field(default=True, alias="GM_ENABLED")
    # 可选白名单：逗号分隔 user_id；空=开发环境任意登录用户可用（仅本地便利）
    gm_allowed_user_ids: str = Field(default="", alias="GM_ALLOWED_USER_IDS")
    # 突破掷骰种子；仅测试注入，生产勿设
    breakthrough_rng_seed: int | None = Field(
        default=None,
        alias="BREAKTHROUGH_RNG_SEED",
    )

    # --- M2 离线帽 / 分配 / 体质 / 品阶 ---
    offline_cap_hours_free: float = Field(
        default=12.0,
        alias="OFFLINE_CAP_HOURS_FREE",
    )  # 免费档离线收益上限（小时）
    offline_cap_hours_member_tier1: float = Field(
        default=18.0,
        alias="OFFLINE_CAP_HOURS_MEMBER_TIER1",
    )  # 会员 tier1 离线帽（小时）
    offline_cap_hours_member_tier2: float = Field(
        default=24.0,
        alias="OFFLINE_CAP_HOURS_MEMBER_TIER2",
    )  # 会员 tier2 离线帽（小时）
    offline_preview_threshold_seconds: int = Field(
        default=300,
        alias="OFFLINE_PREVIEW_THRESHOLD_SECONDS",
    )  # 超过此秒数才写 offline pending 预览
    allocate_min_unit: int = Field(default=1, alias="ALLOCATE_MIN_UNIT")  # 三池分配最小单位
    constitution_unequip_cooldown_seconds: int = Field(
        default=0,
        alias="CONSTITUTION_UNEQUIP_COOLDOWN_SECONDS",
    )  # 体质卸下冷却（秒）；0=无冷却
    grade_rng_seed: int | None = Field(
        default=None,
        alias="GRADE_RNG_SEED",
    )  # 跨境品阶掷骰种子（仅测试）

    # --- M3 战斗成型 / 体力 / 快照 ---
    stamina_enabled: bool = Field(default=True, alias="STAMINA_ENABLED")  # 体力系统总开关
    battle_max_rounds: int = Field(
        default=0,
        alias="BATTLE_MAX_ROUNDS",
    )  # 战斗最大回合；0=读 YAML 默认
    snapshot_manual_cooldown_seconds: int = Field(
        default=0,
        alias="SNAPSHOT_MANUAL_COOLDOWN_SECONDS",
    )  # 手动更新防守快照冷却；0=读配置
    snapshot_lazy_daily_enabled: bool = Field(
        default=True,
        alias="SNAPSHOT_LAZY_DAILY_ENABLED",
    )  # 是否启用每日定点惰性刷快照
    autochess_rng_seed: int | None = Field(
        default=None,
        alias="AUTOCHESS_RNG_SEED",
    )  # 自走棋 RNG 种子（仅测试）
    pve_require_preset: bool = Field(
        default=False,
        alias="PVE_REQUIRE_PRESET",
    )  # PVE 开战是否强制已保存阵容预设

    # --- M4 双线程成长 ---
    avatar_enabled: bool = Field(default=True, alias="AVATAR_ENABLED")  # 化身功能开关
    craft_enabled: bool = Field(default=True, alias="CRAFT_ENABLED")  # 工坊功能开关
    pets_enabled: bool = Field(default=True, alias="PETS_ENABLED")  # 灵宠功能开关
    divine_sense_strict: bool = Field(
        default=True,
        alias="DIVINE_SENSE_STRICT",
    )  # True=超神识容量硬拦截；False=仅告警
    m4_gm_grant_materials: bool = Field(
        default=True,
        alias="M4_GM_GRANT_MATERIALS",
    )  # GM 是否可发放工坊材料

    # --- M5 环境与轮回外环 ---
    calendar_enabled: bool = Field(default=True, alias="CALENDAR_ENABLED")  # 六时历法开关
    weather_enabled: bool = Field(default=True, alias="WEATHER_ENABLED")  # 世界天气开关
    tribulation_enabled: bool = Field(default=True, alias="TRIBULATION_ENABLED")  # 渡劫流程开关
    calendar_epoch_utc: str = Field(
        default="",
        alias="CALENDAR_EPOCH_UTC",
    )  # 历法纪元 UTC ISO；空则读 calendar.yaml
    calendar_slot_seconds: int = Field(
        default=0,
        alias="CALENDAR_SLOT_SECONDS",
    )  # 一时辰现实秒数；0=读 YAML（默认 60）
    world_state_backend: str = Field(
        default="memory",
        alias="WORLD_STATE_BACKEND",
    )  # 世界状态后端：memory / redis / db
    ferry_countdown_seconds: int = Field(
        default=0,
        alias="FERRY_COUNTDOWN_SECONDS",
    )  # 待引渡倒计时秒数；0=读 reincarnation.yaml
    reincarnation_pet_carry: bool = Field(
        default=False,
        alias="REINCARNATION_PET_CARRY",
    )  # 轮回带宠钩子（完整数值 → M5-D06）

    # --- M6 大道 / 道主 / WebSocket ---
    dao_system_enabled: bool = Field(default=True, alias="DAO_SYSTEM_ENABLED")
    dao_lord_enabled: bool = Field(default=True, alias="DAO_LORD_ENABLED")
    ws_enabled: bool = Field(default=True, alias="WS_ENABLED")
    ws_heartbeat_seconds: int = Field(default=25, alias="WS_HEARTBEAT_SECONDS")
    ws_idle_timeout_seconds: int = Field(default=90, alias="WS_IDLE_TIMEOUT_SECONDS")
    ws_redis_url: str = Field(default="", alias="WS_REDIS_URL")
    world_events_enabled: bool = Field(default=False, alias="WORLD_EVENTS_ENABLED")
    # DEV：强制挑战开窗（覆盖 YAML 时段判断）
    dao_lord_force_window: bool = Field(default=False, alias="DAO_LORD_FORCE_WINDOW")

    # --- M7 宗门 / 社交 / 经济（分竖切逐步打开）---
    sect_system_enabled: bool = Field(default=True, alias="SECT_SYSTEM_ENABLED")
    friends_system_enabled: bool = Field(default=True, alias="FRIENDS_SYSTEM_ENABLED")
    trade_system_enabled: bool = Field(default=True, alias="TRADE_SYSTEM_ENABLED")
    face_trade_timeout_sec: int = Field(default=0, alias="FACE_TRADE_TIMEOUT_SEC")
    mail_system_enabled: bool = Field(default=True, alias="MAIL_SYSTEM_ENABLED")
    chat_system_enabled: bool = Field(default=True, alias="CHAT_SYSTEM_ENABLED")
    chat_ws_push_enabled: bool = Field(default=True, alias="CHAT_WS_PUSH_ENABLED")
    heritage_system_enabled: bool = Field(default=True, alias="HERITAGE_SYSTEM_ENABLED")
    heritage_expire_sec: int = Field(default=0, alias="HERITAGE_EXPIRE_SEC")
    mentor_system_enabled: bool = Field(default=True, alias="MENTOR_SYSTEM_ENABLED")
    dual_cultivation_enabled: bool = Field(default=True, alias="DUAL_CULTIVATION_ENABLED")
    commerce_system_enabled: bool = Field(default=True, alias="COMMERCE_SYSTEM_ENABLED")
    commerce_sandbox_enabled: bool = Field(default=True, alias="COMMERCE_SANDBOX_ENABLED")
    same_region_stub: bool = Field(default=True, alias="SAME_REGION_STUB")

    # --- ADM 后台管理系统（与玩家 JWT 隔离）---
    # 为空则派生自 JWT_SECRET_KEY + 后缀，正式环境务必单独设置
    admin_jwt_secret_key: str = Field(default="", alias="ADMIN_JWT_SECRET_KEY")
    admin_access_token_expire_minutes: int = Field(
        default=120,
        alias="ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES",
    )  # 后台 access 有效分钟
    # 启动时若不存在则创建的默认管理员（仅开发便利；生产应改密或关掉）
    admin_bootstrap_username: str = Field(
        default="admin",
        alias="ADMIN_BOOTSTRAP_USERNAME",
    )
    admin_bootstrap_password: str = Field(
        default="admin123",
        alias="ADMIN_BOOTSTRAP_PASSWORD",
    )
    admin_bootstrap_enabled: bool = Field(
        default=True,
        alias="ADMIN_BOOTSTRAP_ENABLED",
    )  # false 时不自动建号

    @property
    def cors_origin_list(self) -> list[str]:
        """将逗号分隔的 CORS 源拆成干净列表。"""
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def resolved_admin_jwt_secret(self) -> str:
        """
        后台 JWT 签名密钥。

        优先 ``ADMIN_JWT_SECRET_KEY``；未设时用玩家密钥 + 固定后缀隔离受众，
        避免玩家 access_token 被误当后台令牌校验通过。
        """
        if self.admin_jwt_secret_key.strip():
            return self.admin_jwt_secret_key.strip()
        return f"{self.jwt_secret_key}::admin-audience"


@lru_cache
def get_settings() -> Settings:
    """
    返回缓存的 Settings 单例。

    Returns:
        Settings: 已加载的配置对象。
    """
    return Settings()  # type: ignore[call-arg]
