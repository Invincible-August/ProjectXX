# Task 7 Report: 原创培养（基础加成、词条升级、突破）

## Status

**DONE**

## Commits

- `86baa84` Add original-technique cultivate APIs for base, affix, and rank.

## Summary

Cultivate APIs write `PrivateTechnique.payload_json` (not the draft). Only `author_character_id == character.id` and `CharacterTechnique.source=research` may cultivate. Base clicks use whole-technique cost index; affix fail still charges; breakthrough fail deducts only `breakthrough_cost_*` and keeps points/rank; success raises `major_rank` and pads affix slots. List/combat grants map base attack/defense/speed by SPELL/MARTIAL efficacy and scale affix stats by YAML `affix_level_mult`. Did not implement Task 8 UI.

## What was implemented

- Domain: `upgrade_points_for_base_level`, `rank_cap`, `can_breakthrough` (realms.yaml `next_major` height), `payload_attr_grants`, failable rolls.
- YAML/parser: `affix_level_mult: 0.2`, `base_stat_per_click: 1`.
- `upgrade_base` / `upgrade_affix` / `breakthrough` on `TechniqueCraftService`.
- `POST /cave/lab/technique/techniques/{id}/base-upgrade|affix-upgrade|breakthrough`.
- `TechniqueService.list_my_techniques` and `ResearchService._private_public` recompute ATTR from payload.

## TDD Evidence

### RED (Step 1)

**Command:** `pytest tests/test_technique_craft.py -k "two_attack or breakthrough_fail or breakthrough_success or affix_upgrade_fail" -q`

**Result:** FAIL as expected (`upgrade_base` / `breakthrough` / `upgrade_affix` missing). `4 failed, 23 deselected`.

### GREEN (Step 2)

**Command (brief):** `pytest tests/test_technique_craft.py -q`

**Result:** PASS — `27 passed in 36.24s`

**Extra:** `test_technique_craft.py` + `test_research_technique_finalize.py` + `test_content_validator.py` + `test_technique_loadout.py`: `38 passed`.

## Files changed

| File | Action |
| --- | --- |
| `backend/app/config_data/research.yaml` | Modified — affix_level_mult / base_stat_per_click |
| `backend/app/services/realm_config.py` | Modified — parse new keys |
| `backend/app/domain/technique_craft.py` | Modified — cultivate pure functions |
| `backend/app/services/technique_craft_service.py` | Modified — upgrade_base / upgrade_affix / breakthrough |
| `backend/app/services/technique_service.py` | Modified — list grants from payload |
| `backend/app/services/research_service.py` | Modified — list_mine stats from payload |
| `backend/app/schemas/technique_craft.py` | Modified — request bodies |
| `backend/app/api/research.py` | Modified — three cultivate routes |
| `backend/tests/test_technique_craft.py` | Modified — four named cases |
| `.superpowers/sdd/task-7-report.md` | This report |

Did not `git add -A`. Did not push. README/CHANGELOG left alone (docs deferred to Task 9). Did not implement Task 8 UI.

## Self-review

- TDD: RED on missing methods, then YAML/parser/domain/service/routes/grants, then GREEN.
- ATTR formula reads `craft.affix_level_mult`; 0.2 is not hardcoded in the grant branch.
- Breakthrough next-rank uses `realms.yaml` `next_major`, not iterating rank keys.
- Writes reuse `_prepare_research_write`.

## Concerns

1. No HTTP-level pytest for the three cultivate routes.
2. `rank_cap` is implemented but cultivate gates go through `can_breakthrough` (same height rule).
3. After `qi_refining`, next realm `foundation` is not in `technique_craft.ranks` → 40223 (expected until more ranks are configured).
4. Weapon-limit bonus is not folded into list/combat grants (spec: combat-time, not this task).
5. Base upgrade has no fail roll (spec only fails affix/breakthrough/embed).
