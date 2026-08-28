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

## Task 3: complete (commits 613977d..6fee389)

Draft table + create/list/abandon. Old technique `create_session` → 40201. Formation/talisman tests still green. Embed is Task 4.
