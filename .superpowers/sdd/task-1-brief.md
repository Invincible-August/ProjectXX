### Task 1: Settings 涓?.env.example

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`

**Produces:**
- `Settings.super_password: str`锛堥粯璁?`""`锛?- `Settings.id_verify_mode: str`锛堥粯璁?`"format"`锛?- `Settings.id_card_hash_salt: str`
- `Settings.sms_provider` / `email_provider` / `id_two_factor_provider` / `id_real_person_provider`
- `Settings.verify_code_ttl_seconds` / `verify_ticket_ttl_seconds` / `verify_send_interval_seconds` / `debug_verify_code`

- [ ] **Step 1: 鎵╁睍 Settings**

鍦?`Settings` 涓鍔狅紙alias 涓庤鏍间竴鑷达級锛?
```python
super_password: str = Field(default="", alias="SUPER_PASSWORD")
id_verify_mode: str = Field(default="format", alias="ID_VERIFY_MODE")
id_card_hash_salt: str = Field(default="dev-id-salt-change-me", alias="ID_CARD_HASH_SALT")
sms_provider: str = Field(default="debug", alias="SMS_PROVIDER")
email_provider: str = Field(default="debug", alias="EMAIL_PROVIDER")
id_two_factor_provider: str = Field(default="stub", alias="ID_TWO_FACTOR_PROVIDER")
id_real_person_provider: str = Field(default="stub", alias="ID_REAL_PERSON_PROVIDER")
verify_code_ttl_seconds: int = Field(default=300, alias="VERIFY_CODE_TTL_SECONDS")
verify_ticket_ttl_seconds: int = Field(default=600, alias="VERIFY_TICKET_TTL_SECONDS")
verify_send_interval_seconds: int = Field(default=60, alias="VERIFY_SEND_INTERVAL_SECONDS")
debug_verify_code: str = Field(default="000000", alias="DEBUG_VERIFY_CODE")
```

- [ ] **Step 2: 鏇存柊 `.env.example`**

杩藉姞涓婅堪鍙橀噺娉ㄩ噴璇存槑锛沗SUPER_PASSWORD=` 鐣欑┖绀轰緥銆?
- [ ] **Step 3: 鏈湴 `.env` 鍙€夋墜鍔ㄨ拷鍔?*锛堜笉鎻愪氦鐪熷疄瓒呯骇瀵嗙爜锛?
- [ ] **Step 4: 楠岃瘉 Settings 鍙姞杞?*

Run: `cd backend; .\.venv\Scripts\python.exe -c "from app.core.config import get_settings; s=get_settings(); print(s.id_verify_mode, s.debug, bool(s.super_password))"`  
Expected: 鎵撳嵃 `format True False`锛堟垨浣犵殑鏈湴鍊硷級

---


