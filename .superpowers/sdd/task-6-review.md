# Task 6 Review：注册改造 + 超级密码登录

**Reviewer:** Subagent (read-only, security-sensitive)  
**Date:** 2026-07-28  
**Brief:** `.superpowers/sdd/task-6-brief.md`  
**Report:** `.superpowers/sdd/task-6-report.md`  
**Design:** `docs/superpowers/specs/2026-07-28-verification-super-password-design.md` §5–§6 / §10

---

## Spec ✅

实现与 brief / 设计规格核心行为一致，可按代码验收；brief Step 2 四项用例均有对应测试。

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| 1. `secrets.compare_digest` 比对超级密码 | ✅ | `auth_service.login_user` L242–245；先判 `settings.super_password` 非空再比对 |
| 2. 禁用号即使用超级密码仍 `40300` | ✅ 代码 | L255–258：密码/超密通过后统一 `if not user.is_active` → `40300` |
| 3. DEBUG vs 非 DEBUG 注册 ticket 规则 | ✅ | 调 `assert_register_tickets(..., debug=settings.debug)`；正式缺材料 `40017`；DEBUG 可缺票 |
| 4. 注册成功后消费 ticket | ✅ | `_consume_ticket` 在用户 `flush` 之后；失败路径不消费（与 Task 4 分工一致） |
| 5. email/phone 冲突 `40013` | ✅ 代码 | L156–167；`User.email` / `User.phone` 有 UNIQUE |
| 6. 密码 / 超级密码不落明文日志 | ✅ | 仅 `super_password_login user_id=… username=…`；失败只打 username；无 password 字段 |
| 7. 测试覆盖 brief Step 2 四案 | ✅ | 4 passed（report）；`test_verification_auth.py` 对齐 brief 1–4 |

---

## Findings

### Critical

无。

### Important

1. **安全回归用例缺口（相对 report 声称行为）**  
   Report 行为表写明「邮箱/手机已占用 → `40013`」「禁用号 + 超级密码 → `40300`」，代码路径正确，但 `test_verification_auth.py` **未覆盖**：
   - 重复 email / phone → `40013`
   - `is_active=False` + `SUPER_PASSWORD` → `40300`（且不得签发 JWT）  
   属安全敏感定稿行为，建议补测后再合入闭环。

2. **超级密码 WARNING 写在 `is_active` 检查之前**  
   禁用账号用超级密码登录时，仍会先打 `super_password_login`，再抛 `40300`。审计上像「超密已登录成功」实则被拒，不符合设计「签发 JWT 时 WARNING」的语义。建议将 WARNING 挪到 `is_active` 通过之后、签发令牌之前。

3. **正式模式未强制 `real_name`**  
   设计 §5 正式模式 `real_name` 必填；`assert_register_tickets` 只检查 phone/sms、email/email_ticket、id_card/id_ticket，**不检查 `real_name`**。可在有 `id_ticket` 时以 `real_name=None` 注册成功。若定稿要求姓名入库，应在 `assert_register_tickets` 或 `register_user` 补 `40017`。

### 通过项（核心）

1. **超密比对** — 与 brief 片段一致：`secrets.compare_digest` + 非空门闩；失败仍 `40002`，不单独暴露超密错误码。  
2. **禁用优先于签发** — 用户密码或超密通过后仍拦 `is_active=False` → `40300`，符合设计定稿。  
3. **注册核验** — DEBUG 可无票；非 DEBUG 缺材料 `40017`；有票则校验目标一致 / 未消费 / 未过期（`40012`）。  
4. **票消费时机** — assert 不写 `consumed_at`；成功落库后 `_consume_ticket`；`test_full_ticket_register_success` 断言三票 `consumed_at` 非空。  
5. **查重** — email / phone 提供时查重 → `40013`；用户名仍 `40001`。  
6. **日志卫生** — 注册/登录日志不含 password / SUPER_PASSWORD；证件仅哈希+脱敏入库。  
7. **Schema** — `RegisterRequest` 扩展字段齐全；空串→None；email/phone/id_card 规范化与 verification 侧对齐。

### 非阻塞备注

1. **并发占用** — 查重后 insert 依赖 DB UNIQUE；竞态时可能冒出 SQLAlchemy `IntegrityError` 而非 `40013`。可后续统一映射。  
2. **brief 源文件中文乱码** — 与 plan Task 6 对照无歧义。  
3. **完整三票用例** — 发码阶段临时 `DEBUG=true` 再关 DEBUG 注册；report 已说明，联调合理。

---

## Checklist（对照本次审查要求）

| # | 项 | 判定 |
| --- | --- | --- |
| 1 | `secrets.compare_digest` | ✅ |
| 2 | 禁用 + 超密 → `40300` | ✅ 实现 / ❌ 缺测 |
| 3 | DEBUG / 非 DEBUG ticket 规则 | ✅ |
| 4 | 注册成功消费 ticket | ✅ |
| 5 | `40013` email/phone | ✅ 实现 / ❌ 缺测 |
| 6 | 无明文密码日志 | ✅ |
| 7 | brief 四案测试 | ✅ |

---

## Verdict

**Changes requested**

Spec 实现达标（Spec ✅），无 Critical。请先处理 Important：

1. 补测：`40013`、禁用号 + 超级密码 → `40300`（无 token）  
2. 将 `super_password_login` WARNING 移到 `is_active` 通过之后  

可选：正式模式强制 `real_name`（对齐设计 §5）。

完成上述后可再审为 Approved。
