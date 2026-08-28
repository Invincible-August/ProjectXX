# Task 1 Report: 协议常量、YAML、解析、灵根映射

## Status

**DONE**

## Commits

- `ffe36dc` Add technique-craft protocol constants, YAML parse, and content checks.

## Summary

Added technique-craft protocol constants, `research.yaml` `technique_craft` placeholders, `ResearchConfig.technique_craft` parsing, and content-validator checks. No inventory cards, drafts, APIs, or frontend.

## Files Changed

| File | Action |
| --- | --- |
| `backend/app/constants/technique_craft.py` | Created — efficacies, card ids, error codes, spirit-root → element map |
| `backend/app/config_data/research.yaml` | Modified — `technique_craft:` block beside existing `technique:` |
| `backend/app/services/realm_config.py` | Modified — `TechniqueCraftConfig` / rank / affix dataclasses; `_parse_technique_craft` |
| `backend/app/config_source/validate_content.py` | Modified — `validate_technique_craft` (efficacy ⊆ `EFFICACY_IDS`, role whitelist, rank ids vs `realms.yaml`) |
| `backend/tests/test_technique_craft.py` | Created — mixed/metal root mapping + config load + missing-block defaults |
| `backend/tests/test_content_validator.py` | Modified — illegal efficacy / role / rank unit test |

## Protocol Surface

- `EFFICACY_IDS = ("spell_attack", "spell_buff", "martial_attack", "martial_buff", "idle_spirit", "idle_body")`
- `element_ids_from_spirit_root_tags` expands `mixed_root` → five elements; `metal_root` → `["metal"]`
- Error codes `40220`–`40224`; card ids `tech_card_*`; `WEAPON_LIMITS`
- Extra vs brief dump: `AFFIX_ROLES = {attack, buff, idle, defense}` so the validator is not a magic set

## TDD

### RED (Step 2)

**Command:**

```powershell
cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_technique_craft.py::test_mixed_root_expands_to_five_elements tests/test_technique_craft.py::test_technique_craft_config_loads -v
```

**Result:** FAIL as expected.

```
ImportError while importing test module '.../tests/test_technique_craft.py'
E   ModuleNotFoundError: No module named 'app.constants.technique_craft'
collected 0 items / 1 error
```

### GREEN (Step 7)

**Command:**

```powershell
cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_technique_craft.py::test_mixed_root_expands_to_five_elements tests/test_technique_craft.py::test_metal_root_only_metal tests/test_technique_craft.py::test_technique_craft_config_loads tests/test_content_validator.py -q
```

**Result:** PASS — `10 passed in 1.88s`

(3 brief tests + 1 missing-block default + 6 content-validator tests including the new reject case.)

### Extra regression

```powershell
cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_technique_craft.py tests/test_content_validator.py tests/test_research_formation_blueprint.py tests/test_research_talisman_whitelist.py -q
```

**Result:** PASS — `19 passed in 17.09s` (formation / talisman research unchanged).

## Self-review

- Followed existing `_parse_research` / frozen dataclass patterns; did not restructure `realm_config.py`.
- Affix `stats` go through `assert_attr_stats` at parse time; validator re-asserts stats, `efficacy_allow`, `role`, and rank ids against `bundle.realms`.
- Missing `technique_craft` uses YAML-matching placeholders so overlay/old fixtures do not crash.
- Did not rewrite `test_research_technique_finalize.py`.
- Did not implement inventory cards, drafts, APIs, or frontend.
- Skipped README/CHANGELOG (Task 9).

## Concerns

- Parser default numbers duplicate YAML placeholders (required by brief: empty block must still load).
- `ranks` YAML currently only lists `body_tempering` and `qi_refining`; higher majors are valid ids but have no craft rank row until later content fill.
- `AFFIX_ROLES` was not in the brief constants dump; added for the validator role check.

## Out of Scope (Not Done)

- Inventory card items / `UseEffectKind`
- Drafts, `TechniqueCraftService`, HTTP, frontend
- Rewrite of R2 technique finalize tests (Task 6+)
