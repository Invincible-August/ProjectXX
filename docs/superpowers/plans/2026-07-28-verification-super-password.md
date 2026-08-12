# 注册核验与超级密码 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地独立 verification API、注册绑定邮箱/手机/身份证（A/B/C 可配置择一）、DEBUG 跳过真实验证，以及任意环境下的超级密码登录。

**Architecture:** `api/verification` → `services/verification`（编排 + Provider 适配器）；注册消费一次性 ticket；登录在用户密码失败后用 `secrets.compare_digest` 比对 `SUPER_PASSWORD`。身份 A 完整实现，B/C 与云短信/邮件保留骨架；主流程只调用 `ID_VERIFY_MODE` 选中实现。

**Tech Stack:** Python 3.11+、FastAPI、SQLAlchemy async、PyJWT、passlib、现有统一信封 `AppError`/`success`。

**Spec:** `docs/superpowers/specs/2026-07-28-verification-super-password-design.md`

## Global Constraints

- 注释与 docstring 使用**中文**；标识符英文。
- 密钥 / `SUPER_PASSWORD` 只来自 `.env`，禁止硬编码。
- 身份证不落明文；日志不打印完整证件号与正式环境验证码明文。
- 每次功能变更同步 `README.md`、`CHANGELOG.md`、`M0前端目录与路由设计.md` §7。
- **不要自动 git commit**，除非用户明确要求。
- SQLite 开发库：扩展 `users` 列时若 `create_all` 无法 ALTER，文档说明可删 `xiuxian.db` 重建，或加轻量 `ALTER TABLE` 启动补丁。

## File map

| 路径 | 职责 |
| --- | --- |
| `backend/app/core/config.py` | 新增核验 / 超级密码相关 Settings |
| `backend/.env.example` | 文档化新变量 |
| `backend/app/db/models/user.py` | 扩展用户字段 |
| `backend/app/db/models/verification.py` | challenges 表 |
| `backend/app/db/models/__init__.py` | 导出新模型 |
| `backend/app/db/session.py` 或 `main.py` | 可选：SQLite 列补齐 |
| `backend/app/services/verification/providers/*` | SMS/Email/ID Provider |
| `backend/app/services/verification/service.py` | 发码、确认、ticket、注册前校验 |
| `backend/app/schemas/verification.py` | 请求/响应 Schema |
| `backend/app/api/verification.py` | 路由 |
| `backend/app/api/router.py` | 挂载 |
| `backend/app/schemas/auth.py` | RegisterRequest 扩展 |
| `backend/app/services/auth_service.py` | 注册核验 + 超级密码登录 |
| `backend/tests/test_verification_auth.py` | 核心用例 |

---

