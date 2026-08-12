# Task 2 Review: User / VerificationChallenge 模型

**Reviewer:** Code review (read-only)  
**Date:** 2026-07-28  
**Verdict:** **Approved**

---

## 1. Spec compliance: ✅

| Requirement | Status | Notes |
| --- | --- | --- |
| Step 1：`User` 8 个新列（类型 / unique / index / default） | ✅ | `user.py` L27–36 与 brief 代码块逐字段一致 |
| Step 2：`VerificationChallenge` 表（指定字段） | ✅ | `verification.py` 含 `id`, `channel`, `target`, `code_hash`, `ticket`, `payload_json`, `expires_at`, `consumed_at`, `created_at` |
| Step 3：导出模型；`main` lifespan 保持 `create_all` | ✅ | `__init__.py` 导出 `User`, `VerificationChallenge`；`main.py` L24/L78 保留 `from app.db import models` + `create_all` |
| Step 4：SQLite 列补丁（`PRAGMA` + `ALTER TABLE`） | ✅ | `_USER_TABLE_COLUMN_PATCHES` + `_patch_sqlite_missing_user_columns` 在 `create_all` 之后、仅 `sqlite` 方言执行 |
| Step 5：冒烟（无报错） | ✅ | 实现者报告已验证；本次 read-only 审查未独立重跑命令，代码路径与报告描述一致 |
| 全局：中文注释 | ✅ | `user.py`、`verification.py`、`main.py` 补丁段均有中文模块/字段说明 |
| 全局：SQLite ALTER 补丁 | ✅ | 8 列补丁清单与 ORM 类型/默认值语义对齐 |
| 范围：不实现核验 API / Provider | ✅ | 仅 ORM 数据结构，无业务逻辑泄漏 |

---

## 2. Findings

### Critical

（无）

### Important

（无）

### Minor

1. **SQLite 存量库补列时 `email` / `phone` 无 DB 级 UNIQUE**  
   - `ALTER TABLE ADD COLUMN` 无法在补丁中声明 `UNIQUE`；实现者已在报告中说明，新建库仍由 `create_all` 生成唯一约束。  
   - 与 brief Step 4「类型与默认值匹配」一致；按审查指引视为已接受限制。  
   - **后续：** Task 3+ 或专用迁移任务若需存量库唯一性，可用 Alembic / 手工 `CREATE UNIQUE INDEX`。

2. **SQLite 存量库补列时未补建 `email` / `phone` / `id_card_hash` 索引**  
   - ORM 上 `index=True`，但补丁 DDL 仅 `ADD COLUMN`，与 UNIQUE 同类 SQLite 限制。  
   - 对 M0 本地小规模数据影响可忽略；生产迁移阶段再统一索引策略即可。

3. **`CHANGELOG.md` / `README.md` 未记录 Task 2 模型变更**  
   - brief 未硬性要求，但项目约定「改功能同步文档」。  
   - 建议在 CHANGELOG `[Unreleased]` 增加 `User` 扩展列与 `verification_challenges` 表条目；README 可在「当前进度」或数据库说明处一句带过 SQLite 自动补列行为。

4. **`VerificationChallenge` 额外索引与字段长度**  
   - brief 未规定 `channel`/`target`/`ticket` 的 `String` 长度及 index；实现选用 `String(32/255/128/64)` 并给 `channel`、`target`、`ticket` 加 index，属于合理扩展，非 spec 偏差。

5. **`main.py` L17–18 多余空行** — 纯格式，不影响行为。

---

## 3. Task quality: **Approved**

**通过项：**

- `User` 扩展字段与 brief / design spec §7 `users` 表定义一致。  
- `VerificationChallenge` 覆盖 design spec §7 全部列；`code_hash` / `ticket` / `payload_json` 可空性与 brief 一致。  
- 补丁逻辑幂等（先 `PRAGMA table_info` 再条件 `ALTER`），且运行在 `engine.begin()` 同一事务内。  
- 补丁参数来自硬编码元组，无 SQL 注入面。  
- `verification_challenges` 新表交由 `create_all` 创建，符合 Step 4 说明。  
- 中文注释覆盖新增核验相关字段与补丁意图。

**非阻塞建议：**

- 合并前或 Task 3 启动前，在 CHANGELOG 补一条 Task 2 变更摘要。  
- 若团队希望在文档中显式记录 SQLite 补列限制，可在 `README.md` 本地运行节加一句：存量 `xiuxian.db` 启动时自动补列，但 UNIQUE/INDEX 仅对新库 `create_all` 生效。

---

## 4. Verification evidence

本次为 **read-only** 审查，未独立执行冒烟命令。对照源码与 implementer 报告：

- 补丁清单 8 项与 `user.py` 新增列一一对应（L35–44 ↔ L27–36）。  
- `lifespan` 顺序：`create_all` → `sqlite` 补丁 → log（L77–82）。  
- 报告声称首次补列、二次幂等均 PASS；代码结构支持该结论。

若需复核，可在 `backend` 目录执行 implementer 报告中的 `create_all` + 补丁脚本，或启动 `uvicorn app.main:app` 观察 `database schema ready` 与 `sqlite column patched` 日志。

---

## 5. Summary

| 维度 | 结果 |
| --- | --- |
| **Spec** | ✅ |
| **Critical** | 0 |
| **Important** | 0 |
| **Minor** | 5 |
| **Verdict** | **Approved** |

Task 2 实现符合 brief 全部 5 步与全局约束（中文注释、SQLite ALTER 补丁、无 git commit）。无阻塞项；Minor 项均为文档同步与 SQLite 平台已知限制，可在后续任务或文档 PR 中处理。
