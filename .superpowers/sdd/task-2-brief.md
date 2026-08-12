### Task 2: User / VerificationChallenge 妯″瀷

**Files:**
- Modify: `backend/app/db/models/user.py`
- Create: `backend/app/db/models/verification.py`
- Modify: `backend/app/db/models/__init__.py`
- Modify: `backend/app/main.py`锛圫QLite 鍚姩琛ラ綈缂哄け鍒楋紝閬垮厤鍒犲簱锛?
**Produces:**
- `User` 鏂板垪锛歚email`, `phone`, `real_name`, `id_card_hash`, `id_card_masked`, `id_verified_level`, `email_verified`, `phone_verified`
- `VerificationChallenge` 琛?
- [ ] **Step 1: 鎵╁睍 User**

```python
email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
phone: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)
real_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
id_card_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
id_card_masked: Mapped[str | None] = mapped_column(String(32), nullable=True)
id_verified_level: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
phone_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
```

- [ ] **Step 2: 鏂板缓 VerificationChallenge**

瀛楁锛歚id`, `channel`, `target`, `code_hash`锛坣ullable锛? `ticket`锛坲nique nullable锛? `payload_json`锛圱ext nullable锛? `expires_at`, `consumed_at`锛坣ullable锛? `created_at`銆?
- [ ] **Step 3: 瀵煎嚭妯″瀷锛沵ain lifespan 淇濇寔 `create_all`**

- [ ] **Step 4: SQLite 鍒楄ˉ涓?*

鍦?`lifespan` 鐨?`create_all` 涔嬪悗锛屽 SQLite 鎵ц `PRAGMA table_info(users)`锛岀己澶卞垪鍒?`ALTER TABLE users ADD COLUMN ...`锛堢被鍨嬩笌榛樿鍊煎尮閰嶏級銆傛柊琛?`verification_challenges` 鐢?`create_all` 鍒涘缓鍗冲彲銆?
- [ ] **Step 5: 鍐掔儫**

Run: 鍚姩 uvicorn 鎴?`create_all` 鑴氭湰锛岀‘璁ゆ棤鎶ラ敊銆?
---


