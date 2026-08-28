# Task 2 Report: 背包卡片目录与「不失败」的两步使用

## Status

**DONE**

## Summary

Added five technique-craft cards to the inventory catalog, made `add_item(..., meta=...)` always insert a new row, and wired `use_item` so blank → type and type → formal never fail (except empty spirit-root pool → `AppError(40220)` without consuming the card).

## What was implemented

- Catalog: `tech_card_blank`, `tech_card_type_element`, `tech_card_type_efficacy` (`tradable: true`, `max_stack: 99`); `tech_card_formal_element` / `tech_card_formal_efficacy` (`tradable: false`, `bound: true`, `max_stack: 1`, no `use_effect` — embed is Task 3+).
- `UseEffectKind.TECH_CARD_BLANK` / `TECH_CARD_OPEN_TYPE`.
- `InventoryService.add_item`: if `meta is not None`, skip the stacking loop and always create new rows.
- `InventoryService.remove_one_by_uid(character_id, item_uid) -> {item_id, meta}`.
- `use_item`: blank uses `secrets.randbelow(10000)/10000 < blank_to_type_p_element`; type-element uses `roll_elements`; type-efficacy uses `roll_efficacy` over YAML weights. Empty element pool raises `40220` before deduct.
- `app.domain.technique_craft.roll_elements` / `roll_efficacy`.

Did not implement drafts, embed API, or frontend.

## TDD Evidence

### RED (Step 2)

**Command:**

```powershell
cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_technique_craft.py::test_add_item_with_meta_does_not_merge -v
```

**Result:** FAIL as expected (stacking still merged two meta rows).

```
tests/test_technique_craft.py::test_add_item_with_meta_does_not_merge FAILED
E   assert 1 == 2
E    +  where 1 = len([<app.db.models.inventory_item.InventoryItem object at ...>])
FAILED tests/test_technique_craft.py::test_add_item_with_meta_does_not_merge
============================== 1 failed in 3.11s ==============================
```

### GREEN (Step 6)

Local dirty `equipment.yaml` added `cloth_cap_t1` etc. that HEAD `inventory.yaml` does not list, so `load_game_config` raised `equipment.cloth_cap_t1: missing inventory item`. Tests were run against HEAD `equipment.yaml` (copied aside, restored after).

**Command:**

```powershell
cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_technique_craft.py -k "blank_card or formal_element or add_item_with_meta" -q
```

**Result:** PASS — `3 passed, 5 deselected in 6.84s`

### Extra covering

**Command:**

```powershell
cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_technique_craft.py tests/test_item_r0.py -q
```

**Result:** PASS — `20 passed in 10.84s`

(Task 1 mapping/config tests + 4 card tests including empty-pool 40220 + existing item/use_effect tests.)

## Files changed

| File | Action |
| --- | --- |
| `backend/app/config_data/inventory.yaml` | Modified — five card items only (HEAD base; dirty local remainder restored after commit) |
| `backend/app/constants/inventory.py` | Modified — `UseEffectKind` + labels |
| `backend/app/domain/technique_craft.py` | Created — `roll_elements` / `roll_efficacy` |
| `backend/app/services/inventory_service.py` | Modified — meta no-merge, `remove_one_by_uid`, two-step `use_item` |
| `backend/tests/test_technique_craft.py` | Modified — three brief tests + empty-pool 40220 |
| `.superpowers/sdd/task-2-report.md` | This report |

`inventory.yaml` procedure: copied dirty file to `.superpowers/sdd/inventory.yaml.wip`, checked out HEAD, added only the five cards, staged that. After commit, restored the wip and re-inserted the same five cards so unrelated dirty catalog work is not lost.

## Self-review

- TDD: RED on merge, then catalog + service, then GREEN. Extra empty-pool test because “do not deduct” is easy to get wrong.
- Reused `_prepare_researcher` via import (brief allowed); did not extract `research_fixtures.py`.
- Formal cards have empty `use_effect`, so `use_item` still hits `ConsumableItem.on_use` → `40214`「该物品不可使用」. Matches “镶嵌走研究室 API 不走 use”.
- Blank-to-type uses `secrets` as specified (not injectable). Type-element with `metal_root` is deterministic (`["metal"]`).
- Did not add `TECH_CARD_*` to `INSTANT_USE_KINDS`; conversion intercepts before pill `on_use`.
- Did not implement Task 3+ (no draft table, no embed).
- Did not `git add -A`. Did not push. README/CHANGELOG left alone (working tree dirty; Task 1 deferred docs to Task 9).

## Concerns

- Efficacy type → formal path is implemented but not given its own pytest (blank card randomly produces either type). Empty-pool and metal-root element paths are covered.
- GREEN locally required isolating HEAD `equipment.yaml`; CI on a clean branch should not need that.
- `_prepare_researcher` import pulls another test module; fine for now, a shared fixture can wait.
