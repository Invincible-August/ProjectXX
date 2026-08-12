# Task 5 报告：verification API 路由

## 完成情况

- [x] **Step 1：挂载 `APIRouter(prefix="/verification")`**
  - `backend/app/api/verification.py`
  - `backend/app/api/router.py`（`include_router(verification.router)`）
- [x] **Step 2：联调**（`httpx.ASGITransport` → `app.main:app`，DEBUG 固定码 `000000`）

## 端点

| 方法 | 路径 | 行为 |
| --- | --- | --- |
| GET | `/api/v1/verification/modes` | `get_modes()` → data 含 `id_verify_mode` 等 |
| POST | `/api/v1/verification/sms/send` | `send_sms`；成功 `data=null` |
| POST | `/api/v1/verification/sms/confirm` | `confirm_sms` → `data.ticket` |
| POST | `/api/v1/verification/email/send` | `send_email` |
| POST | `/api/v1/verification/email/confirm` | `confirm_email` → `data.ticket` |
| POST | `/api/v1/verification/id/submit` | `submit_id` → `data.ticket` |

统一信封：`success()` / `AppError`（与 `auth.py` 一致）。无鉴权。未改 register/login。

## 冒烟结果

`httpx` + `ASGITransport(app=app)`，DEBUG=`true`，码 `000000`：

| 步骤 | 结果 |
| --- | --- |
| GET `/modes` | `code=0`，含 `id_verify_mode=format`、`debug=true` |
| POST `/sms/send` | `code=0` |
| POST `/sms/confirm` code=`000000` | `code=0`，`ticket` 长度 43 |
| POST `/email/send` | `code=0` |
| POST `/email/confirm` | `code=0`，`ticket` 长度 43 |
| POST `/id/submit` | `code=0`，`ticket` 长度 43（DEBUG 格式失败仅日志） |

结论：**SMOKE PASS**

## 涉及文件

| 路径 | 说明 |
| --- | --- |
| `backend/app/api/verification.py` | 新建 6 端点 |
| `backend/app/api/router.py` | 挂载 verification |
| `README.md` / `CHANGELOG.md` | 文档同步 |

## 未做（留给后续）

- 注册消费 ticket / 超级密码登录（Task 6）
- `git commit`（按约束未执行）

## 顾虑

- confirm / id 响应字段统一为 `data.ticket`（Schema `TicketData`）；注册侧字段名为 `sms_ticket` / `email_ticket` / `id_ticket`，由 Task 6 映射。
- 发送间隔仍走服务层 `40011`；联调同一手机号短时间重发会失败。
