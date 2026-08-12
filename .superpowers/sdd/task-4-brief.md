### Task 4: verification service锛堝彂鐮?/ 纭 / ticket锛?
**Files:**
- Create: `backend/app/services/verification/service.py`
- Create: `backend/app/schemas/verification.py`

**Produces:**
- `send_sms(session, phone) -> None`
- `confirm_sms(session, phone, code) -> str`  # ticket
- `send_email` / `confirm_email` 鍚屼笂
- `submit_id(session, real_name, id_card, face_token=None) -> str`
- `assert_register_tickets(session, *, debug, email, phone, id_card, sms_ticket, email_ticket, id_ticket) -> None`
- `get_modes() -> dict`

閫昏緫瑕佺偣锛?- 鍙戦€佸墠鏌ュ悓 `channel+target` 鏈€杩戜竴鏉★紝鏈秴 `verify_send_interval_seconds` 鈫?`40011`
- code 瀛?`hash_password` 鎴?sha256锛涚‘璁ょ敤 `verify` 鎴?compare
- DEBUG锛氭帴鍙?`settings.debug_verify_code`
- ticket锛歚secrets.token_urlsafe(32)`锛孴TL=`verify_ticket_ttl_seconds`锛屽啓鍏ュ悓涓€ challenge 琛屾垨鏂拌
- `submit_id`锛氳嫢 `debug` 鈫?鐩存帴鍙?ticket锛涘惁鍒欐寜 `id_verify_mode` 璋冨搴?provider锛屾垚鍔熷悗鍙?ticket锛坧ayload 鍚?mode锛?
- [ ] **Step 1: 瀹炵幇 service + schemas**

- [ ] **Step 2: httpx 娴?send/confirm**锛圖EBUG锛?
Expected: confirm 杩斿洖 `code=0` 涓?`data.ticket` 闈炵┖锛涢敊璇爜 `40010`/`40011` 鍙祴銆?
---


