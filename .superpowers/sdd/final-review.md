# Final Feature Review — 注册核验 + 超级密码

| 项 | 内容 |
| --- | --- |
| **日期** | 2026-07-28 |
| **范围** | 整功能终审（非 per-task）；只读 |
| **Spec** | `docs/superpowers/specs/2026-07-28-verification-super-password-design.md` |
| **Plan** | `docs/superpowers/plans/2026-07-28-verification-super-password.md` |
| **Progress** | `.superpowers/sdd/progress.md`（Task 1–6 complete；Task 7 文档已落盘） |
| **已知 ledger** | SQLite ALTER 上 UNIQUE 延后；Task5 响应字段 `data.ticket` |
| **证据** | 关键路径代码审阅；`pytest tests/test_verification_auth.py tests/test_id_format.py` → **20 passed** |

---

## Strengths

1. **规格主路径完整落地**：独立 `/api/v1/verification/*`（modes / sms / email / id）、注册消费三票、`DEBUG` 跳过、`ID_VERIFY_MODE` 择一调用 A/B/C、超级密码登录均已实现并挂载。
2. **分层清晰**：路由薄封装 → `verification/service` 编排 → Provider 工厂；密钥与 `SUPER_PASSWORD` 仅来自 Settings / `.env`。
3. **DEBUG 本地联调友好**：固定码 `DEBUG_VERIFY_CODE`、`id/submit` 直接发票、无票可注册；与规格 §4–§5 定稿一致。
4. **正式模式闸门正确**：缺材料 → `40017`；票无效/不匹配 → `40012`；邮箱/手机占用 → `40013`；B/C stub → `50100`；身份证不落明文（hash + mask）。
5. **超级密码行为符合定稿**：用户密码失败后旁路；`secrets.compare_digest`；禁用号仍 `40300`；成功签发前打 `super_password_login` WARNING，不记明文。
6. **测试覆盖核心验收**：DEBUG 无票注册、正式缺票/`real_name`、三票注册并消费、超密登录、错误密码、禁用号、冲突 `40013`；文档（README / CHANGELOG / M0 §7.3）已同步「已实现」。

---

## Issues

### Critical

（无）

对本目标（**DEBUG 本地可用**）无阻塞级缺陷；规格要求的「任意环境可用超级密码」属产品确认行为，不当作实现错误。

### Important

1. **`SUPER_PASSWORD` 为全局账号旁路（运维风险，非实现偏离）**  
   配置非空后可登录任意**启用**账号，且**不区分** `APP_ENV` / `DEBUG`（规格明确）。本地 `.env` 默认空则安全；一旦写入弱口令或泄露 `.env`，等同万能钥匙。DEBUG 本地：保持空或不提交真实值即可。上线前必须：强随机、密钥管理、审计 WARNING、考虑 IP/堡垒限制（规格未要求代码闸门）。

2. **`LoginRequest.password` 最大长度 64**  
   若 `SUPER_PASSWORD` 超过 64 字符，客户端无法提交完整值，超密实际不可用。运维设超密时需 ≤64，或后续放宽 Schema。

3. **规格列出 `EMAIL_PROVIDER=smtp`，仓库无 `email_smtp` 路由**  
   `_EMAIL_PROVIDERS` 仅有 `debug` / `resend` / `aliyun`；设 `smtp` → `50100`。DEBUG 默认 `debug` 不受影响；与规格配置表有小缺口。

4. **`DEBUG=false` 本地全链路摩擦**  
   非 DEBUG 发码为随机 6 位，debug Provider 仅在 `logger.debug` 打码；正式 confirm 不接受「仅固定码绕过」。集成测试用「先 DEBUG 发票再关 DEBUG 注册」绕过。本地验证正式闸门可用，但纯 `DEBUG=false` 手工联调需开 DEBUG 日志或临时改流程——可接受，宜在 README 中心里有数（README 已偏 DEBUG 路径说明）。

5. **身份证哈希未做注册唯一性约束**  
   规格模型未强制 `id_card_hash` UNIQUE；实现也不查重。同一证件可注册多账号。DEBUG 本地无妨；若产品要「一证一号」需补查重/唯一索引。

6. **核验 API 无鉴权 + 仅按 target 限频**  
   符合注册前发码设计；无 IP/全局限流。DEBUG 本机可接受；公网暴露时有刷票/爆破面（confirm 有 bcrypt 成本，缓解有限）。

### Minor

1. **SQLite `ALTER` 补列不带 UNIQUE**（ledger）：存量库补上的 `email`/`phone` 可能缺少唯一约束；新建库 `create_all` 有 UNIQUE。文档已提示可删库重建。
2. **确认响应字段为 `data.ticket`**（ledger）：与注册体字段名 `sms_ticket`/`email_ticket`/`id_ticket` 不一致；前后端约定用通用 `ticket` 即可，非功能错误。
3. **规格 §12 验收勾选仍为 `- [ ]`**，计划 Task 勾选未改；状态行已写「已实现」，文档卫生问题。
4. **计划中的 `codes.py` / `tickets.py` 未拆文件**，逻辑集中在 `service.py`；可维护性偏好，不影响行为。
5. **HTTP 层 verification 无独立 pytest 套件**（进度称 ASGI smoke）；核心逻辑由 service 集成测覆盖。
6. **DEBUG 下 `submit_id` payload 记 `debug_skip`，用户 `id_verified_level` 在有票时仍写当前 `id_verify_mode`**——符合「有票则记实际 mode」定稿，审计上略粗糙。

---

## Gaps vs Spec（摘要）

| 规格项 | 状态 |
| --- | --- |
| 独立 verification API（6 端点） | ✅ |
| DEBUG 跳过 / 固定码 / id 直接发票 | ✅ |
| 正式缺材料 40017 + 三票注册 | ✅（测服用 DEBUG 发票技巧） |
| A 完整 / B·C stub + 50100 | ✅ |
| 超级密码任意环境 + 禁用拒绝 + WARNING | ✅ |
| 错误码 40010–40017 / 50100 | ✅（路径存在；非每码单测全覆盖） |
| `GET /modes` | ✅ |
| README / CHANGELOG / M0 §7 | ✅ |
| `EMAIL_PROVIDER=smtp` | ❌ 未接线（Important） |
| 前端注册核验 UI（§11） | ⏭ 规格标明后续 |

---

## SUPER_PASSWORD 安全结论（DEBUG 本地）

| 点 | 判断 |
| --- | --- |
| 默认空 → 未启用 | ✅ 安全默认 |
| 无硬编码 | ✅ |
| `compare_digest` + 不打明文 | ✅ |
| 不绕过 `is_active` | ✅ |
| 万能登录能力 | ⚠️ **有意为之**；本地勿设弱口令、勿提交 `.env` |
| 与生产同逻辑 | ⚠️ 规格确认；**非**「仅 DEBUG」开关——切生产前运维必须知情 |

**DEBUG 本地建议**：`SUPER_PASSWORD=` 留空即可日常开发；需要排障时临时设强随机串，用完清空。

---

## Verdict

**merge-ready（M0 / DEBUG 本地可用）：是**

功能相对规格闭环，测试 20 passed，文档已对齐；无 Critical 阻塞。  
**不视为生产加固完成**：超级密码全局旁路、无 IP 限流、smtp 缺口、证件未唯一等须在进生产前单独评估/修补。

**推荐用法**：本地 `DEBUG=true`、`SMS/EMAIL_PROVIDER=debug`、`SUPER_PASSWORD` 空；用固定码 `000000` 走 verification →（可选）带票注册；需要时再开超密排障。
