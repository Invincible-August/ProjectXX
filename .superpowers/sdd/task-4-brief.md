### Task 4: 镶嵌正式卡（可失败）

**Files:**
- Modify: `backend/app/services/technique_craft_service.py`
- Modify: `backend/app/domain/technique_craft.py`（`roll_embed_success`）
- Modify: API `POST /cave/lab/technique/drafts/{id}/embed`
- Test: `backend/tests/test_technique_craft.py`

**Body:** `{ "item_uid": "..." }`

规则：
- 正式属性卡：草稿 `elements` 必须仍为空；成功则写入 `elements_json` 并锁定。
- 正式效能卡：`efficacy` 必须仍为空。
- 无论成败都 `remove_one_by_uid` 该正式卡。
- 失败：`embed_fail_rate`，草稿其它字段不变。测试用 monkeypatch `roll_embed_success` 返回 `False`/`True`。

错误：非主人 40207；错误卡类型 40220；该槽已锁定再镶 40221。

- [ ] **Step 1: 测试** `test_embed_fail_consumes_card_keeps_draft`、`test_embed_success_locks_elements`、`test_embed_second_element_card_rejected`

- [ ] **Step 2: 跑测试确认失败 → 实现 → 跑通**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_technique_craft.py -k embed -q`

Expected: PASS

---
