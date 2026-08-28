# Task 3 Report: 草稿表与创建/列表/放弃

## Status

**DONE**

## Commits

- `6fee389` Add technique-research drafts with create, list, and abandon.

## Summary

Added table `technique_research_drafts`, `TechniqueCraftService` (create / list / abandon), and `/cave/lab/technique/drafts` HTTP. Creating a draft does not consume cards. Abandoned drafts stay in the table (`phase=abandoned`) and drop out of `list_drafts`. Old `ResearchService.create_session(kind="technique")` raises `AppError(40201, "请改用功法自研草稿接口")`. Formation/talisman sessions unchanged.

Did not implement embed, conditions, finalize, or frontend.

## What was implemented

- ORM `TechniqueResearchDraft` with columns from the brief; `phase` starts `embedding`; `major_rank` starts as the character’s current `major_realm`.
- `TechniqueCraftService.create_draft` / `list_drafts` (excludes `phase=abandoned`) / `abandon_draft` (no card refund).
- Public payload includes `id, phase, elements, efficacy, can_finalize=false` (always false this task).
- Routes on the existing lab router (PlayGate): `GET/POST /cave/lab/technique/drafts`, `POST /cave/lab/technique/drafts/{id}/abandon`. Writes use `_prepare_research_write`.
- `ResearchService.create_session(kind="technique")` rejected with existing code `40201` (`ERR_RESEARCH_SESSION`). No new error codes.

## TDD Evidence

### RED (Step 2)

**Command:**

```powershell
cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_technique_craft.py::test_create_two_drafts_independent -v
```

**Result:** FAIL as expected (service module missing).

```
ImportError while importing test module '.../tests/test_technique_craft.py'.
tests\test_technique_craft.py:27: in <module>
    from app.services.technique_craft_service import TechniqueCraftService
E   ModuleNotFoundError: No module named 'app.services.technique_craft_service'
ERROR tests/test_technique_craft.py
============================== 1 error in 0.93s ===============================
```

### GREEN (Step 5)

**Command (brief):**

```powershell
cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_technique_craft.py::test_create_two_drafts_independent tests/test_research_formation_blueprint.py tests/test_research_talisman_whitelist.py -q
```

**Result:** PASS — `9 passed in 12.95s`

**Extra:** `test_create_session_technique_kind_rejected` plus the same formation/talisman files: `10 passed`. Full `tests/test_technique_craft.py`: `10 passed`.

## Files changed

| File | Action |
| --- | --- |
| `backend/app/db/models/technique_craft.py` | Created — `TechniqueResearchDraft` |
| `backend/app/db/models/__init__.py` | Modified — export new model for `create_all` |
| `backend/app/services/technique_craft_service.py` | Created — create / list / abandon |
| `backend/app/schemas/technique_craft.py` | Created — `TechniqueDraftPublic` |
| `backend/app/api/research.py` | Modified — technique draft routes |
| `backend/app/core/deps.py` | Modified — `get_technique_craft_service` |
| `backend/app/services/research_service.py` | Modified — technique `create_session` → 40201 |
| `backend/app/constants/technique_craft.py` | Modified — `DRAFT_PHASE_EMBEDDING` / `ABANDONED` |
| `backend/tests/test_technique_craft.py` | Modified — two drafts + old-session 40201 |
| `.superpowers/sdd/task-3-report.md` | This report |

Did not `git add -A`. Did not push. README/CHANGELOG left alone (working tree dirty; docs deferred to Task 9). Did not implement Task 4+.

## Self-review

- TDD: RED on missing service import, then ORM + service + routes, then GREEN. Extra 40201 test because dual-track create_session is easy to leave open.
- `create_draft` does not touch inventory. Abandon only flips `phase`; no refund path exists.
- `list_drafts` filters `phase != abandoned` so abandon reduces list length 2 → 1 as specified.
- Writes reuse `_prepare_research_write`. GET list only `require_character`.
- Reused `ERR_RESEARCH_SESSION` (40201) and `ERR_RESEARCH_OWNER` (40207). Did not invent new codes.
- `can_finalize` is hardcoded `false` until Task 6 has embed + conditions + affix.
- Production `create_all` picks up the table via `from app.db import models` in `main.py`.
- Did not implement embed / conditions / finalize / frontend.
- Did not migrate `test_research_technique_finalize.py` (Task 9).

## Concerns

1. `tests/test_research_technique_finalize.py` now fails two cases (`create_session(kind="technique")` is 40201 instead of the old R2 path). Expected; Task 9 rewrites those tests.
2. Old in-progress technique `research_sessions` rows (if any) can still be fetched/rerolled/finalized via the session APIs. Dual-track until Task 9 cleanup.
3. No HTTP-level pytest for the new routes; coverage is service-level plus PlayGate wiring by convention.
4. `_require_draft` 403-before-abandoned can leak that another character’s draft id exists (same as research sessions).
5. `can_finalize` is always false this task even if later fields were filled by hand in the DB.
