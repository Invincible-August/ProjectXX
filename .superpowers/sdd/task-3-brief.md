### Task 3: ID / SMS / Email Providers

**Files:**
- Create: `backend/app/services/verification/__init__.py`
- Create: `backend/app/services/verification/providers/__init__.py`
- Create: `backend/app/services/verification/providers/id_format.py`锛堝畬鏁存牎楠屼綅锛?- Create: `backend/app/services/verification/providers/id_two_factor.py`锛坰tub锛?- Create: `backend/app/services/verification/providers/id_real_person.py`锛坰tub锛?- Create: `backend/app/services/verification/providers/sms_debug.py` 绛?- Create: `backend/app/services/verification/id_card_util.py`锛坢ask + hash锛?
**Produces:**
- `validate_id_card_format(id_card: str) -> None` 澶辫触鎶?`AppError(40014)`
- `hash_id_card(id_card: str) -> str` / `mask_id_card(id_card: str) -> str`
- `async def verify_identity(...)` 宸ュ巶锛氭寜 mode 璋冪敤 A/B/C
- SMS/Email锛歚async def send_code(target, code) -> None`锛涢潪 debug 鏈疄鐜版椂 `AppError(50100)`

- [ ] **Step 1: 瀹炵幇鍥芥爣 18 浣嶆牎楠屼綅**锛堝惈鍦板潃鐮佺矖妫€鍙€夛紝鑷冲皯鏍￠獙浣嶏級

- [ ] **Step 2: stub B/C**

```python
async def verify_two_factor(*, real_name: str, id_card: str) -> None:
    settings = get_settings()
    if settings.debug:
        return
    if settings.id_two_factor_provider == "stub":
        raise AppError(50100, "浜岃绱?Provider 鏈厤缃?, http_status=501)
    raise AppError(50100, "浜岃绱?Provider 灏氭湭鎺ュ叆", http_status=501)
```

C 鍚岀悊锛屾帴鏀跺彲閫?`face_token`銆?
- [ ] **Step 3: debug SMS/Email** 鈥?浠?`logger.info` 鎻愮ず宸层€屽彂閫併€嶏紙DEBUG 鍙笉鎵撳嵃鐮佸埌鏂囦欢浠ュ锛屾垨浠?debug 绾у埆鎵撳嵃鍥哄畾鐮佽鏄庯級

- [ ] **Step 4: aliyun/tencent/resend 鏂囦欢** 鈥?鍑芥暟绛惧悕榻愬叏锛宍raise AppError(50100, "...")`

- [ ] **Step 5: 鍗曞厓娴嬫牸寮忔牎楠?*

```python
def test_id_card_checksum_valid():
    # 浣跨敤宸茬煡鍚堟硶娴嬭瘯鍙凤紙鍏紑娴嬭瘯鐢ㄥ彿锛屽嬁鐢ㄧ湡浜鸿瘉浠讹級
    validate_id_card_format("110101199003074477")  # 鑻ョ畻娉曚笅闈炴硶鍒欐崲鏍囧噯鏍蜂緥
```

Run: `pytest backend/tests/test_id_format.py -v`

---


