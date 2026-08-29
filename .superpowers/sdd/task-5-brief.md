### Task 5: 发动条件 + 词条三选一/重随

**Files:**
- Modify: `backend/app/domain/technique_craft.py`（`filter_affixes`, `roll_three`）
- Modify: `technique_craft_service.py`
- API：`POST .../conditions` `{element_limit?, weapon_limit?}`；`POST .../affix/roll` `{slot}`；`POST .../affix/choose` `{slot, affix_id}`；`POST .../affix/reroll` `{slot}`
- Test: `backend/tests/test_technique_craft.py`

规则：
- `conditions`：须已嵌属性+效能。`element_limit` 空或 ∈ `elements`。`weapon_limit` 空或 ∈ `WEAPON_LIMITS`。
- 词条栏数 = `ranks[draft.major_rank].affix_slots`（锻体默认 1）。未选条件也可 roll（过滤仍看效能/属性；发动条件空则不过滤武器）。
- `filter_affixes`：`efficacy in efficacy_allow`；`role=defense` 且效能 ∈ `ATTACK_EFFICACIES` 则丢弃（占位词条不要给攻击类配 defense）。法术/武技用 `SPELL_EFFICACIES` / `MARTIAL_EFFICACIES`。
- 每栏 `options: [id,id,id]`，选中后 `chosen_id`。重随扣 `affix_reroll_cost[min(n, len-1)]` 的修为或炼体（法术/修为修炼扣 `cultivation_points`，武技/炼体扣 `body_tempering_points`）。重随后 `chosen_level=0`、`upgrade_count=0`。
- 池子不足 3 条时允许重复抽（测试用 1 条池也能出 3 个选项）。

- [ ] **Step 1: 纯函数测试** `test_filter_hides_martial_affix_from_spell`

- [ ] **Step 2: 服务测试** 选词条、重随清等级、扣资源

- [ ] **Step 3: 实现并跑通**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_technique_craft.py -k "affix or conditions or filter" -q`

Expected: PASS

---
