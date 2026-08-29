# 功法自研 P3（藏经阁秘籍上缴与条目学习）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创作者上缴自研秘籍经管理审核后成为门派永久条目；本门弟子扣贡献学会定格副本（`source=sect`）；拒绝退同快照书；同 origin 再缴可替换。

**Architecture:** 扩展 `SectScriptureEntry` 存快照；`scripture_donate(item_uid)` 扣书写 `SectDonationReview`；`review_donation` 通过则入库/替换并发贡献、拒绝则 `add_item` 退书；`scripture_exchange` 对有快照条目扣学费并调用 `TechniqueCraftService.learn_from_manual_meta(..., source=sect)`。YAML 目录兑换仍占位。前端扩 `SectScripturePanel`。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy async、pytest、Vue 3；现有 `SectFacilityService`、`InventoryService`、`TechniqueCraftService`、`PlayGate`。

**Spec:** `docs/superpowers/specs/2026-08-29-technique-scripture-p3-design.md`；父规格 §8.3 / §10 P3。

**Branch:** 继续 `feat/technique-research-p1`，不要合入 `main`。

## Global Constraints

- 注释与 docstring 英文标识符；复杂规则可用中文注释。
- 上缴奖励 / 学习学费禁止写死在 `if` 分支，必须读 `get_game_config().sects.scripture`（`donate_reward_contrib` / `learn_cost_contrib` / `specialty_match_bonus_contrib`）。
- 阵法/符箓自研、P2 秘籍学、YAML 目录占位兑换不得无故失败。
- 失败无保底。习得副本不能培养、不能再制成秘籍。
- 测试用 `tests.async_db.open_test_session_factory` + DEBUG + `sect_system_enabled=True`。
- 不要自动 git commit，除非用户明确要求或选用 Subagent-Driven；脏工作区禁止 `git add -A`。
- 每次任务同步 `README.md` / `CHANGELOG.md` 一句（可 defer 到末任务）。
- 自研条目 `technique_id == origin_technique_id`（形如 `custom:technique:…`）；`SectScriptureEntry.technique_id` 列宽改为 `String(128)`。
- 学会副本仍用新 id：`custom:technique:{learner_id}:{8hex}`，`CharacterTechnique.source=sect`。

---

## File map

| 路径 | 职责 |
| --- | --- |
| `backend/app/db/models/sect.py` | `SectScriptureEntry` 新列；`technique_id` → 128 |
| `backend/app/db/bootstrap.py` | SQLite 补列 |
| `backend/app/config_data/sects.yaml` | `donate_reward_contrib` / `learn_cost_contrib` |
| `backend/app/constants/technique_craft.py` 或 `sect.py` | `ERR_SCRIPTURE_DONATE=40227`（可选学习复用 40226） |
| `backend/app/schemas/sect.py` | donate body → `item_uid` |
| `backend/app/services/technique_craft_service.py` | `learn_from_manual_meta` 增加 `source` 参数 |
| `backend/app/services/sect_facility_service.py` | donate / review / exchange / list / list_donations |
| `backend/app/api/sect.py` | `GET /donations`；donate schema |
| `frontend/src/api/sect.ts` | donate / donations / review 包装 |
| `frontend/src/components/sect/SectScripturePanel.vue` | 上缴 / 学习 / 审核 UI |
| `backend/tests/test_sect_scripture_technique.py` | P3 单测 |

**本计划不做：** 目录真授予系统功法、每日次数、非创作者代缴、P4 师徒。

---

### Task 1: 模型、YAML、SQLite 补列、错误码

**Files:**
- Modify: `backend/app/db/models/sect.py`（`SectScriptureEntry`）
- Modify: `backend/app/db/bootstrap.py`（`_patch_sqlite_sect_columns`）
- Modify: `backend/app/config_data/sects.yaml`（`scripture` 段）
- Modify: `backend/app/constants/technique_craft.py`（或新建 `constants/sect_scripture.py`：优先在 `technique_craft.py` 旁的 `app/constants/sect.py` 若已有则追加；否则加在 `technique_craft.py`）
- Test: `backend/tests/test_sect_scripture_technique.py`（新建）

**Produces:**
- 新列：`origin_technique_id`（String 128 nullable）、`author_character_id`（Integer nullable）、`major_rank`（String 32 nullable）、`payload_json` / `stats_json` / `affix_ids_json`（Text nullable）、`cost_contribution`（Integer not null default 0）
- `technique_id: String(128)`
- YAML：`donate_reward_contrib: 40`、`learn_cost_contrib: 60`（`specialty_match_bonus_contrib` 已有则勿改名）
- `ERR_SCRIPTURE_DONATE: Final[int] = 40227`

- [ ] **Step 1: 写失败测试**

