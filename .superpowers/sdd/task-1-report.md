# Task 1 Report: Settings 与 .env.example

## Status

**DONE**

## Commits

none (N/A — no git repo / user forbids unsolicited commits)

## Summary

扩展 `backend/app/core/config.py` 中的 `Settings`，新增核验与超级密码相关 11 个字段（alias 与 brief 完全一致）；更新 `backend/.env.example` 注释说明；在本地 `backend/.env` 追加空 `SUPER_PASSWORD=`；同步更新 `README.md` 与 `CHANGELOG.md`。

## Files Changed

| File | Action |
| --- | --- |
| `backend/app/core/config.py` | Modified — 新增 11 个 `Field` |
| `backend/.env.example` | Modified — 追加核验/超级密码变量及中文注释 |
| `backend/.env` | Modified — 追加 `SUPER_PASSWORD=`（空值） |
| `README.md` | Modified — 后端环境变量表补充新项 |
| `CHANGELOG.md` | Modified — Unreleased 记录 |

## Settings Fields Added

| Python field | Env alias | Default |
| --- | --- | --- |
| `super_password` | `SUPER_PASSWORD` | `""` |
| `id_verify_mode` | `ID_VERIFY_MODE` | `"format"` |
| `id_card_hash_salt` | `ID_CARD_HASH_SALT` | `"dev-id-salt-change-me"` |
| `sms_provider` | `SMS_PROVIDER` | `"debug"` |
| `email_provider` | `EMAIL_PROVIDER` | `"debug"` |
| `id_two_factor_provider` | `ID_TWO_FACTOR_PROVIDER` | `"stub"` |
| `id_real_person_provider` | `ID_REAL_PERSON_PROVIDER` | `"stub"` |
| `verify_code_ttl_seconds` | `VERIFY_CODE_TTL_SECONDS` | `300` |
| `verify_ticket_ttl_seconds` | `VERIFY_TICKET_TTL_SECONDS` | `600` |
| `verify_send_interval_seconds` | `VERIFY_SEND_INTERVAL_SECONDS` | `60` |
| `debug_verify_code` | `DEBUG_VERIFY_CODE` | `"000000"` |

## Verification

**Command:**

```powershell
cd backend; .\.venv\Scripts\python.exe -c "from app.core.config import get_settings; s=get_settings(); print(s.id_verify_mode, s.debug, bool(s.super_password))"
```

**Output:**

```
format True False
```

**Expected:** `format True False`（或本地自定义值）

**Result:** PASS — 与预期一致。

## Concerns

None.

## Out of Scope (Not Done)

- 未实现 Task 2+（verification API、provider 实现、超级密码逻辑等）
- 未向 `.env` 写入真实超级密码值
- 未执行 git commit
