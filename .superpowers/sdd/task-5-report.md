# Task 5 Report: 发动条件 + 词条三选一/重随

## Status

**DONE**

## Commits

- (filled after git commit)

## Summary

Added launch conditions (`set_conditions`) and affix roll / choose / reroll. Conditions require embedded elements + efficacy; both boxes may be empty. Affix columns = `ranks[major_rank].affix_slots`. Roll is allowed before conditions. Reroll spends `cultivation_points` (spell / idle_spirit) or `body_tempering_points` (martial / idle_body) and clears `chosen_level` / `upgrade_count`.

Did not implement finalize/equip (Task 6).

## What was implemented

- `filter_affixes`: keep `efficacy in efficacy_allow`; hide other family via `SPELL_EFFICACIES` / `MARTIAL_EFFICACIES`; drop `role=defense` when efficacy ∈ `ATTACK_EFFICACIES`. Empty `weapon_limit` does not filter weapons.
- `roll_three`: 3 ids; duplicates when pool < 3 (1-item pool → three identical options).
- `POST .../conditions` `{element_limit?, weapon_limit?}`
- `POST .../affix/roll` `{slot}` (free; first generation)
- `POST .../affix/choose` `{slot, affix_id}`
- `POST .../affix/reroll` `{slot}` cost `affix_reroll_cost[min(n, len-1)]`

## TDD Evidence

### RED (Step 1)

**Command:**

```powershell
cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_technique_craft.py -k "affix or conditions or filter" -q
```

**Result:** FAIL as expected (`filter_affixes` / `roll_three` missing).

```
ImportError: cannot import name 'filter_affixes' from 'app.domain.technique_craft'
1 error in 0.63s
```

### GREEN (Step 3)

**Command (brief):**

```powershell
cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_technique_craft.py -k "affix or conditions or filter" -q
```

**Result:** PASS — `5 passed, 14 deselected in 7.54s`

**Extra:** full `tests/test_technique_craft.py`: `19 passed in 25.84s`

## Files changed

| File | Action |
| --- | --- |
| `backend/app/domain/technique_craft.py` | Modified — `filter_affixes`, `roll_three` |
| `backend/app/services/technique_craft_service.py` | Modified — conditions + affix roll/choose/reroll |
| `backend/app/schemas/technique_craft.py` | Modified — request bodies |
| `backend/app/api/research.py` | Modified — four lab routes |
| `backend/tests/test_technique_craft.py` | Modified — filter, roll_three, conditions, choose, reroll |
| `.superpowers/sdd/task-5-report.md` | This report |

Did not `git add -A`. Did not push. README/CHANGELOG left alone (docs deferred to Task 9). Did not implement Task 6+.

## Self-review

- TDD: RED on missing `filter_affixes`, then domain + service + routes, then GREEN.
- Choose test rolls without calling `set_conditions` (roll-before-conditions).
- Spell reroll deducts `character.cultivation_points` (same field as `ResearchService`); no new ledger.
- Writes reuse `_prepare_research_write`.
- `can_finalize` stays false.

## Concerns

1. No `conditions_confirmed` column yet; empty limits look like the create-draft default. Task 6 needs a boolean.
2. Martial / idle_body reroll (`body_tempering_points`) is implemented but not in the brief tests.
3. Illegal `element_limit` / `weapon_limit` / slot index / empty pool: coded (40220 / 40208 / 40221) but untested.
4. No HTTP-level pytest for the four new routes.
5. YAML affixes have no `weapon_allow` / `element_allow` / `role=defense`; those extra filters are ready but unused.
6. Changing conditions after a roll does not redraw existing `options`.
