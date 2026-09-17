# 功法自研 P1（创造与培养）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在研究室功法页用三步卡创造多份草稿、定稿进已学列表，并让原创者能升级基础加成、词条和功法阶（不经秘籍/藏经阁/师徒）。

**Architecture:** 阵法/符箓继续走现有 `ResearchService` 会话。功法从该会话剥离到 `TechniqueCraftService` + 表 `technique_research_drafts`；卡片是背包 `consumable`（空白/类型可堆叠；正式卡带 `meta_json` 且不合并堆叠）。定稿写入现有 `private_techniques`（扩展 payload）和 `character_techniques`。数值全部来自 `research.yaml` 的 `technique_craft` 段。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy async、pytest、Vue 3、Pinia、现有 `AppError` 信封、`DiceService`、`InventoryService`、`PlayGate`。

**Spec:** `docs/superpowers/specs/2026-08-27-technique-research-design.md`（仅 P1：§1–7、§9、§10 P1、§11 中与创造/培养相关的配置）。

## Global Constraints

- 注释与 docstring 英文标识符；复杂规则可用中文注释。
- 数值禁止写死在 `if` 分支，必须读 `get_game_config().research.technique_craft`。
- 阵法/符箓自研 API 与单测不得无故失败。
- 旧功法 R2「选材料 → 预览词条 → 定稿」路径删除或改为调用新服务；`test_research_technique_finalize.py` 改为新规则。
- **不要自动 git commit**，除非用户明确要求。
- 每次任务同步 `README.md` 与 `CHANGELOG.md` 一句进度（不必每步都改）。
- 失败无保底。放弃草稿不退已镶嵌消耗的正式卡。
- 测试用 `tests.async_db.open_test_session_factory` + DEBUG 注册，与 `test_research_technique_finalize.py` 相同。

---

## File map

| 路径 | 职责 |
| --- | --- |
| `backend/app/constants/technique_craft.py` | 效能/卡阶段/发动条件/错误码/灵根→元素 |
| `backend/app/config_data/research.yaml` | 新增 `technique_craft:` 占位数值与词条目录 |
| `backend/app/config_data/inventory.yaml` | 空白卡、属性类型卡、效能类型卡、两张正式卡目录 |
| `backend/app/constants/inventory.py` | `UseEffectKind` 增加卡片使用 kind |
| `backend/app/services/realm_config.py` | 解析 `technique_craft` |
| `backend/app/config_source/validate_content.py` | 校验词条 ATTR 键、效能枚举 |
| `backend/app/db/models/technique_craft.py` | `TechniqueResearchDraft` |
| `backend/app/db/models/research.py` | `PrivateTechnique` 增加 `payload_json` / `major_rank` / `author_character_id` |
| `backend/app/db/models/__init__.py` | 导出新模型 |
| `backend/app/db/bootstrap.py` | SQLite 给 `private_techniques` 补列 |
| `backend/app/domain/technique_craft.py` | 纯函数：抽属性、过滤词条、升级点、阶门槛、ATTR 汇总 |
| `backend/app/services/technique_craft_service.py` | 草稿/镶嵌/定稿/培养编排 |
| `backend/app/services/inventory_service.py` | `meta` 非空则新建行；按 `item_uid` 扣 1 |
| `backend/app/services/inventory_service.py`（use） | 空白→类型、类型→正式 |
| `backend/app/services/technique_service.py` | 修炼效能才能装备主功法格；payload ATTR |
| `backend/app/admin_api` / `api/research.py` 或 `api/cave.py` | `/cave/lab/technique/*` 路由 |
| `backend/app/services/gm_service.py` | GM 发空白卡 |
| `backend/tests/test_technique_craft.py` | P1 单测 |
| `frontend/src/types/techniqueCraft.ts` | DTO |
| `frontend/src/api/cave.ts` | 新 API |
| `frontend/src/stores/techniqueCraft.ts` | 研究室功法状态 |
| `frontend/src/components/research/TechniqueResearchPanel.vue` | 重做 UI |
| `frontend/src/constants/craft.ts` 不改 | 工坊筛选与本玩法无关 |

