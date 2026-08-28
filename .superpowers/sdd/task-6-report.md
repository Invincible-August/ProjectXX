# Task 6 Report: 定稿、已学列表、装备角色限制

## Status

**DONE**

## Commits

- `ddb7a84` Add draft finalize, learned-list insert, and main-slot efficacy gate.

## Summary

Finalize writes `PrivateTechnique` + `CharacterTechnique` (`source=research`, id `custom:technique:{cid}:{slug}`). Draft `phase=finalized` and drops out of `list_drafts`. Gate: elements, efficacy, `conditions_confirmed` (both boxes may be empty), at least one `chosen_id` still in the current affix pool. Main-slot equip of non-idle efficacy raises `40224`. Art slots accept all six. Did not implement cultivate APIs (Task 7).

## What was implemented

- `TechniqueResearchDraft.conditions_confirmed` Boolean; `set_conditions` sets it true.
- `PrivateTechnique.payload_json` / `major_rank` / `author_character_id`; SQLite patch via `_patch_sqlite_table_columns` on `private_techniques` and `technique_research_drafts`.
- `TechniqueCraftService.finalize_draft` + `POST /cave/lab/technique/drafts/{id}/finalize`.
- `ResearchService.list_mine` / `TechniqueService.list_my_techniques` add `efficacy`, `author_character_id`, `cultivable`.
- `equip_technique`: `slot=main` and `efficacy ∉ IDLE_EFFICACIES` → `AppError(40224, "该功法不能装备为主功法")`. Same id still cannot occupy main+art (existing clear-then-set).

## TDD Evidence

### RED (Step 1)

**Command:**

```powershell
cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_technique_craft.py -k "finalize or equip" tests/test_research_technique_finalize.py -q
```

**Result:** FAIL as expected (`finalize_draft` missing).

```
AttributeError: 'TechniqueCraftService' object has no attribute 'finalize_draft'
5 failed, 1 passed, 19 deselected in 9.14s
```

### GREEN (Step 3)

**Command (brief):**

```powershell
cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_technique_craft.py -k "finalize or equip" tests/test_research_technique_finalize.py -q
```

**Result:** PASS — `6 passed, 19 deselected in 8.85s`

**Extra:** `tests/test_technique_craft.py` + `tests/test_technique_loadout.py` + `tests/test_research_technique_finalize.py`: `27 passed in 30.72s`

## Files changed

| File | Action |
| --- | --- |
| `backend/app/db/models/research.py` | Modified — payload_json / major_rank / author_character_id |
| `backend/app/db/models/technique_craft.py` | Modified — conditions_confirmed |
| `backend/app/db/bootstrap.py` | Modified — SQLite patches for both tables |
| `backend/app/constants/technique_craft.py` | Modified — DRAFT_PHASE_FINALIZED |
| `backend/app/services/technique_craft_service.py` | Modified — finalize_draft, conditions flag, list filter |
| `backend/app/services/technique_service.py` | Modified — list DTO + main-slot 40224 |
| `backend/app/services/research_service.py` | Modified — list_mine DTO |
| `backend/app/schemas/technique_craft.py` | Modified — TechniqueFinalizeRequest |
| `backend/app/api/research.py` | Modified — POST .../finalize |
| `backend/tests/test_technique_craft.py` | Modified — four named tests |
| `backend/tests/test_research_technique_finalize.py` | Rewritten — new finalize then equip |
| `.superpowers/sdd/task-6-report.md` | This report |

Did not `git add -A`. Did not push. README/CHANGELOG left alone (docs deferred to Task 9). Did not implement Task 7+.

## Self-review

- TDD: RED on missing `finalize_draft`, then models/bootstrap/service/equip, then GREEN.
- `conditions_confirmed` distinguishes “conditions API called with both empty” from the create-draft default.
- Finalize re-filters chosen affixes against current efficacy/conditions (Task 5 does not redraw options after conditions change).
- Official techniques have no `efficacy` on the list DTO, so the main-slot gate does not affect them.
- Writes reuse `_prepare_research_write`.

## Concerns

1. `can_finalize` on the draft DTO does not re-check affix-pool match; only `finalize_draft` does.
2. Missing-conditions / empty-embed / stale-affix 40222 paths are implemented but not in the four named tests.
3. No HTTP-level pytest for `POST .../finalize`.
4. `CharacterTechnique.technique_id` remains `String(64)` while `PrivateTechnique` is `String(128)`; current ids fit.
5. Old R2 `finalize_session` technique body is still dead code (Task 9).
