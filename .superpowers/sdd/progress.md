# SDD Progress Ledger

Plan: docs/superpowers/plans/2026-08-27-technique-research-p1.md
Branch: feat/technique-research-p1

## Task 1: complete (commits e62ccb5..ef80509, review clean)

Review: spec yes, quality Approved after two fixes (strip TALISMAN_KINDS import; strip InventoryItemDef.talisman_effect_id).

Minors deferred to whole-branch review:
- `_parse_int_tuple`: empty list `[]` becomes `()` instead of default
- `weapon_bonus` stats asserted only in validator, not at parse
- Parser placeholder weights/affixes use string literals not EFFICACY_IDS constants
- `task-1-fix2-report.md` recorded SHA `d468cf6` but commit is `ef80509`

## Task 2: complete (commits ef80509..613977d, review clean)

Minors deferred:
- Efficacy type → formal untested
- `roll_efficacy` silent fallback if rng has no `choices`
- empty dict `meta={}` vs `meta is not None` stacking mismatch
- `_prepare_researcher` imported from another test module
- No test that formal cards refuse `use_item`

## Task 3: complete (commits 613977d..917f6c9, review clean)

After fix: leftover technique reroll/finalize → 40201; list_open_sessions omits technique rows.

Minors deferred:
- Dead R2 finalize/reroll bodies remain until Task 9
- get_session still returns leftover technique row by id
- get_catalog still advertises technique open
- No HTTP-level draft tests
- ORM defaults use string literals instead of DRAFT_PHASE_*
- test_create_two_drafts_independent does not assert inventory/major_rank
- README/CHANGELOG one-liner deferred to Task 9

## Task 4: complete (commits 917f6c9..fa48aea, review clean)

Minors deferred:
- Efficacy embed path untested
- 40207/40220 embed cases untested
- No HTTP-level embed tests
- Peek qty=0 uses 40000 vs remove_one_by_uid 40055
- Uses InventoryService._parse_row_meta private helper

## Task 5: complete