```python
def test_scripture_yaml_costs_and_entry_columns() -> None:
    from app.db.models.sect import SectScriptureEntry
    from app.services.realm_config import clear_game_config_cache, get_game_config

    clear_game_config_cache()
    sc = get_game_config().sects.scripture
    assert int(sc.get("donate_reward_contrib") or 0) == 40
    assert int(sc.get("learn_cost_contrib") or 0) == 60
    assert hasattr(SectScriptureEntry, "origin_technique_id")
    assert hasattr(SectScriptureEntry, "payload_json")
    assert hasattr(SectScriptureEntry, "cost_contribution")
```

- [ ] **Step 2: 跑测确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_sect_scripture_technique.py::test_scripture_yaml_costs_and_entry_columns -q`  
Expected: FAIL

- [ ] **Step 3: 落地模型 / YAML / bootstrap**

`sects.yaml` `scripture:` 下增加：

```yaml
  donate_reward_contrib: 40
  learn_cost_contrib: 60
```

`SectScriptureEntry` 追加列；`_patch_sqlite_sect_columns` 对 `sect_scripture_entries` 调 `_patch_sqlite_table_columns`。

- [ ] **Step 4: 跑测确认通过**

Expected: PASS

---

### Task 2: `learn_from_manual_meta` 支持 `source=sect`

**Files:**
- Modify: `backend/app/services/technique_craft_service.py`
- Modify: `backend/tests/test_technique_craft.py`（一条断言 chance 默认不变）
- Test: `backend/tests/test_sect_scripture_technique.py`

**Consumes:** P2 `learn_from_manual_meta`、`TECHNIQUE_SOURCE_SECT`

**Produces:**
- `async def learn_from_manual_meta(self, character, meta, *, source: str = TECHNIQUE_SOURCE_CHANCE) -> dict`
- `source` 写入 `CharacterTechnique.source`（经 `normalize_technique_source`）；自学/已学/境界闸不变
- 培养/再印仍因 `_require_cultivable` 失败

- [ ] **Step 1: 测试**

```python
def test_learn_from_manual_meta_source_sect(tmp_path, monkeypatch):
    # 复用 P2：定稿→印书→把 snapshot 交给第二角色 learn_from_manual_meta(..., source=TECHNIQUE_SOURCE_SECT)
    # 断言 CharacterTechnique.source == "sect"；list_my_techniques 该项 cultivable is False
```

同时确认现有 P2 `use_item` 学书仍为 `chance`（跑 `-k use_manual_learns`）。

- [ ] **Step 2: 实现最小改动（默认参数保持 chance）**
- [ ] **Step 3: 跑测通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_technique_craft.py -k "use_manual or learn_from_manual" tests/test_sect_scripture_technique.py -q`

---

### Task 3: 上缴秘籍（扣书 + 待审）

**Files:**
- Modify: `backend/app/schemas/sect.py`（`SectScriptureDonateRequest` → `item_uid: str`）
- Modify: `backend/app/services/sect_facility_service.py`（重写 `scripture_donate`）
- Modify: `backend/app/api/sect.py`（传 `item_uid`）
- Test: `backend/tests/test_sect_scripture_technique.py`

**Consumes:** Task 1 列；P2 秘籍 meta；`InventoryService.remove_one_by_uid` / `_parse_row_meta`

**Produces:**
- `async def scripture_donate(self, user, *, item_uid: str) -> dict`
- 校验：本门、`scripture_pavilion` 闸、行属自己、`item_id==tech_manual`、meta 合法、`author_character_id==character.id`
- 已有同 origin **pending** 审核 → `AppError(40227, "该功法已在审核中")`
- 已有条目不挡提交（替换留给审核通过）
- 扣 1 本 → `SectDonationReview(kind="scripture", status="pending", payload_json=完整快照字典)`
- **不发贡献**

测试助手建议：自建宗（founder）+ 印书（可 monkeypatch embed）；或拜入 NPC 后把角色抬成可印书境界。优先 **自建宗** 方便审核职。

```python
def test_scripture_donate_consumes_book_and_opens_review(tmp_path, monkeypatch):
    # founder 印书 → scripture_donate(item_uid) → 背包无书；pending review 1 条；contrib 未变
```

```python
def test_scripture_donate_rejects_non_author(tmp_path, monkeypatch):
    # 把书 add_item 给非作者本门弟子 → 40227 或 403 文案「仅创作者可上缴」；书仍在
```