**P2–P4 不在本计划：** 秘籍、藏经阁、师徒。本计划结束后另写 `2026-08-27-technique-research-p2.md` 等。

---

### Task 1: 协议常量、YAML、解析、灵根映射

**Files:**
- Create: `backend/app/constants/technique_craft.py`
- Modify: `backend/app/config_data/research.yaml`
- Modify: `backend/app/services/realm_config.py`（`ResearchConfig` / `_parse_research`）
- Modify: `backend/app/config_source/validate_content.py`
- Test: `backend/tests/test_technique_craft.py`

**Produces:**
- `EFFICACY_IDS: tuple[str, ...] = ("spell_attack", "spell_buff", "martial_attack", "martial_buff", "idle_spirit", "idle_body")`
- `element_ids_from_spirit_root_tags(tags: list[str]) -> list[str]`
- `get_game_config().research.technique_craft` 含失败率、各阶表、词条目录

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_technique_craft.py`：

```python
from app.constants.technique_craft import element_ids_from_spirit_root_tags
from app.services.realm_config import clear_game_config_cache, get_game_config


def test_mixed_root_expands_to_five_elements() -> None:
    got = set(element_ids_from_spirit_root_tags(["mixed_root"]))
    assert got == {"metal", "wood", "water", "fire", "earth"}


def test_metal_root_only_metal() -> None:
    assert element_ids_from_spirit_root_tags(["metal_root"]) == ["metal"]


def test_technique_craft_config_loads() -> None:
    clear_game_config_cache()
    craft = get_game_config().research.technique_craft
    assert abs(craft.blank_to_type_p_element - 0.5) < 1e-6
    assert "spell_attack" in craft.efficacy_weights
    assert craft.embed_fail_rate >= 0
    assert "body_tempering" in craft.ranks
    assert len(craft.affixes) >= 6
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_technique_craft.py::test_mixed_root_expands_to_five_elements tests/test_technique_craft.py::test_technique_craft_config_loads -v`

Expected: FAIL（模块或属性不存在）

- [ ] **Step 3: 实现常量与映射**

`backend/app/constants/technique_craft.py`：

```python
from __future__ import annotations
from typing import Final
from app.constants.technique import (
    ELEMENT_EARTH, ELEMENT_FIRE, ELEMENT_METAL, ELEMENT_THUNDER,
    ELEMENT_WATER, ELEMENT_WIND, ELEMENT_WOOD,
)

ERR_CRAFT_CARD: Final[int] = 40220
ERR_CRAFT_EMBED: Final[int] = 40221
ERR_CRAFT_FINALIZE: Final[int] = 40222
ERR_CRAFT_CULTIVATE: Final[int] = 40223
ERR_CRAFT_EQUIP_ROLE: Final[int] = 40224

EFFICACY_SPELL_ATTACK: Final[str] = "spell_attack"
EFFICACY_SPELL_BUFF: Final[str] = "spell_buff"
EFFICACY_MARTIAL_ATTACK: Final[str] = "martial_attack"
EFFICACY_MARTIAL_BUFF: Final[str] = "martial_buff"
EFFICACY_IDLE_SPIRIT: Final[str] = "idle_spirit"
EFFICACY_IDLE_BODY: Final[str] = "idle_body"
EFFICACY_IDS: Final[tuple[str, ...]] = (
    EFFICACY_SPELL_ATTACK, EFFICACY_SPELL_BUFF,
    EFFICACY_MARTIAL_ATTACK, EFFICACY_MARTIAL_BUFF,
    EFFICACY_IDLE_SPIRIT, EFFICACY_IDLE_BODY,
)
IDLE_EFFICACIES: Final[frozenset[str]] = frozenset({EFFICACY_IDLE_SPIRIT, EFFICACY_IDLE_BODY})
SPELL_EFFICACIES: Final[frozenset[str]] = frozenset({EFFICACY_SPELL_ATTACK, EFFICACY_SPELL_BUFF, EFFICACY_IDLE_SPIRIT})
MARTIAL_EFFICACIES: Final[frozenset[str]] = frozenset({EFFICACY_MARTIAL_ATTACK, EFFICACY_MARTIAL_BUFF, EFFICACY_IDLE_BODY})
ATTACK_EFFICACIES: Final[frozenset[str]] = frozenset({EFFICACY_SPELL_ATTACK, EFFICACY_MARTIAL_ATTACK})

