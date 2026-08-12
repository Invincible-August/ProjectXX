# Task 4 报告：verification service（发码 / 确认 / ticket）

## 完成情况

- [x] **Step 1：实现 service + schemas**
  - `backend/app/services/verification/service.py`
  - `backend/app/schemas/verification.py`
- [x] **Step 2：DEBUG 下 send/confirm 冒烟**（直接调服务函数 + `AsyncSession`，未挂 HTTP）

## API 表面（服务层）

| 函数 | 行为 |
| --- | --- |
| `send_sms(session, phone)` | 间隔检查 → 写 challenge（code bcrypt）→ `send_sms_code` |
| `confirm_sms(session, phone, code) -> ticket` | 验码 → 同行签发 `token_urlsafe(32)` |
| `send_email` / `confirm_email` | 同上，channel=`email` |
| `submit_id(...)` | DEBUG 直接发票；正式调 `verify_identity`；target=`hash_id_card` |
| `assert_register_tickets(...)` | 正式缺材料 `40017`；票无效 `40012`；**不**标 consumed |
| `get_modes() -> dict` | debug / id_verify_mode / 各 provider |

## 错误码

| code | 场景 |
| --- | --- |
| `40010` | 验证码错误或过期 |
| `40011` | 发送间隔未到 |
| `40012` | ticket 无效/过期/不匹配/已消费 |
| `40014` | 正式模式身份证格式失败（经 Provider） |
| `40017` | 正式模式缺核验材料 |
| `50100` | Provider 未配置（经工厂透传） |

## 冒烟结果

DEBUG=`true`，固定码 `000000`，独立临时 SQLite：

| 步骤 | 结果 |
| --- | --- |
| `get_modes` | OK（含 `id_verify_mode=format`） |
| `send_sms` → 再发 | `40011` |
| 错码 `111111` | `40010` |
| `confirm_sms('000000')` | ticket 长度 43 |
| `send_email` / `confirm_email` | OK |
| `submit_id` | OK |
| `assert_register_tickets`（三票） | OK |
| 伪造 sms_ticket | `40012` |

结论：**SMOKE PASS**

## 涉及文件

| 路径 | 说明 |
| --- | --- |
| `backend/app/services/verification/service.py` | 编排服务 |
| `backend/app/schemas/verification.py` | 请求/响应 Schema（供 Task 5 复用） |
| `README.md` / `CHANGELOG.md` | 文档同步 |

## 未做（留给后续）

- HTTP 路由（Task 5）
- 注册消费 ticket / 登录超级密码（Task 6）
- `git commit`（按约束未执行）

## 顾虑

- `assert_register_tickets` 故意不写 `consumed_at`，避免注册失败废票；Task 6 成功落库后需标记消费。
- DEBUG 下 `confirm` 额外接受 `debug_verify_code`（`compare_digest`），即使与库内哈希不一致也可通。
- `submit_id` 在 DEBUG 时 payload.mode=`debug_skip`；正式为实际 `id_verify_mode`。

---

## Task 4 Review 修复：`id_card` 规范化一致（2026-07-28）

### 问题

Review Important finding：`IdSubmitRequest` Schema 会将证件号 `strip` 且末位 `x→X`，但 `submit_id` / `assert_register_tickets` 原先仅 `strip()`，可能导致「已签发 `id_ticket` 但注册比对 target 不匹配 → `40012`」。

### 修复

| 文件 | 变更 |
| --- | --- |
| `backend/app/services/verification/id_card_util.py` | 新增 `normalize_id_card()`；`hash_id_card` / `mask_id_card` 哈希/脱敏前先规范化 |
| `backend/app/services/verification/service.py` | `submit_id`、`assert_register_tickets` 调用 `normalize_id_card`，与 Schema 规则对齐 |
| `backend/tests/test_id_format.py` | 新增 2 条规范化/哈希一致性断言 |

### 测试结果

```
pytest tests/test_id_format.py -v  →  13 passed
```

新增用例：

- `test_normalize_id_card_strip_and_uppercase_x` — PASSED
- `test_hash_id_card_treats_lowercase_x_as_uppercase` — PASSED

结论：**FIX VERIFIED**（未执行 git commit）
