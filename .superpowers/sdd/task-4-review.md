# Task 4 Review：verification service（发码 / 确认 / ticket）

**Reviewer:** Subagent (read-only)  
**Date:** 2026-07-28  
**Brief:** `.superpowers/sdd/task-4-brief.md`  
**Report:** `.superpowers/sdd/task-4-report.md`

---

## Spec ✅

实现与 brief 所列 Produces、逻辑要点及 Step 1–2 范围一致，可验收。

| Brief 要求 | 验证结果 |
| --- | --- |
| `send_sms(session, phone) -> None` | ✅ 间隔检查 → bcrypt 写 challenge → `send_sms_code` |
| `confirm_sms(session, phone, code) -> str` | ✅ 验码后同行写入 `token_urlsafe(32)` ticket |
| `send_email` / `confirm_email` 同上 | ✅ channel=`email`，target 小写规范化 |
| `submit_id(..., face_token=None) -> str` | ✅ DEBUG 直发票；正式调 `verify_identity`；target=`hash_id_card` |
| `assert_register_tickets(...)` | ✅ 正式缺材料 `40017`；票无效/过期/不匹配/已消费 `40012`；不标 `consumed_at` |
| `get_modes() -> dict` | ✅ 返回 `ModesData.model_dump()` |
| 发送前查同 `channel+target` 最近一条 → 未超间隔 `40011` | ✅ `_assert_send_interval` |
| code 存 `hash_password`；确认用 `verify_password` / compare | ✅ bcrypt + DEBUG `compare_digest(debug_verify_code)` |
| DEBUG 接受 `settings.debug_verify_code` | ✅ 生成码与确认兜底均覆盖 |
| ticket TTL=`verify_ticket_ttl_seconds`；同行或新行 | ✅ SMS/Email 同行更新；`submit_id` 新行 |
| `submit_id` payload 含 mode | ✅ DEBUG `debug_skip`；正式为 `id_verify_mode` |
| Step 1：service + schemas | ✅ 两文件齐全，Schema 覆盖 Task 5 六端点请求/响应 |
| Step 2：DEBUG send/confirm 可测 `40010`/`40011`/ticket | ✅ report 冒烟 PASS（服务层直调；HTTP 信封留 Task 5） |

---

## Findings

### 通过项（核心）

1. **编排完整性** — `service.py` 导出 brief 要求的 7 个公开函数；渠道常量 `sms`/`email`/`id` 与设计 §7 `verification_challenges.channel` 对齐。
2. **发码 / 确认** — 发送频率按 `created_at` 与 `verify_send_interval_seconds` 比较；验证码 bcrypt 哈希、过期用 `verify_code_ttl_seconds`；确认成功后 `expires_at` 切换为 ticket TTL。
3. **身份核验** — DEBUG 跳过 Provider 并写 `payload_json`；正式模式委托 Task 3 `verify_identity`，错误码透传（如 `40014`/`50100`）。
4. **注册前校验** — `assert_register_tickets` 正式模式三项材料齐全性检查；有票则 `_load_valid_ticket` 校验 channel/target/过期/消费；故意不写 `consumed_at` 与 report/Task 6 分工一致。
5. **Schema** — `verification.py` 含 SMS/Email Send·Confirm、`IdSubmitRequest`、`TicketData`、`ModesData`；手机号/邮箱/验证码规范化可在 Task 5 路由层直接复用。
6. **日志与安全** — 发码/发票打 INFO 不含明文验证码；ticket 长度 43 落在 `String(64)` 内。
7. **文档** — `README.md`、`CHANGELOG.md` 已同步 Task 4 说明。

### Important

1. **`id_card` 规范化不一致** — `IdSubmitRequest` 将末位 `x` 统一为大写 `X`，但 `submit_id` / `assert_register_tickets` 仅 `strip()`。若 Task 6 注册路径未复用同一 validator，可能出现「已拿到 `id_ticket` 但注册校验 target 不匹配 → `40012`」。建议在服务层统一规范化，或 Task 6 强制复用 `IdSubmitRequest` 规则。

### 非阻塞备注（已知 / 后续任务）

1. **Step 2 未做 httpx HTTP** — brief 字面写 httpx；report 为服务层 + `AsyncSession` 直调冒烟。HTTP `code=0` + `data.ticket` 属 Task 5；当前服务层返回 ticket 字符串，可接受。
2. **无 verification service 自动化测试入库** — 冒烟仅 report 自述；与 Task 3 类似，集成/单测可随 Task 5–6 补充。
3. **DEBUG 确认兜底** — `compare_digest(debug_verify_code)` 可在哈希不一致时仍通过；report 已标注，仅限联调。
4. **同一 challenge 行可重复 confirm** — 未发新码时再次 confirm 会覆盖同行 ticket；M0 可接受，Task 6 消费后自然失效。
5. **brief 源文件部分中文乱码** — 不影响与 plan/spec 及代码对照。

---

## Verdict

**Approved**

Task 4 服务层与 Schema 交付齐全，错误码与 brief 逻辑要点一致，文档已同步。可进入 Task 5（verification HTTP API）。Task 6 接入时注意 `id_card` 规范化一致性。
