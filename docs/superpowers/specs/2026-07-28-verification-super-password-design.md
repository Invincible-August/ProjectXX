# 注册核验模块与超级密码设计

| 项 | 内容 |
| --- | --- |
| **日期** | 2026-07-28 |
| **状态** | **已实现**（2026-07-28） |
| **依据** | 用户确认：方案甲；`ID_VERIFY_MODE` 环境变量选型；超级密码任意环境可用；A/B/C 均落地可切换 |
| **相关** | `M0工程骨架设计.md` 鉴权扩展；`M0前端目录与路由设计.md` §7 |

---

## 1. 目标

1. 注册需绑定 **邮箱、手机号**，并完成 **身份证核验**（主流程择一启用 A/B/C）。
2. 提供 **独立** `/api/v1/verification/*` 管理发码、验码、身份核验与 ticket。
3. **`DEBUG=true`（测试模式）**：跳过真实第三方；固定验证码 / 自动签发 ticket。
4. **`DEBUG=false`**：必须完成短信、邮件、当前 `ID_VERIFY_MODE` 对应身份核验后才能注册。
5. A/B/C **三套 Provider 代码均保留**；主流程只调用配置选中的那一套。
6. **超级密码**：`.env` 中配置 `SUPER_PASSWORD` 后，**任意环境**可用其登录任意已注册且启用的账号。

---

## 2. 架构（方案甲）

```text
api/verification.py          # 独立验证路由
api/auth.py                  # register 消费 ticket；login 支持超级密码
services/verification/
  ├── service.py             # 编排：发码、确认、签发 ticket、注册前校验
  ├── codes.py               # 验证码生成 / 哈希 / 频率限制
  ├── tickets.py             # ticket 签发与消费
  └── providers/
      ├── sms_base.py        # 短信接口
      ├── sms_debug.py
      ├── sms_aliyun.py       # 桩：流程完整，未配密钥则 NotImplemented/日志
      ├── sms_tencent.py      # 桩
      ├── email_base.py
      ├── email_debug.py
      ├── email_resend.py     # 桩
      ├── email_aliyun.py     # 桩
      ├── id_base.py
      ├── id_format.py        # A：格式 + 校验位（可真正执行）
      ├── id_two_factor.py    # B：二要素（默认 stub）
      └── id_real_person.py  # C：实人（默认 stub）
services/auth_service.py     # 注册字段扩展；登录超级密码分支
db/models/user.py            # 邮箱/手机/实名/证件哈希等
db/models/verification.py    # challenges / tickets 表（无 Redis 时）
```

分层：`api` → `services` → `providers` / ORM。路由不直连第三方 SDK。

---

## 3. 配置（环境变量）

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `DEBUG` | `true` | `true`：不发真码、不调真身份 API |
| `ID_VERIFY_MODE` | `format` | `format` \| `two_factor` \| `real_person` |
| `SUPER_PASSWORD` | 空 | 非空则启用超级密码（任意 `APP_ENV`） |
| `ID_CARD_HASH_SALT` | 必填建议 | 身份证哈希加盐 |
| `SMS_PROVIDER` | `debug` | `debug` \| `aliyun` \| `tencent` |
| `EMAIL_PROVIDER` | `debug` | `debug` \| `resend` \| `aliyun` \| `smtp` |
| `ID_TWO_FACTOR_PROVIDER` | `stub` | `stub` \| `aliyun` \| `tencent` |
| `ID_REAL_PERSON_PROVIDER` | `stub` | `stub` \| `aliyun` \| `tencent` |
| `VERIFY_CODE_TTL_SECONDS` | `300` | 验证码有效期 |
| `VERIFY_TICKET_TTL_SECONDS` | `600` | ticket 有效期 |
| `VERIFY_SEND_INTERVAL_SECONDS` | `60` | 同目标发送间隔 |
| `DEBUG_VERIFY_CODE` | `000000` | DEBUG 下可用的固定码 |

