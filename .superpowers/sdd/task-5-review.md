# Task 5 Review：verification API 路由

**Reviewer:** Subagent (read-only)  
**Date:** 2026-07-28  
**Brief:** `.superpowers/sdd/task-5-brief.md`  
**Report:** `.superpowers/sdd/task-5-report.md`

---

## Spec ✅

实现与 brief / plan Task 5 及设计 §4 六端点范围一致，可验收。

| Brief / 规格要求 | 验证结果 |
| --- | --- |
| 新建 `backend/app/api/verification.py` | ✅ 6 个端点齐全 |
| 修改 `backend/app/api/router.py` 挂载 | ✅ `include_router(verification.router)` |
| `APIRouter(prefix="/verification")` | ✅ L19；经 `main.py` `settings.api_prefix` → `/api/v1/verification/*` |
| GET `/modes` 含 `id_verify_mode` | ✅ 委托 `get_modes()`，无 DB |
| POST `/sms/send` body `{phone}` | ✅ `SmsSendRequest` + `send_sms` → `success(None)` |
| POST `/sms/confirm` → ticket | ✅ `confirm_sms` → `success({"ticket": ticket})` |
| POST `/email/send` / `/email/confirm` | ✅ 对称实现 |
| POST `/id/submit` → ticket | ✅ `submit_id` 传 `real_name` / `id_card` / `face_token` |
| 无鉴权 | ✅ 未使用 `get_current_user` |
| 未改 register / login | ✅ 仅 `router.py` 增一行 import + include |
| Step 2 联调（DEBUG `000000`） | ✅ report 自述 ASGI 冒烟 PASS（6 端点） |

---

## Findings

### 通过项（核心）

1. **路由挂载** — `verification.py` 使用 `prefix="/verification"`、`tags=["verification"]`；`router.py` 在 auth 之后挂载，路径与设计 `{API_PREFIX}/verification` 一致。
2. **薄路由层** — 各 handler 仅做 Schema 绑定、`get_db` 注入、调用 `verification_service`、返回 `success()`；业务逻辑留在 Task 4 服务层，职责清晰。
3. **信封一致性** — 与 `auth.py` 相同：`response_model=None`、`success()` / 全局 `AppError`；send 成功 `data=null`，confirm / id 成功 `data.ticket`。
4. **Schema 复用** — 直接引用 Task 4 的 `SmsSendRequest` 等模型，手机号/邮箱/验证码规范化在 Pydantic 层完成。
5. **端点完整性** — brief 联调仅列 SMS 三步骤，但「规格 6 端点」均已实现；report 对 email / id 亦有冒烟记录。
6. **文档** — `README.md`、`CHANGELOG.md` 已列出六端点与联调示例。

### Important（非阻塞）

1. **响应字段名 vs 设计 §4 表** — 设计表写 confirm / id 分别返回 `sms_ticket` / `email_ticket` / `id_ticket`；实现统一为 `data.ticket`（与 Task 4 `TicketData` 一致）。report 已说明 Task 6 注册侧做字段映射；前端/README 亦文档化为 `data.ticket`。建议在 Task 6 或 Task 7 更新设计 spec 表项，避免双轨文档。
2. **无自动化 HTTP 测试入库** — brief Step 2 为 httpx 联调而非 pytest；当前仅 report 自述冒烟。可随 Task 6 集成测试一并补 `test_verification_auth.py` 或独立 API 测试。

### 非阻塞备注（已知 / 后续任务）

1. **发送间隔 `40011`** — 同一 target 短时间重发会失败；属服务层预期行为，report 已标注。
2. **Task 4 id_card 规范化** — 服务层已调用 `normalize_id_card()`，与 Schema 对齐；Task 6 注册路径应继续复用同一规则。
3. **brief 源文件部分中文乱码** — 与 plan 正文对照无歧义。

---

## Verdict

**Approved**

Task 5 HTTP 层交付完整，六端点挂载与联调预期一致，与现有 auth 路由风格统一。可进入 Task 6（注册消费 ticket + 超级密码登录）。Task 6 接入时注意 ticket 字段名映射及可选补 HTTP 自动化测试。