CARD_BLANK_ID: Final[str] = "tech_card_blank"
CARD_TYPE_ELEMENT_ID: Final[str] = "tech_card_type_element"
CARD_TYPE_EFFICACY_ID: Final[str] = "tech_card_type_efficacy"
CARD_FORMAL_ELEMENT_ID: Final[str] = "tech_card_formal_element"
CARD_FORMAL_EFFICACY_ID: Final[str] = "tech_card_formal_efficacy"

WEAPON_LIMITS: Final[tuple[str, ...]] = (
    "sword", "saber", "spear", "gauntlet", "bow", "puppet", "avatar",
)

ROOT_TAG_TO_ELEMENTS: Final[dict[str, tuple[str, ...]]] = {
    "metal_root": (ELEMENT_METAL,),
    "wood_root": (ELEMENT_WOOD,),
    "water_root": (ELEMENT_WATER,),
    "fire_root": (ELEMENT_FIRE,),
    "earth_root": (ELEMENT_EARTH,),
    "thunder_root": (ELEMENT_THUNDER,),
    "wind_root": (ELEMENT_WIND,),
    "mixed_root": (ELEMENT_METAL, ELEMENT_WOOD, ELEMENT_WATER, ELEMENT_FIRE, ELEMENT_EARTH),
}

def element_ids_from_spirit_root_tags(tags: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        for el in ROOT_TAG_TO_ELEMENTS.get(str(tag), ()):
            if el not in seen:
                seen.add(el)
                ordered.append(el)
    return ordered
```

- [ ] **Step 4: 追加 `research.yaml` 的 `technique_craft`**

挂在文件根上（与现有 `technique:` 并列）。占位如下（可微调数字，键名必须一致）：

```yaml
technique_craft:
  help_zh: 用空白卡生成属性/效能正式卡，镶入草稿后选发动条件与词条，定稿后可培养。
  blank_to_type_p_element: 0.5
  efficacy_weights:
    spell_attack: 1
    spell_buff: 1
    martial_attack: 1
    martial_buff: 1
    idle_spirit: 1
    idle_body: 1
  embed_fail_rate: 0.2
  affix_upgrade_fail_rate: 0.2
  breakthrough_fail_rate: 0.3
  base_bonus_points: [5, 10, 20]
  affix_upgrade_points: [5, 10, 20]
  spirit_upgrade_cost: [20, 40, 80, 160]
  body_upgrade_cost: [20, 40, 80, 160]
  affix_upgrade_cost: [15, 30, 60, 120]
  affix_reroll_cost: [10, 20, 40, 80]
  breakthrough_cost_cultivation: 50
  breakthrough_cost_body: 50
  ranks:
    body_tempering:
      affix_slots: 1
      base_upgrade_cap: 3
      upgrade_points_required: 10
    qi_refining:
      affix_slots: 2
      base_upgrade_cap: 6
      upgrade_points_required: 100
  weapon_bonus:
    sword: { phys_atk: 2 }
    saber: { phys_atk: 2 }
    spear: { phys_atk: 2 }
    gauntlet: { phys_atk: 2 }
    bow: { phys_atk: 2 }
    puppet: { phys_atk: 2 }
    avatar: { magic_atk: 2 }
  affixes:
    sa_edge:
      label_zh: 法锋
      efficacy_allow: [spell_attack]
      role: attack
      stats: { magic_atk: 3 }
    sb_ward:
      label_zh: 法盾
      efficacy_allow: [spell_buff]
      role: buff
      stats: { magic_def: 3 }
    ma_edge:
      label_zh: 武锋
      efficacy_allow: [martial_attack]
      role: attack
      stats: { phys_atk: 3 }
    mb_ward:
      label_zh: 武御
      efficacy_allow: [martial_buff]
      role: buff
      stats: { phys_def: 3 }
    is_flow:
      label_zh: 周天
      efficacy_allow: [idle_spirit]
      role: idle
      stats: { magic_atk: 1 }
    ib_bone:
      label_zh: 锻骨
      efficacy_allow: [idle_body]
      role: idle
      stats: { phys_atk: 1 }
```

现有 `technique:` 材料会话块保留给兼容，但功法 HTTP 不再使用它创建会话。

- [ ] **Step 5: 解析进 `ResearchConfig.technique_craft`**

在 `realm_config.py` 增加 frozen dataclass `TechniqueCraftConfig`（字段与 YAML 键对应：`blank_to_type_p_element: float`、`efficacy_weights: dict[str, float]`、`ranks: dict[str, TechniqueCraftRankConfig]`、`affixes: dict[str, TechniqueCraftAffixDef]` 等）。`_parse_research` 末尾解析 `raw.get("technique_craft") or {}`，缺省时用与 YAML 相同的占位，避免旧测试环境空段崩掉。

词条 `stats` 必须走现有 `assert_attr_stats`。

- [ ] **Step 6: 校验器**

`validate_content.py`：每个 affix 的 `efficacy_allow` ⊆ `EFFICACY_IDS`；`role` ∈ `{attack, buff, idle, defense}`；`ranks` 的键须为 `realms.yaml` 大境界 id。

- [ ] **Step 7: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_technique_craft.py::test_mixed_root_expands_to_five_elements tests/test_technique_craft.py::test_metal_root_only_metal tests/test_technique_craft.py::test_technique_craft_config_loads tests/test_content_validator.py -q`

Expected: PASS

---

### Task 2: 背包卡片目录与「不失败」的两步使用

**Files:**
- Modify: `backend/app/config_data/inventory.yaml`
- Modify: `backend/app/constants/inventory.py`
- Modify: `backend/app/services/inventory_service.py`（`add_item`、`use_item`）
- Modify: `backend/app/domain/technique_craft.py`（抽属性、抽效能）
- Test: `backend/tests/test_technique_craft.py`

**Consumes:** Task 1 卡 id 常量、`element_ids_from_spirit_root_tags`、`technique_craft` 权重

**Produces:**
- `InventoryService.add_item(..., meta=dict)`：`meta` 非 `None` 时**始终新建行**，不合并已有堆
- `InventoryService.remove_one_by_uid(character_id, item_uid) -> dict` 返回被扣行的 `item_id` + 解析后的 meta
- 使用空白卡 → 扣 1 张空白，发 1 张类型卡（`secrets.random` vs `blank_to_type_p_element`）
- 使用属性类型卡 → 扣类型卡，发正式属性卡，`meta={"elements": ["metal", ...]}`
- 使用效能类型卡 → `meta={"efficacy": "spell_attack"}`
- 无可用元素时使用属性类型卡 → `AppError(40220)`，不扣卡

- [ ] **Step 1: 写失败测试**

```python
import json
from sqlalchemy import select
from app.db.models.inventory_item import InventoryItem
from app.constants.technique_craft import CARD_BLANK_ID, CARD_TYPE_ELEMENT_ID, CARD_TYPE_EFFICACY_ID
from app.services.inventory_service import InventoryService
from tests.async_db import open_test_session_factory, run_async as _run
# 复用 test_research_technique_finalize._prepare_researcher 或把 helper 抽到 tests/research_fixtures.py


def test_blank_card_becomes_type_card(tmp_path) -> None:
    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "blank.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "blank@test.com", "空白测")
                inv = InventoryService(session)
                await inv.add_item(char.id, "consumable", CARD_BLANK_ID, 1)
                await session.commit()
                row = (await session.execute(
                    select(InventoryItem).where(InventoryItem.character_id == char.id, InventoryItem.item_id == CARD_BLANK_ID)
                )).scalar_one()
                await inv.use_item(char, row.item_uid)
                await session.commit()
                left = list((await session.execute(
                    select(InventoryItem).where(
                        InventoryItem.character_id == char.id,
                        InventoryItem.item_id == CARD_BLANK_ID,
                        InventoryItem.quantity > 0,
                    )
                )).scalars())
                assert left == []
                type_ids = {
                    r.item_id
                    for r in (await session.execute(
                        select(InventoryItem).where(
                            InventoryItem.character_id == char.id,
                            InventoryItem.quantity > 0,
                        )
                    )).scalars()
                }
                assert CARD_TYPE_ELEMENT_ID in type_ids or CARD_TYPE_EFFICACY_ID in type_ids
    _run(_body())
```

另写 `test_formal_element_card_uses_actor_roots`：角色 `spirit_root_tags_json='["metal_root"]'`，使用属性类型卡后 `meta.elements == ["metal"]`。

`test_add_item_with_meta_does_not_merge`：两次 `add_item(..., meta={"elements":["metal"]})` 与 `meta={"elements":["fire"]}` 得到两行。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_technique_craft.py::test_add_item_with_meta_does_not_merge -v`

Expected: FAIL

- [ ] **Step 3: inventory.yaml 四条 + 正式卡两条**

`item_type: consumable`，空白与类型 `tradable: true`，`max_stack: 99`。正式卡 `tradable: false`，`bound: true`，`max_stack: 1`，`use_effect.kind` 分别为 `tech_card_blank` / `tech_card_open_type` / `tech_card_open_formal`（正式卡 kind 可为空，镶嵌走研究室 API 不走 use）。

在 `UseEffectKind` 追加：`TECH_CARD_BLANK = "tech_card_blank"`，`TECH_CARD_OPEN_TYPE = "tech_card_open_type"`。

- [ ] **Step 4: `add_item` 分支**

若 `meta is not None`：跳过堆叠循环，直接 `while remaining` 新建行（与现循环内 `InventoryItem(...)` 相同）。

- [ ] **Step 5: `use_item` 分支**

读 `defn.use_effect.kind`：空白则 `secrets.randbelow(10000)/10000 < p` 发属性类型否则效能类型。类型卡看 `item_id` 决定抽元素或效能。抽元素：`domain.technique_craft.roll_elements(pool, rng)` — 种数 `randint(1, len(pool))` 再 `sample`。抽效能：按 `efficacy_weights` 加权。正式卡不可 `use_item`（研究室镶嵌）。

无元素池：`raise AppError(code=40220, message="灵根无法生成属性卡")`，且不扣数量。

- [ ] **Step 6: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_technique_craft.py -k "blank_card or formal_element or add_item_with_meta" -q`

Expected: PASS

---

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

### Task 7: 原创培养（基础加成、词条升级、突破）

**Files:**
- Modify: `technique_craft_service.py`
- API：`POST .../techniques/{technique_id}/base-upgrade` `{stat: attack|defense|speed}`；`POST .../affix-upgrade` `{slot}`；`POST .../breakthrough`
- Domain：`upgrade_points_for_base_level(n)`、`rank_cap(character.major_realm, ranks.keys())`、`can_breakthrough`
- `technique_service` 列表/战斗 grants：把 `base_json` 的 attack/defense/speed 按效能映射到 `phys_atk`/`magic_atk`/`phys_def`/`magic_def`/`speed`，再加词条 `stats * (1 + 0.2 * chosen_level)`（系数放 YAML `affix_level_mult: 0.2`）
- Test: `backend/tests/test_technique_craft.py`

规则：
- 仅 `author_character_id == character.id` 的 `source=research` 可培养。
- 基础加成：`total_upgrades + 1 <= ranks[major_rank].base_upgrade_cap`；费用取 `spirit_upgrade_cost` 或 `body_upgrade_cost` 下标 `min(total_upgrades, len-1)`；成功则对应 stat +1 段（payload 里存次数即可，展示点数 = 次数，ATTR = 次数 × YAML `base_stat_per_click` 默认 1）。
- `upgrade_points += base_bonus_points[min(new_level-1, len-1)]`。
- 词条升级：失败率 `affix_upgrade_fail_rate`，失败仍扣费；成功 `chosen_level += 1` 并加点。
- 突破：`upgrade_points >= ranks[next].upgrade_points_required` 且 `next` 在角色 `major_realm` 及以下（用 `realms.yaml` 的 `next_major` 链，下一阶 id 的「高度」≤ 角色当前高度）。下一阶不存在或超过人物境界 → 40223。失败只扣 `breakthrough_cost_*`（法术扣修为、武技扣炼体；修炼类按 SPELL/MARTIAL 集）。成功改 `major_rank`，**不扣** upgrade_points；若新阶 `affix_slots` 更大，给新栏空位。

定稿后培养改 `PrivateTechnique.payload_json`，不再写草稿行。

- [ ] **Step 1: 测试** 连续两次加 attack 第二次更贵；突破失败点不变阶不变；突破成功阶升点仍在；词条失败等级不变

- [ ] **Step 2: 实现并跑通**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_technique_craft.py -q`

Expected: PASS

---

### Task 8: 前端研究室功法页

**Files:**
- Create: `frontend/src/types/techniqueCraft.ts`
- Create: `frontend/src/stores/techniqueCraft.ts`
- Modify: `frontend/src/api/cave.ts`
- Modify: `frontend/src/components/research/TechniqueResearchPanel.vue`
- Modify: `frontend/src/stores/research.ts`（功法不再 `create({ kind: 'technique', materials })`）
- Test: `cd frontend && npx vue-tsc -b --pretty false`

UI（现行 1100px 玩法壳、`el-button size="small"`）：
- 列表多份草稿 +「新建草稿」
- 背包展示空白/类型/正式卡；使用空白/类型走现有物品使用 API（若没有，加 `POST /inventory/use {item_uid}` 已有则复用）
- 草稿：镶嵌下拉正式卡 → 条件两框 → 词条三选一/重随 → 定稿
- 已定稿原创：基础加成三钮、词条升级、突破；攻击类藏「装备主功法」提示

- [ ] **Step 1: 接 API 类型与 store**
- [ ] **Step 2: 重写面板，去掉材料多选与旧 reroll**
- [ ] **Step 3: `npx vue-tsc -b --pretty false` 退出码 0**

---

### Task 9: GM 发卡、旧测迁移、文档

**Files:**
- Modify: `backend/app/services/gm_service.py`（`grant_craft_materials` 顺带 `add_item` 空白卡 10 张，或新开关 `grant_technique_cards`）
- Modify: `backend/tests/test_research_technique_finalize.py`（删除非法材料会话用例或改为「technique kind 拒绝旧 create_session」）
- Modify: `docs/superpowers/specs/2026-08-27-technique-research-design.md` 状态改为 P1 实现中/已实现
- Modify: `README.md`、`CHANGELOG.md`、`设计文档/M8自研与内容管线设计.md` 一句 P1 进度

- [ ] **Step 1: GM 发 `tech_card_blank`**
- [ ] **Step 2: 全量相关测**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_technique_craft.py tests/test_research_technique_finalize.py tests/test_research_formation_blueprint.py tests/test_research_talisman_whitelist.py tests/test_content_validator.py -q`

Expected: PASS

- [ ] **Step 3: 前端 `npx vue-tsc -b --pretty false`**
- [ ] **Step 4: 文档同步**

---

## Spec coverage（自检）

| Spec | 任务 |
| --- | --- |
| 三步卡、交易性、灵根抽属性、镶嵌失败 | T2 T4 |
| 多草稿、放弃不退卡 | T3 |
| 定稿门槛、锁死属性/效能/条件 | T5 T6 |
| 主/技法效能限制 | T6 |
| 基础加成累计次数与阶上限 | T7 |
| 词条过滤/三选一/重随归零/升级失败 | T5 T7 |
| 功法阶=大境界名、点不扣、突破失败 | T7 |
| 配置 YAML | T1 |
| 秘籍/藏经阁/师徒 | **本计划不做（P2–P4）** |

## 后续计划（不要在本计划实现）

- P2 秘籍：`manual_kind=technique` 实例 + 署名 + 境界门槛学习 + 副本只读
- P3 藏经阁条目
- P4 师徒次数/折扣/再学替换
