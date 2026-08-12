### Task 5: verification API 璺敱

**Files:**
- Create: `backend/app/api/verification.py`
- Modify: `backend/app/api/router.py`

**Produces:** 瑙勬牸涓殑 6 涓鐐?
- [ ] **Step 1: 鎸傝浇 `APIRouter(prefix="/verification")`**

- [ ] **Step 2: 鑱旇皟**

```text
GET /api/v1/verification/modes
POST /api/v1/verification/sms/send {"phone":"13800138000"}
POST /api/v1/verification/sms/confirm {"phone":"13800138000","code":"000000"}
```

Expected: modes 鍚?`id_verify_mode`锛沜onfirm 寰?ticket銆?
---


