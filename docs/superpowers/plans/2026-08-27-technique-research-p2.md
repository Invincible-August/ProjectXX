# 功法自研 P2（秘籍印制与学习）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 原创者把当前功法快照印成一本秘籍；别人使用后学会定格副本（只读、不可培养、不可再印），成功后该书消失。

**Architecture:** 印制走 `TechniqueCraftService.print_manual`，写入背包 `manual` 行（`item_id=tech_manual`，`meta` 带快照，不并堆）。学习走 `InventoryService.use_item` 的 `tech_manual_learn`：校验境界后给学习者新建 `PrivateTechnique` + `CharacterTechnique(source=chance)`。拍卖/给予沿用现有交易，本计划不接线。P3 藏经阁、P4 师徒另开计划。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy async、pytest、Vue 3、Pinia；现有 `AppError`、`InventoryService.add_item(meta=…)`、`PlayGate`。

**Spec:** `docs/superpowers/specs/2026-08-27-technique-research-design.md` §8.1–8.2、§10 P2、§12（副本不可再印）。

**Branch:** 继续 `feat/technique-research-p1`，不要合入 `main`。

## Global Constraints

- 注释与 docstring 英文标识符；复杂规则可用中文注释。
- 印制消耗禁止写死在 `if` 分支，必须读 `get_game_config().research.technique_craft`。
- 阵法/符箓自研 API 与单测不得无故失败。
- 失败无保底。习得副本不能培养、不能再制成秘籍。
- 测试用 `tests.async_db.open_test_session_factory` + DEBUG 注册，与 `test_technique_craft.py` 相同。
- 不要自动 git commit，除非用户明确要求或选用 Subagent-Driven。
- 每次任务同步 `README.md` 与 `CHANGELOG.md` 一句进度（不必每步都改）。
- `CharacterTechnique.technique_id` 仍是 `String(64)`；新副本 id 继续用 `custom:technique:{learner_id}:{8hex}`。

---

## File map

| 路径 | 职责 |
| --- | --- |
| `backend/app/constants/technique_craft.py` | `CARD_MANUAL_ID`、`ERR_CRAFT_MANUAL` / `ERR_CRAFT_LEARN` |
| `backend/app/constants/inventory.py` | `UseEffectKind.TECH_MANUAL_LEARN` |
| `backend/app/config_data/research.yaml` | `print_manual_cost_cultivation` / `print_manual_cost_body` |
| `backend/app/config_data/inventory.yaml` | `tech_manual` 目录行 |
| `backend/app/services/realm_config.py` | `TechniqueCraftConfig` 解析上述费用 |
| `backend/app/domain/technique_craft.py` | `learner_meets_manual_rank` |
| `backend/app/services/technique_craft_service.py` | `print_manual`、`learn_from_manual_meta` |
| `backend/app/services/inventory_service.py` | `use_item` 拦截 `tech_manual_learn`（先学再扣书） |
| `backend/app/api/research.py` | `POST .../techniques/{technique_id}/print-manual` |
| `frontend/src/api/cave.ts` | `printTechniqueManual` |
| `frontend/src/stores/techniqueCraft.ts` | 印制动作 |
| `frontend/src/components/research/TechniqueResearchPanel.vue` | 「制成秘籍」钮 |
| `backend/tests/test_technique_craft.py` | P2 单测 |

**本计划不做：** 藏经阁条目、师徒传授、世界掉落表、当面互传。

---

### Task 1: 配置与目录（费用、秘籍物品、错误码）

**Files:**
- Modify: `backend/app/constants/technique_craft.py`
- Modify: `backend/app/constants/inventory.py`
- Modify: `backend/app/config_data/research.yaml`
- Modify: `backend/app/config_data/inventory.yaml`
- Modify: `backend/app/services/realm_config.py`（`TechniqueCraftConfig` + `_parse_technique_craft`）
- Test: `backend/tests/test_technique_craft.py`

**Produces:**
- `CARD_MANUAL_ID = "tech_manual"`
- `ERR_CRAFT_MANUAL = 40225`（不能印）
- `ERR_CRAFT_LEARN = 40226`（不能学）
- `UseEffectKind.TECH_MANUAL_LEARN = "tech_manual_learn"`
- `get_game_config().research.technique_craft.print_manual_cost_cultivation == 500`
- `print_manual_cost_body == 500`
- `inventory.items["tech_manual"]`：`item_type: manual`，`manual_kind: technique`，`tradable: true`，`bound: false`，`max_stack: 1`，`use_effect.kind: tech_manual_learn`

- [ ] **Step 1: 写失败测试**

```python
def test_technique_manual_catalog_and_print_cost_load() -> None:
    from app.constants.inventory import UseEffectKind
    from app.constants.technique_craft import CARD_MANUAL_ID
    from app.services.realm_config import clear_game_config_cache, get_game_config

    clear_game_config_cache()
    cfg = get_game_config()
    craft = cfg.research.technique_craft
    assert craft.print_manual_cost_cultivation == 500
    assert craft.print_manual_cost_body == 500
    item = cfg.inventory.items[CARD_MANUAL_ID]
    assert item.item_type == "manual"
    assert item.manual_kind == "technique"
    assert item.tradable is True
    assert item.max_stack == 1
    assert (item.use_effect or {}).get("kind") == UseEffectKind.TECH_MANUAL_LEARN
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_technique_craft.py::test_technique_manual_catalog_and_print_cost_load -q`