密钥类（阿里云/腾讯云/Resend）仅写入 `.env`，**禁止入库与提交仓库**。

---

## 4. 独立验证 API

前缀：`{API_PREFIX}/verification`（如 `/api/v1/verification`）。

| 方法 | 路径 | 鉴权 | 说明 |
| --- | --- | --- | --- |
| GET | `/modes` | 无 | 当前 `id_verify_mode`、`debug`、各 provider 名 |
| POST | `/sms/send` | 无 | body: `{ "phone": "..." }` |
| POST | `/sms/confirm` | 无 | body: `{ "phone", "code" }` → `sms_ticket` |
| POST | `/email/send` | 无 | body: `{ "email": "..." }` |
| POST | `/email/confirm` | 无 | body: `{ "email", "code" }` → `email_ticket` |
| POST | `/id/submit` | 无 | 见下 → `id_ticket` |

### `POST /id/submit` 请求字段

| 字段 | A format | B two_factor | C real_person |
| --- | --- | --- | --- |
| `real_name` | 建议填 | 必填 | 必填 |
| `id_card` | 必填 | 必填 | 必填 |
| `face_token` / `certify_id` | 忽略 | 忽略 | 必填（前端 SDK 结果；stub 时 DEBUG 可空） |

服务端 **只执行** `ID_VERIFY_MODE` 对应 Provider；其余 Provider 类保留在仓库，本请求不调用。

### DEBUG 行为

- `send`：不调用云厂商；将码写入日志（或仅接受 `DEBUG_VERIFY_CODE`）。
- `confirm`：码正确或等于 `DEBUG_VERIFY_CODE` 即发 ticket。
- `id/submit`：仍跑 A 的格式校验（可选：DEBUG 下连格式也跳过——**本设计采用：DEBUG 下身份核验直接签发 ticket，但若传了证件则顺带做格式检查并记日志，失败不阻断**）。为降低测试摩擦，定稿为：**DEBUG=true 时 id/submit 直接成功发 ticket**；非 DEBUG 才强制执行当前 mode。

### Ticket 规则

- 一次性、绑定目标（phone / email / id_card_hash）。
- 注册时校验 ticket 未过期、未消费，且与请求中的 phone/email/id_card 一致。
- 注册成功后标记 consumed。

---

## 5. 注册改造 `POST /auth/register`

### 请求 Body

| 字段 | DEBUG | 正式 |
| --- | --- | --- |
| `username` / `password` | 必填 | 必填 |
| `email` / `phone` | 建议填，可空兼容旧测 | 必填 |
| `real_name` / `id_card` | 可空 | 必填 |
| `sms_ticket` / `email_ticket` / `id_ticket` | 可空（服务端视为跳过） | 必填且校验 |

冲突：`40001` 用户名；`40013` 邮箱或手机已占用。

成功后：写入 User 扩展字段；`id_verified_level` = 当前 mode（DEBUG 跳过则记 `none` 或 `debug_skip`——定稿用 **`none` 若跳过，否则为实际 mode**）。

---

## 6. 登录与超级密码

`POST /auth/login` 字段不变。

顺序：

1. 查用户；不存在 → `40002`。
2. `verify_password(password, user.password_hash)` 成功 → 正常登录。
3. 否则若 `SUPER_PASSWORD` 非空且 `secrets.compare_digest(password, SUPER_PASSWORD)` → 以该用户签发 JWT；日志 **WARNING**（`super_password_login user_id=... username=...`），**不记录密码明文**。
4. 否则 → `40002`。
5. `is_active=false` → `40300`（超级密码也不能进禁用号——定稿：**禁用号拒绝，含超级密码**）。

生产与开发行为一致（用户确认「任意环境可用」）；风险由运维保证 `.env` 保密。

---

## 7. 数据模型

### `users` 新增

