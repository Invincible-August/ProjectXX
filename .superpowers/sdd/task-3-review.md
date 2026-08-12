# Task 3 Review：ID / SMS / Email Providers

**Reviewer:** Subagent (read-only)  
**Date:** 2026-07-28  
**Brief:** `.superpowers/sdd/task-3-brief.md`  
**Report:** `.superpowers/sdd/task-3-report.md`

---

## Spec ✅

实现与 brief 所列 Step 1–5 及 Produces 条目一致，可验收。

| Brief 要求 | 验证结果 |
| --- | --- |
| `validate_id_card_format` 失败抛 `AppError(40014)` | ✅ `providers/id_format.py` 全部失败路径均为 `40014` + `http_status=400` |
| `hash_id_card` / `mask_id_card` | ✅ `id_card_util.py`：SHA-256(salt+id)、前3+`*`+后4 |
| `verify_identity` 按 mode 路由 A/B/C | ✅ `__init__.py`：`format` / `two_factor` / `real_person`；未知 mode → `50100` |
| SMS/Email `async send_code(target, code)` | ✅ debug 实现 + 工厂 `send_sms_code` / `send_email_code` |
| 非 debug / 未实现 Provider → `AppError(50100)` | ✅ B/C stub、aliyun/tencent/resend 骨架、未知 provider 路由均 `50100` + `http_status=501` |
| Step 1 国标 18 位校验位 | ✅ 正则、地址码粗检、出生日期、GB 11643 权重与映射 |
| Step 2 B/C stub | ✅ 与 brief 伪代码一致（debug 跳过；stub→未配置；其它→尚未接入） |
| Step 3 debug SMS/Email | ✅ INFO 提示已发送；仅 `settings.debug` 时 DEBUG 级打印明文码 |
| Step 4 厂商骨架 | ✅ `sms_aliyun`、`sms_tencent`、`email_aliyun`、`email_resend` 签名对齐且恒定 50100 |
| Step 5 单元测试 | ✅ `pytest tests/test_id_format.py -v` → **11 passed**（复核通过） |

---

## Findings

### 通过项（核心）

1. **Provider A（格式校验）** — `id_format.py` 实现完整：18 位模式、首位非 0、合法日历日且不晚于今天、校验位大小写 X 兼容。测试号 `110101199003074477` 与 X 后缀用例均通过。
2. **Provider B/C（stub）** — `id_two_factor.py`、`id_real_person.py` 行为与 brief 一致；C 接受可选 `face_token`。
3. **工厂与工具** — `verify_identity`、`send_sms_code`、`send_email_code` 路由清晰；`hash_id_card` 使用 `settings.id_card_hash_salt`；`mask_id_card` 输出与测试期望 `110***********4477` 一致。
4. **SMS/Email** — debug 不调用外部网关；厂商文件为骨架，符合 M0「未接入即 50100」策略。
5. **配置** — `config.py` 含 `ID_VERIFY_MODE`、`SMS_PROVIDER`、`EMAIL_PROVIDER`、`ID_TWO_FACTOR_PROVIDER`、`ID_REAL_PERSON_PROVIDER`、`ID_CARD_HASH_SALT` 等字段，默认值与 report 描述一致。
6. **文档** — `README.md`、`CHANGELOG.md` 已同步 Task 3 说明与测试命令。

### 非阻塞备注（已知 / 后续任务）

1. **B/C 在 `DEBUG=true` 时直接放行** — report 已标注；生产须 `DEBUG=false`，否则二要素/实人误放行。属设计预期，非 Task 3 缺陷。
2. **`verify_identity` 在 B/C 模式不自动先跑 A** — report 明确由 Task 4 `submit_id` 决定是否先格式校验；与 brief 范围一致。
3. **无 B/C/SMS/Email 单测** — brief Step 5 仅要求格式校验测试；当前覆盖足够 Task 3，集成测试可留 Task 4+。
4. **brief 源文件部分中文乱码** — 不影响实现对照；report 与代码为可读中文。

### 测试复核

```text
.\.venv\Scripts\python.exe -m pytest tests/test_id_format.py -v
→ 11 passed in 0.12s
```

---

## Verdict

**Approved**

Task 3 交付物齐全、错误码正确、测试通过，与 brief/report 一致。可进入 Task 4（verification HTTP API / 注册链路集成）。