Expected: FAIL（缺属性 / 缺物品）

- [ ] **Step 3: 落地 YAML 与解析**

`research.yaml` `technique_craft` 增加：

```yaml
  print_manual_cost_cultivation: 500
  print_manual_cost_body: 500
```

`inventory.yaml` 增加：

```yaml
  tech_manual:
    name: 功法秘籍
    item_type: manual
    max_stack: 1
    bag_allowed: [normal]
    manual_kind: technique
    tradable: true
    bound: false
    use_effect:
      kind: tech_manual_learn
```

`TechniqueCraftConfig` 增加两个 `int` 字段；`_parse_technique_craft` 缺省 500。`UseEffectKind` 追加 `TECH_MANUAL_LEARN`，并在 `USE_EFFECT_KIND_LABELS_ZH` 写「功法秘籍」。

- [ ] **Step 4: 跑测试确认通过**

Run: 同 Step 2  
Expected: PASS

---

### Task 2: 印制秘籍（仅原创者、当下快照、不并堆）

**Files:**
- Modify: `backend/app/services/technique_craft_service.py`
- Modify: `backend/app/api/research.py`
- Modify: `backend/app/schemas/technique_craft.py`（若需要空 body）
- Test: `backend/tests/test_technique_craft.py`

**Consumes:** Task 1 目录与费用；P1 `_require_cultivable`；`InventoryService.add_item(..., meta=dict)`

**Produces:**
- `async def print_manual(self, character, technique_id: str) -> dict`
- 扣费：效能 ∈ `SPELL_EFFICACIES` 扣 `cultivation_points`，否则扣 `body_tempering_points`，数额读 YAML
- `add_item(character.id, "manual", CARD_MANUAL_ID, 1, meta=snapshot)`
- snapshot 至少含：`manual_kind=technique`、`origin_technique_id`、`author_character_id`、`label_zh`、`major_rank`、`payload`（深拷贝当前 `payload_json`）、`stats`、`affix_ids`
- 原创者功法行不变；副本不可调用：非 `_require_cultivable` → `AppError(40225, "仅原创者可制成秘籍")`
- `POST /cave/lab/technique/techniques/{technique_id}/print-manual`，写操作走 `_prepare_research_write`

- [ ] **Step 1: 写失败测试**

复用现有 finalize helper（`test_finalize_enters_learn_list` 那条路径：空白草稿 → 嵌卡 → 条件 → 词条 → 定稿）。定稿后把角色 `cultivation_points` 设为足够大。

```python
def test_print_manual_consumes_points_and_grants_unmerged_books(tmp_path) -> None:
    # 1) 定稿一门法术效能功法
    # 2) print_manual 两次
    # 3) 背包有两行 tech_manual（meta 不同或即便相同也不并堆）
    # 4) cultivation_points 减少 2 * print_manual_cost_cultivation
    # 5) 原 PrivateTechnique.payload_json 未变
```

另写 `test_print_manual_rejected_for_non_author`：学到的副本（可先 skip 到 Task 3 后补）或伪造 `author_character_id != character.id` 的 private 行。

- [ ] **Step 2: 跑测试确认失败**

Expected: FAIL（无 `print_manual`）

- [ ] **Step 3: 实现**

费用不足沿用现有培养扣费错误（`40000`「修为不足」同类，不要新造货币错误码）。`meta` 必须是 `dict` 且非空，才能走 P1 不并堆分支。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_technique_craft.py -k print_manual -q`  
Expected: PASS

---

### Task 3: 使用秘籍学会定格副本（一本一人、境界门槛、原值）

**Files:**
- Modify: `backend/app/domain/technique_craft.py`（`learner_meets_manual_rank`）
- Modify: `backend/app/services/technique_craft_service.py`（`learn_from_manual_meta`）
- Modify: `backend/app/services/inventory_service.py`（`use_item` 在扣数量**之前**拦截 `TECH_MANUAL_LEARN`）
- Test: `backend/tests/test_technique_craft.py`

**Consumes:** Task 2 snapshot 形状；P1 `payload_attr_grants`；`_major_heights` / `major_realm_order`

**Produces:**
- `learner_meets_manual_rank(learner_major: str, snapshot_rank: str) -> bool`：学习者高度 ≥ 快照功法阶高度（`realms.yaml` `next_major` 链）。低于 → 不扣书。
- 成功：新建 `PrivateTechnique`（`character_id=学习者`，新 `technique_id`，`author_character_id=快照作者`，`payload`/`major_rank`/`label_zh` 为快照原值），`CharacterTechnique(source=chance, level=1)`；然后扣 1 本秘籍（qty→0 则删行）。
- 已有相同 `payload.origin_technique_id`（或 snapshot `origin_technique_id`）的副本 → `AppError(40226, "已习得该功法")`，不扣书。
- 自己对自己印的书：允许学吗？规格未禁。若学习者 == 作者 → `40225`「不可学习自己的秘籍」（避免已学列表双份）。
- 数值不打折。

- [ ] **Step 1: 纯函数测试**

```python
def test_learner_meets_manual_rank_qi_refining_needs_qi_refining() -> None:
    from app.domain.technique_craft import learner_meets_manual_rank

    assert learner_meets_manual_rank("qi_refining", "body_tempering") is True
    assert learner_meets_manual_rank("body_tempering", "qi_refining") is False