### Task 1: Settings 与 .env.example

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`

**Produces:**
- `Settings.super_password: str`（默认 `""`）
- `Settings.id_verify_mode: str`（默认 `"format"`）
- `Settings.id_card_hash_salt: str`
- `Settings.sms_provider` / `email_provider` / `id_two_factor_provider` / `id_real_person_provider`
- `Settings.verify_code_ttl_seconds` / `verify_ticket_ttl_seconds` / `verify_send_interval_seconds` / `debug_verify_code`

- [ ] **Step 1: 扩展 Settings**

在 `Settings` 中增加（alias 与规格一致）：

```python
super_password: str = Field(default="", alias="SUPER_PASSWORD")
id_verify_mode: str = Field(default="format", alias="ID_VERIFY_MODE")
id_card_hash_salt: str = Field(default="dev-id-salt-change-me", alias="ID_CARD_HASH_SALT")
sms_provider: str = Field(default="debug", alias="SMS_PROVIDER")
email_provider: str = Field(default="debug", alias="EMAIL_PROVIDER")
id_two_factor_provider: str = Field(default="stub", alias="ID_TWO_FACTOR_PROVIDER")
id_real_person_provider: str = Field(default="stub", alias="ID_REAL_PERSON_PROVIDER")
verify_code_ttl_seconds: int = Field(default=300, alias="VERIFY_CODE_TTL_SECONDS")
verify_ticket_ttl_seconds: int = Field(default=600, alias="VERIFY_TICKET_TTL_SECONDS")
verify_send_interval_seconds: int = Field(default=60, alias="VERIFY_SEND_INTERVAL_SECONDS")
debug_verify_code: str = Field(default="000000", alias="DEBUG_VERIFY_CODE")
```

- [ ] **Step 2: 更新 `.env.example`**

追加上述变量注释说明；`SUPER_PASSWORD=` 留空示例。

- [ ] **Step 3: 本地 `.env` 可选手动追加**（不提交真实超级密码）

- [ ] **Step 4: 验证 Settings 可加载**

Run: `cd backend; .\.venv\Scripts\python.exe -c "from app.core.config import get_settings; s=get_settings(); print(s.id_verify_mode, s.debug, bool(s.super_password))"`  
Expected: 打印 `format True False`（或你的本地值）

---

### Task 2: User / VerificationChallenge 模型

**Files:**
- Modify: `backend/app/db/models/user.py`
- Create: `backend/app/db/models/verification.py`
- Modify: `backend/app/db/models/__init__.py`
- Modify: `backend/app/main.py`（SQLite 启动补齐缺失列，避免删库）

**Produces:**
- `User` 新列：`email`, `phone`, `real_name`, `id_card_hash`, `id_card_masked`, `id_verified_level`, `email_verified`, `phone_verified`
- `VerificationChallenge` 表

- [ ] **Step 1: 扩展 User**

```python
email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
phone: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)
real_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
id_card_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
id_card_masked: Mapped[str | None] = mapped_column(String(32), nullable=True)
id_verified_level: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
phone_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
```

- [ ] **Step 2: 新建 VerificationChallenge**

字段：`id`, `channel`, `target`, `code_hash`（nullable）, `ticket`（unique nullable）, `payload_json`（Text nullable）, `expires_at`, `consumed_at`（nullable）, `created_at`。

- [ ] **Step 3: 导出模型；main lifespan 保持 `create_all`**

- [ ] **Step 4: SQLite 列补丁**

在 `lifespan` 的 `create_all` 之后，对 SQLite 执行 `PRAGMA table_info(users)`，缺失列则 `ALTER TABLE users ADD COLUMN ...`（类型与默认值匹配）。新表 `verification_challenges` 由 `create_all` 创建即可。

- [ ] **Step 5: 冒烟**

Run: 启动 uvicorn 或 `create_all` 脚本，确认无报错。

---

### Task 3: ID / SMS / Email Providers

**Files:**
- Create: `backend/app/services/verification/__init__.py`
- Create: `backend/app/services/verification/providers/__init__.py`
- Create: `backend/app/services/verification/providers/id_format.py`（完整校验位）
- Create: `backend/app/services/verification/providers/id_two_factor.py`（stub）
- Create: `backend/app/services/verification/providers/id_real_person.py`（stub）
- Create: `backend/app/services/verification/providers/sms_debug.py` 等
- Create: `backend/app/services/verification/id_card_util.py`（mask + hash）

**Produces:**
- `validate_id_card_format(id_card: str) -> None` 失败抛 `AppError(40014)`
- `hash_id_card(id_card: str) -> str` / `mask_id_card(id_card: str) -> str`
- `async def verify_identity(...)` 工厂：按 mode 调用 A/B/C
- SMS/Email：`async def send_code(target, code) -> None`；非 debug 未实现时 `AppError(50100)`

- [ ] **Step 1: 实现国标 18 位校验位**（含地址码粗检可选，至少校验位）

- [ ] **Step 2: stub B/C**

```python
async def verify_two_factor(*, real_name: str, id_card: str) -> None:
    settings = get_settings()
    if settings.debug:
        return
    if settings.id_two_factor_provider == "stub":
        raise AppError(50100, "二要素 Provider 未配置", http_status=501)
    raise AppError(50100, "二要素 Provider 尚未接入", http_status=501)
```

C 同理，接收可选 `face_token`。

- [ ] **Step 3: debug SMS/Email** — 仅 `logger.info` 提示已「发送」（DEBUG 可不打印码到文件以外，或仅 debug 级别打印固定码说明）

- [ ] **Step 4: aliyun/tencent/resend 文件** — 函数签名齐全，`raise AppError(50100, "...")`

- [ ] **Step 5: 单元测格式校验**

```python
def test_id_card_checksum_valid():
    # 使用已知合法测试号（公开测试用号，勿用真人证件）
    validate_id_card_format("110101199003074477")  # 若算法下非法则换标准样例
