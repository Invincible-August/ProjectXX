### Task 6: 定稿、已学列表、装备角色限制

**Files:**
- Modify: `backend/app/db/models/research.py`（`PrivateTechnique.payload_json` `Text default '{}'`，`major_rank` `String(32)`，`author_character_id` `Integer`）
- Modify: `backend/app/db/bootstrap.py` 给 `private_techniques` 补这三列
- Modify: `technique_craft_service.py` `finalize_draft`
- Modify: `technique_service.py` `equip_technique`
- Modify: `ResearchService.list_mine` / technique list DTO 带 `efficacy`、`author_character_id`、`cultivable: true`
- Test: `backend/tests/test_technique_craft.py`；改写 `tests/test_research_technique_finalize.py` 为调用新 finalize 或删除过时用例并在本文件覆盖「定稿后可装备」

**finalize 门槛：** elements 非空、efficacy 非空、conditions 已调用过（允许两框都空，用 `conditions_confirmed` 布尔）、至少一栏 `chosen_id` 非空。

定稿：`phase=finalized`；插入 `PrivateTechnique`（`technique_id=custom:technique:{cid}:{slug}` 沿用现前缀）；插入 `CharacterTechnique` `source=research`；草稿不再出现在 list_drafts。

装备：读 payload.efficacy，若 slot=main 且 efficacy ∉ `IDLE_EFFICACIES` → `AppError(40224, "该功法不能装备为主功法")`。技法格六种都行。同一门不能同时占 main+art（现逻辑保留）。

- [ ] **Step 1: 测试** `test_finalize_requires_affix`、`test_finalize_enters_learn_list`、`test_equip_attack_spell_as_main_rejected`、`test_equip_idle_spirit_as_main_ok`

- [ ] **Step 2: 实现 bootstrap 补列**（与现有 `_patch_table` 模式一致，表名 `private_techniques`）

- [ ] **Step 3: 跑测试**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_technique_craft.py -k "finalize or equip" tests/test_research_technique_finalize.py -q`

Expected: PASS

---
