# Task 6 报告：注册改造 + 超级密码登录

## 完成情况

- [x] **Step 1：Schema + service**
  - `RegisterRequest` 扩展 `email` / `phone` / `real_name` / `id_card` / 三票
  - `register_user`：`assert_register_tickets`、email/phone 查重 `40013`、写扩展字段、成功后消费 ticket
  - `login_user`：用户密码失败后 `SUPER_PASSWORD` + `secrets.compare_digest` + WARNING；禁用号仍 `40300`
- [x] **Step 2：集成测试** `backend/tests/test_verification_auth.py`

## 行为摘要

| 场景 | 结果 |
| --- | --- |
| `DEBUG=true` 无 ticket 注册 | 成功；若带 email/phone 仍落库；verified 标志为 false；`id_verified_level=none` |
| `DEBUG=false` 缺材料 | `AppError(40017)` |
| 三票 + format 注册 | 成功；`email_verified`/`phone_verified=true`；`id_verified_level=format`；票 `consumed_at` 已写 |
| 邮箱/手机已占用 | `40013` |
| 超级密码登录 | 签发 JWT；日志 WARNING `super_password_login ...` |
| 错误密码 | `40002` |
| 禁用号 + 超级密码 | `40300`（定稿） |

## 测试结果

```
pytest tests/test_verification_auth.py -v
============================= test session starts =============================
collected 4 items

tests/test_verification_auth.py::test_debug_register_without_tickets PASSED
tests/test_verification_auth.py::test_non_debug_missing_tickets_returns_40017 PASSED
tests/test_verification_auth.py::test_full_ticket_register_success PASSED
tests/test_verification_auth.py::test_super_password_login_and_bad_password PASSED

============================== 4 passed in 2.30s ==============================
```

结论：**PASS**

## 涉及文件

| 路径 | 说明 |
| --- | --- |
| `backend/app/schemas/auth.py` | `RegisterRequest` 扩展与规范化 |
| `backend/app/services/auth_service.py` | 注册核验 + 消费票；超级密码登录 |
| `backend/app/api/auth.py` | 注册 docstring 同步 |
| `backend/tests/test_verification_auth.py` | 集成测试（临时 SQLite） |
| `README.md` / `CHANGELOG.md` | 文档同步 |

## 未做

- `git commit`（按约束未执行）
- Task 7 文档收尾（规格状态行 / M0 §7 步骤 3.5 标完成）留给后续

## 顾虑

- 正式模式缺材料由 `assert_register_tickets` 抛 `40017`；注册成功路径才 `_consume_ticket`，失败不废票。
- 完整三票用例：发码/确认阶段临时 `DEBUG=true` 拿票（固定码），再 `DEBUG=false` 注册，以覆盖正式材料检查而不依赖云厂商。

---

## Review Important 修复（2026-07-28）

### 修复项

1. **`login_user` 审计顺序**：先校验 `is_active`（禁用 → `40300`），再写 `super_password_login` WARNING；禁用号不再产生成功态审计。
2. **补测**：
   - `test_email_or_phone_conflict_returns_40013` — email/phone 冲突 → `40013`
   - `test_inactive_user_super_password_returns_40300` — 禁用 + 超密 → `40300`（`pytest.raises`，无 JWT）
   - `test_non_debug_missing_real_name_returns_40017` — 正式缺 `real_name` → `40017`
3. **正式模式强制 `real_name`**：`register_user` 在非 DEBUG 且缺 `real_name` 时抛 `AppError(40017)`（对齐设计 §5；`id_card` 仍由 tickets/`assert_register_tickets` 覆盖）。

### 复测结果

```
pytest tests/test_verification_auth.py -v
============================= test session starts =============================
collected 7 items

tests/test_verification_auth.py::test_debug_register_without_tickets PASSED
tests/test_verification_auth.py::test_non_debug_missing_tickets_returns_40017 PASSED
tests/test_verification_auth.py::test_full_ticket_register_success PASSED
tests/test_verification_auth.py::test_super_password_login_and_bad_password PASSED
tests/test_verification_auth.py::test_email_or_phone_conflict_returns_40013 PASSED
tests/test_verification_auth.py::test_inactive_user_super_password_returns_40300 PASSED
tests/test_verification_auth.py::test_non_debug_missing_real_name_returns_40017 PASSED

============================== 7 passed in 3.79s ==============================
```

结论：**7 passed**（PASS）
