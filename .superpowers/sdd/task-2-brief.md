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