- [ ] **Step 1–4: TDD + 实现 + 通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_sect_scripture_technique.py -k donate -q`

---

### Task 4: 审核通过 / 拒绝（入库、发贡献、退书、替换）

**Files:**
- Modify: `backend/app/services/sect_facility_service.py`（`review_donation` 的 scripture 分支）
- Modify: `backend/app/api/sect.py`（`GET /donations`）
- Test: `backend/tests/test_sect_scripture_technique.py`

**Produces:**
- `async def list_donations(self, user) -> dict`：仅 `founder`/`leader`/`supreme_elder`；返回 `items: [{id, kind, label_zh, origin_technique_id, character_id, created_at}]`
- **拒绝**：`add_item(..., item_id=tech_manual, meta=快照)` 给 `review.character_id`；status=rejected
- **通过**：
  - `technique_id = origin_technique_id`
  - 若已有同行：更新 `label_zh` / `major_rank` / payload/stats/affix / `author_character_id` / `cost_contribution=learn_cost_contrib` / `source=self_research`
  - 若无：插入新 `SectScriptureEntry`
  - 给上缴者 `donate_reward_contrib` +（`specialty_tag==sect.specialty` 时）`specialty_match_bonus_contrib`
- 非管理职 list/review → 403

```python
def test_scripture_review_reject_returns_manual(tmp_path, monkeypatch): ...
def test_scripture_review_approve_grants_contrib_and_entry(tmp_path, monkeypatch): ...
def test_scripture_review_approve_replaces_same_origin(tmp_path, monkeypatch): ...
```

- [ ] **Step 1–4: TDD + 实现**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_sect_scripture_technique.py -k review -q`

---

### Task 5: 列表 + 扣贡献学会（真授予）

**Files:**
- Modify: `backend/app/services/sect_facility_service.py`（`scripture_list`、`scripture_exchange`）
- Test: `backend/tests/test_sect_scripture_technique.py`

**Produces:**
- `scripture_list` 的 `entries` 含：`technique_id`、`origin_technique_id`、`author_character_id`、`label_zh`、`major_rank`、`cost_contribution`、`source`、`owned`（是否已学同 origin）、`has_snapshot`（payload 非空）
- `scripture_exchange`：
  - 若 entry 有 `payload_json`：扣 `entry.cost_contribution`（不足 → 现有贡献不足错误）→ 组 meta → `TechniqueCraftService(...).learn_from_manual_meta(char, meta, source=TECHNIQUE_SOURCE_SECT)`；学失败须**回滚贡献**（先学后扣，或同一事务内先学再扣——推荐 **先学后扣**：学抛错则不扣）
  - 若无快照（目录）：保持现有占位行为
- 已学同 origin / 境界不足：不扣贡献（学服务先抛）

```python
def test_scripture_exchange_learns_sect_copy_and_charges(tmp_path, monkeypatch):
    # 通过审核后给弟子加贡献 → exchange → source=sect、cultivable False、contrib 减少 learn_cost
def test_scripture_exchange_below_rank_no_charge(tmp_path, monkeypatch): ...
def test_catalog_exchange_still_placeholder(tmp_path):
    # 兑换 YAML catalog id 仍返回「占位授予」类文案且不建 PrivateTechnique
```

- [ ] **Step 1–4: TDD + 实现**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_sect_scripture_technique.py -q`

---

### Task 6: 前端藏经阁面板

**Files:**
- Modify: `frontend/src/api/sect.ts`
- Modify: `frontend/src/components/sect/SectScripturePanel.vue`
- Test: `cd frontend && npx vue-tsc -b --pretty false`

**Produces:**
- `donateScriptureApi({ item_uid })`、`fetchDonationsApi()`、`reviewDonationApi(id, { approve })`
- 面板分区：目录（占位兑换）、已收录自研（学习）、我的可上缴秘籍（`item_id===tech_manual` 且 `meta.author_character_id===自己`）、管理待审（有权限才显示）
- 成功后 `reload` + toast；学习成功可 `inventory`/`character` 刷新若页面已有 store

`sect.ts` / 面板若有脏 WIP：只提交本任务相关 hunk（aside 流程同 P2）。

- [ ] **Step 1: API + UI**
- [ ] **Step 2: vue-tsc 退出码 0**

---

### Task 7: 回归与文档

**Files:**
- Modify: `docs/superpowers/specs/2026-08-29-technique-scripture-p3-design.md` 状态 → 已实现
- Modify: `docs/superpowers/specs/2026-08-27-technique-research-design.md` 状态行含 P3
- Modify: `README.md`、`CHANGELOG.md` 一句

- [ ] **Step 1: 后端回归**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_sect_scripture_technique.py tests/test_technique_craft.py tests/test_sect_treasury_pages.py tests/test_research_formation_blueprint.py tests/test_research_talisman_whitelist.py -q`  
Expected: PASS

- [ ] **Step 2: `npx vue-tsc -b --pretty false`**
- [ ] **Step 3: 文档**

---

## Spec coverage（自检）

| Spec | 任务 |
| --- | --- |
| 必须经秘籍 / 仅创作者 | T3 |
| 提交扣书、拒绝退书、通过不退 | T3 T4 |
| 通过发 YAML 贡献 + 专精加成 | T4 |
| 学条目扣 YAML 学费、真学会 source=sect | T2 T5 |
| 同 origin 替换；pending 挡新缴 | T3 T4 |
| 目录占位并存 | T5 |
| 待审 GET + 前端 | T4 T6 |
| 模型/补列/YAML | T1 |
| 不可培养再印 | T2（复用闸）+ T5 断言 |

## 后续（不要在本计划实现）

- P4 师徒
- 目录 YAML 真授予系统功法
- 每日学习次数