| 列 | 类型 | 说明 |
| --- | --- | --- |
| `email` | VARCHAR(255) UNIQUE NULL | |
| `phone` | VARCHAR(20) UNIQUE NULL | |
| `real_name` | VARCHAR(64) NULL | |
| `id_card_hash` | VARCHAR(128) NULL | SHA-256(salt + id_card) |
| `id_card_masked` | VARCHAR(32) NULL | |
| `id_verified_level` | VARCHAR(32) NOT NULL DEFAULT `none` | |
| `email_verified` | BOOL NOT NULL DEFAULT false | |
| `phone_verified` | BOOL NOT NULL DEFAULT false | |

M0 本地 SQLite：`create_all` 不改已有列时需迁移策略——首版可用 Alembic 或开发期删库重建；文档注明。

### `verification_challenges`

| 列 | 说明 |
| --- | --- |
| `id` | PK |
| `channel` | `sms` / `email` / `id` |
| `target` | 规范化后的手机/邮箱/证件指纹 |
| `code_hash` | 验证码哈希（id 通道可空） |
| `ticket` | 确认后的一次性票（唯一） |
| `payload_json` | 可选附加（如 mode） |
| `expires_at` / `consumed_at` / `created_at` | |

---

## 8. 错误码

| code | 含义 |
| --- | --- |
| `40010` | 验证码错误或过期 |
| `40011` | 发送过于频繁 |
| `40012` | ticket 无效/过期/不匹配 |
| `40013` | 邮箱或手机已占用 |
| `40014` | 身份证格式非法（A） |
| `40015` | 二要素核验失败（B） |
| `40016` | 实人核验失败（C） |
| `40017` | 正式模式缺少核验材料 |
| `50100` | Provider 未配置/未实现（正式模式误选 stub） |

登录超级密码失败不单独暴露错误码。

---

## 9. 第三方推荐与 Provider 状态

| 通道 | 推荐厂商 | 首版实现 |
| --- | --- | --- |
| 短信 | 阿里云短信 / 腾讯云短信 | `debug` 可用；`aliyun`/`tencent` 保留调用骨架 |
| 邮件 | Resend / 阿里云邮件推送 / SMTP | `debug` 可用；其余骨架 |
| 身份 A | 本地国标校验位 | **完整实现** |
| 身份 B | 阿里云/腾讯云二要素 | stub：非 DEBUG 返回 `50100` 或明确「未配置」 |
| 身份 C | 腾讯云慧眼 / 阿里云实人 | stub + 预留 `face_token`；非 DEBUG 未配置 → `50100` |

主流程：`ID_VERIFY_MODE=format` 即可在正式模式（`DEBUG=false`）用 A 完成闭环；切 B/C 前需配好对应 Provider。

---

## 10. 安全

- 所有密钥与超级密码仅环境变量。
- 身份证不落明文；日志禁止打印完整证件号、验证码明文（DEBUG 日志可打码，正式只打「已发送」）。
- 超级密码使用 `secrets.compare_digest` 防时序攻击。
- 发送频率限制按 target。

---

## 11. 前端影响（后续实现时可跟）

- 注册表单：邮箱、手机、发码、证件、按 `/verification/modes` 展示当前模式。
- DEBUG 时可隐藏核验步骤或一键填固定码。
- 登录无需改字段（超级密码对用户表现为「另一个密码」）。

---

## 12. 验收清单

- [ ] DEBUG 下可无 ticket 注册（若提供 email/phone 则落库）。
- [ ] `DEBUG=false` + `ID_VERIFY_MODE=format`：无 ticket 注册失败 `40017`；完成短信/邮件/A 后注册成功。
- [ ] B/C Provider 文件存在；mode 切到 B/C 且 provider=stub 时正式模式得到明确错误。
- [ ] 超级密码可登录任意启用账号；禁用账号不可；日志有 WARNING。
- [ ] `GET /verification/modes` 反映配置。
- [ ] README / CHANGELOG / `M0前端目录与路由设计.md` §7 已更新。

---

## 13. 修订记录

| 日期 | 说明 |
| --- | --- |
| 2026-07-28 | 初稿：三节设计经用户确认后落盘 |
