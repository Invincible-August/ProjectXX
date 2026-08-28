# Task 4 Report: 镶嵌正式卡（可失败）

## Status

**DONE**

## Commits

- Add fail-able embed of formal technique cards onto drafts.

## Summary

Added `roll_embed_success`, `TechniqueCraftService.embed_card`, and `POST /cave/lab/technique/drafts/{id}/embed`. Formal element/efficacy cards can be embedded into an owned draft. Validation errors do not consume the card; after validation the card is always `remove_one_by_uid`, then the YAML `embed_fail_rate` roll either writes+locks the slot or leaves other draft fields unchanged.

Did not implement conditions, affix roll, finalize, or frontend.

## What was implemented

- `roll_embed_success(fail_rate)`: uniform `[0,1)` draw `< fail_rate` fails; rate `<=0` always succeeds, `>=1` always fails.
- Element card: draft `elements` must still be empty; success writes `elements_json` (that is the lock).
- Efficacy card: `efficacy` must still be empty; success writes `efficacy`.
- Errors: not owner `40207` (`ERR_RESEARCH_OWNER` via `_require_draft`); wrong card type / empty formal meta `40220` (`ERR_CRAFT_CARD`); slot already filled `40221` (`ERR_CRAFT_EMBED`). No new codes.
- Route uses `_prepare_research_write`. Body `{ "item_uid": "..." }`. Response is the public draft payload.

## TDD Evidence

### RED (Step 1)

**Command:**

```powershell
cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_technique_craft.py -k "embed_fail_consumes or embed_success_locks or embed_second_element" -q
```

**Result:** FAIL as expected (`embed_card` missing).

```
AttributeError: 'TechniqueCraftService' object has no attribute 'embed_card'
3 failed, 11 deselected in 6.83s
```

### GREEN (Step 2)

**Command (brief):**

```powershell
cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_technique_craft.py -k embed -q
```

**Result:** PASS — `3 passed, 11 deselected in 6.65s`

**Extra:** full `tests/test_technique_craft.py`: `14 passed in 20.39s`

## Files changed

| File | Action |
| --- | --- |
| `backend/app/domain/technique_craft.py` | Modified — `roll_embed_success` |
| `backend/app/services/technique_craft_service.py` | Modified — `embed_card` |
| `backend/app/schemas/technique_craft.py` | Modified — `TechniqueEmbedRequest` |
| `backend/app/api/research.py` | Modified — `POST .../drafts/{id}/embed` |
| `backend/tests/test_technique_craft.py` | Modified — three brief embed tests |
| `.superpowers/sdd/task-4-report.md` | This report |

Did not `git add -A`. Did not push. README/CHANGELOG left alone (docs deferred to Task 9). Did not implement Task 5+.

## Self-review

- TDD: RED on missing `embed_card`, then domain + service + route, then GREEN.
- Slot lock is “field already filled”; second card of that kind is `40221` and is not deducted.
- Fail path consumes the card and leaves `elements` / `efficacy` / other columns as they were.
- Tests monkeypatch `technique_craft_service.roll_embed_success` True/False (`raising=False` so RED could patch before the symbol existed).
- Reused `ERR_RESEARCH_OWNER` (40207), `ERR_CRAFT_CARD` (40220), `ERR_CRAFT_EMBED` (40221).
- Writes reuse `_prepare_research_write`.

## Concerns

1. Named tests only cover element cards. Efficacy write/lock is implemented but not in the three brief tests.
2. 40207 / 40220 have no new embed-specific pytest (40207 is existing `_require_draft`; 40220 is wrong type / empty meta).
3. No HTTP-level pytest for the new route; coverage is service-level plus PlayGate wiring by convention.
4. Formal card with missing `elements`/`efficacy` meta is treated as 40220 and is not consumed.
5. Peek-then-`remove_one_by_uid` is same-session; qty-0 rows raise 40000 before deduct (inventory would use 40055).
