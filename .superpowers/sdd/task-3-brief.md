### Task 3: 草稿表与创建/列表/放弃

**Files:**
- Create: `backend/app/db/models/technique_craft.py`
- Modify: `backend/app/db/models/__init__.py`
- Create: `backend/app/services/technique_craft_service.py`
- Modify: `backend/app/api/research.py`（或 cave lab 路由文件，与现网关同一 PlayGate）
- Modify: `backend/app/schemas/research.py` 或新建 `schemas/technique_craft.py`
- Test: `backend/tests/test_technique_craft.py`

**Produces:**
- 表 `technique_research_drafts`
- `TechniqueCraftService.create_draft(character) -> dict`
- `list_drafts(character) -> list[dict]`
- `abandon_draft(character, draft_id) -> None`（`phase=abandoned`，不退卡）
- `GET/POST /cave/lab/technique/drafts`，`POST /cave/lab/technique/drafts/{id}/abandon`

草稿列：`id, character_id, phase, label_zh, elements_json, efficacy, element_limit, weapon_limit, base_json, affixes_json, upgrade_points, major_rank, created_at, updated_at`。`phase` 初值 `embedding`。`major_rank` 初值角色当前 `major_realm`（通常 `body_tempering`）。

- [ ] **Step 1: 写失败测试** `test_create_two_drafts_independent`

创建两次 `create_draft`，`list_drafts` 长度为 2；`abandon` 后列表为 1。

- [ ] **Step 2: 跑测试确认失败**

Expected: FAIL（服务不存在）

- [ ] **Step 3: ORM + create_all**

模型文件；`models/__init__.py` import。测试 factory 会 `create_all`，无需手工 SQL。本地 `xiuxian.db` 靠启动 `create_all` 建新表。

- [ ] **Step 4: Service + 路由**

`create_draft` 不扣卡。响应含 `id, phase, elements, efficacy, can_finalize=false`。PlayGate 写操作走现有 `_prepare_research_write`。

`ResearchService.create_session(kind="technique")` 改为 `raise AppError(40201, "请改用功法自研草稿接口")` 或内部转调 `create_draft`（推荐直接拒绝旧接口，避免双轨）。阵法/符箓 `kind` 不变。

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_technique_craft.py::test_create_two_drafts_independent tests/test_research_formation_blueprint.py tests/test_research_talisman_whitelist.py -q`

Expected: PASS（阵法/符测仍绿）

---
