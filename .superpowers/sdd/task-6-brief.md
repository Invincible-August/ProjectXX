### Task 6: 娉ㄥ唽鏀归€?+ 瓒呯骇瀵嗙爜鐧诲綍

**Files:**
- Modify: `backend/app/schemas/auth.py`
- Modify: `backend/app/services/auth_service.py`
- Modify: `backend/app/api/auth.py`锛堣嫢闇€锛?
**Produces:**
- `RegisterRequest` 澧炲姞 optional/required 瀛楁锛歚email`, `phone`, `real_name`, `id_card`, `sms_ticket`, `email_ticket`, `id_ticket`
- `register_user`锛氶潪 DEBUG 缂烘潗鏂?鈫?`40017`锛涜皟 `assert_register_tickets`锛涙煡閲?email/phone 鈫?`40013`锛涘啓鎵╁睍瀛楁
- `login_user`锛氱敤鎴峰瘑鐮佸け璐ュ悗瓒呯骇瀵嗙爜鍒嗘敮 + WARNING 鏃ュ織锛涚鐢ㄥ彿浠?`40300`

- [ ] **Step 1: Schema + service**

瓒呯骇瀵嗙爜姣斿锛?
```python
import secrets
from app.core.config import get_settings

settings = get_settings()
if settings.super_password and secrets.compare_digest(payload.password, settings.super_password):
    logger.warning("super_password_login user_id=%s username=%s", user.id, user.username)
    return _build_token_payload(user, remember_me=payload.remember_me)
```

- [ ] **Step 2: 闆嗘垚娴嬭瘯**

1. DEBUG 娉ㄥ唽鏃?ticket 鎴愬姛  
2. 涓存椂 `DEBUG=false`锛堟祴璇曞唴 monkeypatch锛夋棤 ticket 鈫?`40017`  
3. 瀹屾垚涓?ticket + format 娉ㄥ唽鎴愬姛  
4. 瓒呯骇瀵嗙爜鐧诲綍鎴愬姛锛涢敊璇瘑鐮佷粛 `40002`

Run: `pytest backend/tests/test_verification_auth.py -v`  
Expected: PASS

---