```

Run: `pytest backend/tests/test_id_format.py -v`

---

### Task 4: verification service（发码 / 确认 / ticket）

**Files:**
- Create: `backend/app/services/verification/service.py`
- Create: `backend/app/schemas/verification.py`

**Produces:**
- `send_sms(session, phone) -> None`
- `confirm_sms(session, phone, code) -> str`  # ticket
- `send_email` / `confirm_email` 同上
- `submit_id(session, real_name, id_card, face_token=None) -> str`
- `assert_register_tickets(session, *, debug, email, phone, id_card, sms_ticket, email_ticket, id_ticket) -> None`
- `get_modes() -> dict`

逻辑要点：
- 发送前查同 `channel+target` 最近一条，未超 `verify_send_interval_seconds` → `40011`
- code 存 `hash_password` 或 sha256；确认用 `verify` 或 compare
- DEBUG：接受 `settings.debug_verify_code`
- ticket：`secrets.token_urlsafe(32)`，TTL=`verify_ticket_ttl_seconds`，写入同一 challenge 行或新行
- `submit_id`：若 `debug` → 直接发 ticket；否则按 `id_verify_mode` 调对应 provider，成功后发 ticket（payload 含 mode）

- [ ] **Step 1: 实现 service + schemas**

- [ ] **Step 2: httpx 测 send/confirm**（DEBUG）

Expected: confirm 返回 `code=0` 且 `data.ticket` 非空；错误码 `40010`/`40011` 可测。

---

### Task 5: verification API 路由

**Files:**
- Create: `backend/app/api/verification.py`
- Modify: `backend/app/api/router.py`

**Produces:** 规格中的 6 个端点

- [ ] **Step 1: 挂载 `APIRouter(prefix="/verification")`**

- [ ] **Step 2: 联调**

```text
GET /api/v1/verification/modes
POST /api/v1/verification/sms/send {"phone":"13800138000"}
POST /api/v1/verification/sms/confirm {"phone":"13800138000","code":"000000"}
```

Expected: modes 含 `id_verify_mode`；confirm 得 ticket。

---

### Task 6: 注册改造 + 超级密码登录

**Files:**
- Modify: `backend/app/schemas/auth.py`
- Modify: `backend/app/services/auth_service.py`
- Modify: `backend/app/api/auth.py`（若需）

**Produces:**
- `RegisterRequest` 增加 optional/required 字段：`email`, `phone`, `real_name`, `id_card`, `sms_ticket`, `email_ticket`, `id_ticket`
- `register_user`：非 DEBUG 缺材料 → `40017`；调 `assert_register_tickets`；查重 email/phone → `40013`；写扩展字段
- `login_user`：用户密码失败后超级密码分支 + WARNING 日志；禁用号仍 `40300`

- [ ] **Step 1: Schema + service**

超级密码比对：

```python
import secrets
from app.core.config import get_settings

settings = get_settings()
if settings.super_password and secrets.compare_digest(payload.password, settings.super_password):
    logger.warning("super_password_login user_id=%s username=%s", user.id, user.username)
    return _build_token_payload(user, remember_me=payload.remember_me)
```

- [ ] **Step 2: 集成测试**

1. DEBUG 注册无 ticket 成功  
2. 临时 `DEBUG=false`（测试内 monkeypatch）无 ticket → `40017`  
3. 完成三 ticket + format 注册成功  
4. 超级密码登录成功；错误密码仍 `40002`

Run: `pytest backend/tests/test_verification_auth.py -v`  
Expected: PASS

---

### Task 7: 文档与进度

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `M0前端目录与路由设计.md` §7（3.5 → 实现中/已完成）
- Modify: `docs/superpowers/specs/2026-07-28-verification-super-password-design.md` 状态行

- [ ] **Step 1: 写清新环境变量、联调步骤、第三方推荐摘要**

- [ ] **Step 2: 将步骤 3.5 标为已完成（若测试全过）**

---

## Spec coverage check

| 规格项 | Task |
| --- | --- |
| 独立 verification API | 4–5 |
| DEBUG 跳过 | 4、6 |
| ID_VERIFY_MODE 择一 A/B/C | 3–4 |
| B/C 代码保留 | 3 |
| 注册绑定 + ticket | 6 |
| 超级密码任意环境 | 1、6 |
| 错误码 40010–40017 / 50100 | 3–6 |
| 文档 | 7 |

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-28-verification-super-password.md`.

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每任务独立子代理，任务间复查  
2. **Inline Execution** — 本会话按计划连续实现并设检查点  

你选哪一种？
