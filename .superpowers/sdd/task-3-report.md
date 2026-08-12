# Task 3 报告：ID / SMS / Email Providers

## 完成情况

- [x] **Step 1：国标 18 位校验位**（`providers/id_format.py`）
  - `validate_id_card_format(id_card) -> None`
  - 正则：前 17 位数字 + 末位 `0-9/Xx`
  - 地址码粗检：首位不为 `0`
  - 出生日期：`YYYYMMDD` 合法日历日且不晚于今天
  - 校验位：GB 11643 权重 `(7,9,10,5,8,4,2,1,6,3,7,9,10,5,8,4,2)`，余数映射 `"10X98765432"`
  - 失败统一抛 `AppError(40014, ..., http_status=400)`
- [x] **Step 2：B/C stub**
  - `id_two_factor.verify_two_factor(*, real_name, id_card)`：`debug` 直接 return；`stub` → 50100「未配置」；其它 → 50100「尚未接入」
  - `id_real_person.verify_real_person(*, real_name, id_card, face_token=None)`：同上逻辑（实人文案）
- [x] **Step 3：debug SMS/Email**
  - `sms_debug.send_code` / `email_debug.send_code`：`logger.info` 提示已发送（不写明文码到 INFO）；仅 `settings.debug` 时 `logger.debug` 打印明文码
- [x] **Step 4：aliyun / tencent / resend 骨架**
  - `sms_aliyun`、`sms_tencent`、`email_aliyun`、`email_resend`：签名与 debug 对齐，恒定 `raise AppError(50100, ..., http_status=501)`
- [x] **Step 5：单元测试**（见下）
- [x] **工厂 / 工具**
  - `id_card_util.hash_id_card`：SHA-256(`id_card_hash_salt` + `id_card`)
  - `id_card_util.mask_id_card`：前 3 + `*` + 后 4
  - `verify_identity`：按 `id_verify_mode` 路由 `format` / `two_factor` / `real_person`，未知 mode → 50100
  - `send_sms_code` / `send_email_code`：按 `sms_provider` / `email_provider` 路由，未知 → 50100

## 测试结果

命令（`backend/.venv`）：

```text
.\.venv\Scripts\python.exe -m pytest tests/test_id_format.py -v
```

结果：**11 passed**（约 0.10s）

| 用例 | 结果 |
| --- | --- |
| `test_id_card_checksum_valid`（合成合法号 `110101199003074477`） | PASSED |
| `test_id_card_checksum_invalid`（篡改校验位 → 40014） | PASSED |
| `test_id_card_format_rejects_invalid_inputs` × 6 | PASSED |
| `test_id_card_checksum_x_suffix`（校验位 X/x） | PASSED |
| `test_hash_id_card_is_deterministic_and_not_plaintext` | PASSED |
| `test_mask_id_card_pattern`（`110***********4477`） | PASSED |

测试号为满足校验位算法的合成/教学用号，非真实自然人证件。

## 涉及文件

| 路径 | 说明 |
| --- | --- |
| `backend/app/services/verification/__init__.py` | 工厂：`verify_identity` / `send_sms_code` / `send_email_code` |
| `backend/app/services/verification/id_card_util.py` | `hash_id_card` / `mask_id_card` |
| `backend/app/services/verification/providers/__init__.py` | Provider 子包说明 |
| `backend/app/services/verification/providers/id_format.py` | A：格式+校验位 |
| `backend/app/services/verification/providers/id_two_factor.py` | B：stub |
| `backend/app/services/verification/providers/id_real_person.py` | C：stub + `face_token` |
| `backend/app/services/verification/providers/sms_debug.py` | 短信 debug |
| `backend/app/services/verification/providers/sms_aliyun.py` | 短信阿里云骨架 |
| `backend/app/services/verification/providers/sms_tencent.py` | 短信腾讯云骨架 |
| `backend/app/services/verification/providers/email_debug.py` | 邮件 debug |
| `backend/app/services/verification/providers/email_aliyun.py` | 邮件阿里云骨架 |
| `backend/app/services/verification/providers/email_resend.py` | 邮件 Resend 骨架 |
| `backend/tests/test_id_format.py` | 格式/哈希/脱敏单测 |
| `README.md` / `CHANGELOG.md` | 文档同步 |

## 未做（按约束留给后续任务）

- 验证码 HTTP API、注册/登录改造（Tasks 4–6）
- 真实厂商 SDK 接入
- `git commit`（按全局约束未执行）

## 顾虑 / 后续注意事项

- B/C 在 `debug=True` 时跳过真实核验；生产须 `DEBUG=false`，否则二要素/实人会误放行。
- `verify_identity` 在 `two_factor` / `real_person` 模式**不**自动先跑格式校验；Task 4 `submit_id` 应自行决定是否先调 A。
- SMS/Email 工厂未知 provider 名抛 50100；与骨架「尚未接入」语义一致，便于配置错误尽早暴露。
