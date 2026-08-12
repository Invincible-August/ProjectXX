# Task 2 报告：User / VerificationChallenge 模型

## 完成情况

- [x] Step 1：扩展 `User`（`backend/app/db/models/user.py`）
  - 新增字段：`email`（unique, index）、`phone`（unique, index）、`real_name`、
    `id_card_hash`（index）、`id_card_masked`、`id_verified_level`（默认 `"none"`）、
    `email_verified`（默认 `False`）、`phone_verified`（默认 `False`）
  - 全部与 brief 中的类型 / 约束一致；新增字段均加中文注释说明用途
- [x] Step 2：新建 `VerificationChallenge`（`backend/app/db/models/verification.py`）
  - 字段：`id`、`channel`、`target`、`code_hash`（nullable）、`ticket`（unique, nullable）、
    `payload_json`（Text, nullable）、`expires_at`、`consumed_at`（nullable）、`created_at`
  - 未实现任何验证码生成 / 校验逻辑，仅数据结构（符合"不实现核验 API/Provider"约束）
- [x] Step 3：导出模型（`backend/app/db/models/__init__.py`）
  - `__all__ = ["User", "VerificationChallenge"]`
  - `main.py` 中 `from app.db import models` 保持不变，`Base.metadata.create_all` 能感知新模型
- [x] Step 4：SQLite 列补丁（`backend/app/main.py`）
  - 新增 `_USER_TABLE_COLUMN_PATCHES` 清单（8 个新列的列名 + DDL 类型/默认值）
  - 新增 `_patch_sqlite_missing_user_columns(connection)` 同步函数：
    `PRAGMA table_info(users)` 读取现有列 → 对缺失列执行 `ALTER TABLE users ADD COLUMN ...`
  - `lifespan` 中 `create_all` 之后，若 `engine.dialect.name == "sqlite"` 则
    `await connection.run_sync(_patch_sqlite_missing_user_columns)`
  - `verification_challenges` 是全新表，`create_all` 直接建出，无需补丁
- [x] Step 5：冒烟测试（见下）

## 测试结果

使用项目虚拟环境 `backend/.venv` 执行冒烟脚本（`create_all` + SQLite 列补丁）：

1. **首次运行**：`verification_challenges` 表被创建（含 3 个索引），`users` 表 8 个新列
   全部通过 `ALTER TABLE` 成功补齐，日志逐列打印 `sqlite column patched table=users column=...`。
   最终 `import app.db.models` 得到 `User`、`VerificationChallenge` 均正常。
2. **二次运行（幂等性验证）**：`PRAGMA table_info(users)` 检测到列已存在，未再执行任何
   `ALTER TABLE`，无报错，输出 `IDEMPOTENT OK`。

结论：模型定义、导出、`create_all` 与 SQLite 补列逻辑均按预期工作，存量 `xiuxian.db`
可安全升级到新 schema，不需要删库重建。

## 涉及文件

- 修改：`backend/app/db/models/user.py`
- 新建：`backend/app/db/models/verification.py`
- 修改：`backend/app/db/models/__init__.py`
- 修改：`backend/app/main.py`（新增列补丁清单 + `_patch_sqlite_missing_user_columns` + lifespan 调用）

## 顾虑 / 后续注意事项

- SQLite 的 `ALTER TABLE ADD COLUMN` 不支持在事务中动态添加 `UNIQUE` 约束，因此
  `email`、`phone`（User 上应为 unique）在补丁 DDL 中**未**声明 `UNIQUE`，仅在 ORM 层
  面（新建库场景）通过 `create_all` 生成唯一索引。若存量库需要唯一性保证，需后续用
  Alembic 迁移单独补建唯一索引（当前任务范围不含此项，Task 3+ 或专门的迁移任务应关注）。
- `id_verified_level` 补丁默认值写作 SQLite 字面量 `'none'`，与 ORM 层 `default="none"`
  语义一致；`email_verified` / `phone_verified` 用 `0` 代表 `False`，与 SQLAlchemy Boolean
  在 SQLite 上的整数存储方式一致。
- 未涉及验证码发送、核验校验、`ticket` 签发等业务逻辑，均留给 Task 3+。
- 未执行 `git commit`（按全局约束）。
