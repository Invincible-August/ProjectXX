# Task 1 Review: Settings 与 .env.example

**Reviewer:** Code review (read-only)  
**Date:** 2026-07-28  
**Verdict:** **Changes requested**

---

## 1. Spec compliance: ❌

| Requirement | Status | Notes |
| --- | --- | --- |
| 11 个 Settings 字段（alias / 默认值与 brief 一致） | ✅ | `config.py` L62–91 与 brief 完全对齐 |
| 更新 `backend/.env.example` 注释 | ⚠️ | 变量齐全，但 `ID_VERIFY_MODE` 注释枚举值错误（见 Important #1） |
| 本地 `.env` 可选追加空 `SUPER_PASSWORD=` | ✅ | 报告已说明；未提交真实密码 |
| 验证命令输出 `format True False` | ✅ | 独立复现通过 |
| 标识符 English / 注释 Chinese | ✅ | `config.py`、`.env.example` 符合 |
| 密钥仅来自 env | ✅ | 无硬编码 API 密钥；`super_password` 默认 `""` |
| `ID_VERIFY_MODE` 允许值与 plan 一致 | ❌ | `.env.example` 写为 `hash`/`provider`，plan 要求 `two_factor`/`real_person` |

---

## 2. Findings

### Critical

（无）

### Important

1. **`.env.example` 中 `ID_VERIFY_MODE` 注释与 plan/spec 不一致**  
   - 当前（L27）：`format（仅格式）\| hash（哈希比对）\| provider（外部实人）`  
   - 设计规格 [`2026-07-28-verification-super-password-design.md`](../../docs/superpowers/specs/2026-07-28-verification-super-password-design.md) §3：`format \| two_factor \| real_person`  
   - 实现计划与 M0 前端设计均引用同一套 A/B/C 模式名。错误注释会导致后续 Task 2+ 实现与运维配置偏离规格。  
   - **Fix:** 将注释改为 `format（仅格式）\| two_factor（二要素）\| real_person（实人核验）`（或等价中文说明，枚举字面量必须为上述三者）。

### Minor

1. **`Settings.id_verify_mode` 无运行时枚举校验** — brief 仅要求 `str`，当前可接受任意字符串；Task 2 编排层需校验或在 Settings 增加 `Literal`/validator，避免无效 mode 静默流入业务逻辑。  
2. **`README.md` 环境变量表未列出 `ID_VERIFY_MODE` 允许值** — 仅写「默认 `format`」；非 brief 硬性要求，但与 design spec 对齐时可补充 `format \| two_factor \| real_person`。  
3. **README / CHANGELOG 同步** — 超出 brief 两文件范围，但符合项目「改功能同步文档」约定；CHANGELOG 条目准确，**不视为 excess**。

---

## 3. Task quality: **Changes requested**

**通过项：** 11 个 Field 定义、alias、默认值、`.env.example` 变量块、Settings 可加载性均达标；验证命令独立复现 PASS。

**阻塞项：** `.env.example` 中 `ID_VERIFY_MODE` 文档枚举与 plan 不符，必须在合并/进入 Task 2 前修正。

**建议（非阻塞）：** Task 2 或本 Task 收尾时考虑在 Settings 或 service 层对 `id_verify_mode` 做允许值校验，与 design spec §3 保持一致。

---

## 4. Verification evidence

```text
> cd backend; .\.venv\Scripts\python.exe -c "from app.core.config import get_settings; s=get_settings(); print(s.id_verify_mode, s.debug, bool(s.super_password))"
format True False
```

与 implementer 报告及 brief 预期一致。
