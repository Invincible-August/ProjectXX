# Task 1 review-fix report

## Status

**DONE_WITH_CONCERNS**

## What you implemented

Review (spec+quality) on `e62ccb5..1ed6f5a` failed because `validate_content.py` imported `TALISMAN_KINDS` that is not in committed `research.py`, and tests asserted YAML rows/fields not in that commit.

This fix **strips** the incomplete talisman-kind checks. It does **not** add `TALISMAN_KINDS` to constants.

- `backend/app/config_source/validate_content.py`
  - Import `TALISMAN_TRIGGERS` only (drop `TALISMAN_KINDS`).
  - Keep `AFFIX_ROLES` / `EFFICACY_IDS` and `validate_technique_craft` (still called from `validate_loaded_bundle`).
  - `validate_talisman_effects_raw` and `validate_loaded_bundle`: label_zh + trigger whitelist only.
- `backend/tests/test_content_validator.py`
  - `test_current_yaml_samples_pass_validator`: BASE assertions only (`iron_sword_t1`, `first_hit_ward`, `phys_edge`, `sample_main_affix_iron`).
  - `test_talisman_effects_require_label_and_trigger`: label + trigger only; no `kind` cases.
  - Kept `test_technique_craft_rejects_illegal_affix_and_rank`.

## What you tested and test results

**Required** (cwd `backend`):

```
python -m pytest tests/test_technique_craft.py tests/test_content_validator.py -q
```

**Result:** PASS — `11 passed in 1.87s`

**Optional extra** (brief named `tests/test_research.py tests/test_research_technique_finalize.py`):

- `tests/test_research.py` does not exist (pytest exit 4, no tests ran).
- Closest existing files: `test_research_technique_finalize.py`, `test_research_formation_blueprint.py`, `test_research_talisman_whitelist.py`.

```
python -m pytest tests/test_research_technique_finalize.py tests/test_research_formation_blueprint.py tests/test_research_talisman_whitelist.py -q
```

**Result:** `1 failed, 10 passed in 20.66s`

Failure: `test_research_technique_finalize` — `assert tech_row is not None` in `CharacterService.build_combat_attrs` technique breakdown. That path does not import this validator. Working tree is dirty with unrelated character/cave/craft/talisman edits; this failure is **not** attributed to the kind-check revert. Did not touch those files.

## TDD Evidence

Review fix: GREEN after the revert is enough.

- Pre-fix: committed validator imported `TALISMAN_KINDS` (not in committed `research.py`).
- Post-fix: `git show HEAD:backend/app/constants/research.py` has `TALISMAN_TRIGGERS` only; validator no longer references `TALISMAN_KINDS`.
- Required suite GREEN: 11 passed.

## Files changed

| File | Action |
| --- | --- |
| `backend/app/config_source/validate_content.py` | Modified — drop `TALISMAN_KINDS` import and kind checks; keep technique_craft |
| `backend/tests/test_content_validator.py` | Modified — restore BASE YAML/talisman assertions; keep technique_craft test |
| `.superpowers/sdd/task-1-fix-report.md` | Created — this report |

Staged **only** these three files. Did not `git add -A`. Did not change dirty `constants/research.py` or YAML.

## Self-review findings

- Validator import surface matches BASE for talisman (`TALISMAN_TRIGGERS` only) plus Task 1 `technique_craft` imports.
- No `kind not in TALISMAN_KINDS` remains in the two allowed files.
- Tests no longer mention `cloth_cap_t1`, `curse_weaken_atk`, `talisman_effect_id`, or kind success/fail cases.
- `validate_technique_craft` still enforces efficacy ⊆ `EFFICACY_IDS`, role ∈ `AFFIX_ROLES`, ranks vs `realms.yaml`.
- Did not add `TALISMAN_KINDS` to committed constants.
- Did not implement Task 2+.
- Did not push.

## Concerns

1. Optional extra research tests: `test_research.py` missing; `test_research_technique_finalize` failed on the dirty tree in combat-attr packing, unrelated to this revert. Required Task 1 tests passed.
2. Required tests were run with a dirty working tree. Assertions now only require rows present at `1ed6f5a`, and the validator no longer needs unstaged `TALISMAN_KINDS`, so a clean checkout of this commit should import. Dirty YAML/constants were not staged.
3. Uncommitted `TALISMAN_KINDS` remains in working-tree `backend/app/constants/research.py` for later work; it is not part of this commit.

## Commits

Recorded after `git commit` (see git log on `feat/technique-research-p1`).