```

- [ ] **Step 2: 服务测试**

`test_use_manual_learns_frozen_copy_and_consumes_book`：角色 A 印书 → 转给角色 B（测试里直接 `add_item` 到 B，不经交易）→ B `use_item` → B 已学列表有 `source=chance`、`cultivable is False`、payload 与印制时一致；B 包里该书消失。

`test_use_manual_below_rank_does_not_consume`：B 境界 `body_tempering`，快照 `qi_refining` → 40226，quantity 仍为 1。

- [ ] **Step 3: 实现 `use_item` 拦截**

放在 `TECH_CARD_*` 分支旁。占用中不可用。先 `learn_from_manual_meta`，成功后再 `remove`/`delete`。解析 meta 用现有 `_parse_row_meta`。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_technique_craft.py -k "manual or meets_manual" -q`  
Expected: PASS

---

### Task 4: 副本只读（不可培养、不可再印）+ 列表来源

**Files:**
- Modify: `backend/app/services/technique_craft_service.py`（`print_manual` 已用 `_require_cultivable` 即足够；补测试）
- Modify: `backend/app/services/technique_service.py` / `research_service.list_mine`：`source=chance` 的 `cultivable` 必须为 false（已按 author!=self 计算则自然 false；加断言）
- Test: `backend/tests/test_technique_craft.py`

- [ ] **Step 1: 测试**

`test_copied_technique_cannot_upgrade_or_print`：B 学会后 `upgrade_base` → 40223；`print_manual` → 40225。`list_my_techniques` 该项 `source` 规范化为 `chance`，`cultivable is False`。

- [ ] **Step 2: 实现缺口**

若 `print_manual` 误用「只要有 PrivateTechnique 行」而未检查 source/author，改为复用 `_require_cultivable` 或同等检查。

- [ ] **Step 3: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_technique_craft.py -k "copied_technique or print_manual or use_manual" -q`  
Expected: PASS

---

### Task 5: 前端印制入口

**Files:**
- Modify: `frontend/src/api/cave.ts`
- Modify: `frontend/src/stores/techniqueCraft.ts`
- Modify: `frontend/src/components/research/TechniqueResearchPanel.vue`
- Test: `cd frontend && npx vue-tsc -b --pretty false`

**Produces:**
- `printTechniqueManual(techniqueId: string)` → `POST /cave/lab/technique/techniques/{id}/print-manual`
- 已定稿原创区、培养三钮旁增加 `el-button size="small"`「制成秘籍」；成功 toast + `inventoryStore.load()`
- 学习走现有背包使用（秘籍页 `item_type=manual`）；不必新学页面
- 阵法/符箓入口不改

- [ ] **Step 1: API + store + 按钮**
- [ ] **Step 2: `npx vue-tsc -b --pretty false` 退出码 0**

`frontend/src/api/cave.ts` 可能仍有未提交脏改：只加印制包装，不要把无关 diff 打进本任务 commit。

---

### Task 6: 回归与文档

**Files:**
- Modify: `docs/superpowers/specs/2026-08-27-technique-research-design.md` 状态行：P1+P2 已实现，P3/P4 未做
- Modify: `README.md`、`CHANGELOG.md` 一句

- [ ] **Step 1: 后端回归**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_technique_craft.py tests/test_research_technique_finalize.py tests/test_research_formation_blueprint.py tests/test_research_talisman_whitelist.py tests/test_content_validator.py -q`

Expected: PASS

- [ ] **Step 2: 前端 `npx vue-tsc -b --pretty false`**
- [ ] **Step 3: 文档**

---

## Spec coverage（自检）

| Spec | 任务 |
| --- | --- |
| 仅原创者印当下快照 | T2 |
| 高消耗读 YAML | T1 T2 |
| 署名、不并堆混版本 | T2（meta 快照） |
| 学成消失、一本一人 | T3 |
| 境界 ≥ 功法阶，低于不学不扣 | T3 |
| 原值不打折 | T3 |
| 新对象；原创仍可培养 | T2 T3 |
| 副本不能培养、不能再印 | T4 |
| 拍卖/给予后接现有交易 | 不实现，只保证背包 tradable |
| 藏经阁 / 师徒 | **P3 / P4，本计划不做** |

## 后续计划（不要在本计划实现）

- P3 藏经阁：放入耗秘籍变永久条目
- P4 师徒次数/折扣/再学替换
