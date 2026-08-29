# SDD Progress Ledger

Plan: docs/superpowers/plans/2026-08-27-technique-research-p2.md
(P1 ledger kept below. Do not re-dispatch P1 tasks.)
Branch: feat/technique-research-p1

## P2 Task 1: complete (commits 2f98ff1..8c39607, review clean)

Review: spec yes, quality Approved.

Minors deferred to whole-branch review:
- test does not assert `item.bound is False`
- ERR_CRAFT_MANUAL / ERR_CRAFT_LEARN unused until later tasks
- `test_technique_craft_defaults_when_block_missing` not extended for print costs

⚠️ controller: focused catalog test + `tests/test_content_validator.py` 8 passed; formation/talisman full regression deferred to P2 Task 6.

## P2 Task 2: complete (commits 8c39607..aef01db, review clean)

Review: spec yes, quality Approved.

Minors deferred:
- martial/body print-cost path untested
- non-author/non-research both map to 「仅原创者可制成秘籍」
- return item_id is catalog id not item_uid
- HTTP print-manual route untested

⚠️ controller: body-cost and HTTP tests not required by this task's brief; Task 6 regression covers craft file (30 passed in implementer report).

## P2 Task 3: complete (commits aef01db..19aeeb1, review clean)

Review: spec yes, quality Approved.

Minors deferred:
- occupancy / quantity!=1 / bad-snapshot untested
- below-rank test does not assert message or no CharacterTechnique insert
- `_already_learned_origin` scans all private JSON in Python

⚠️ controller: list_my_techniques still hardcodes private `source=research` — that is Task 4. Formation/talisman suite deferred to Task 6.

## P2 Task 4: complete (commits 19aeeb1..08f7266, review clean)

Review: spec yes, quality Approved.

Minors deferred:
- no list_mine assertion
- source_label_zh not asserted

⚠️ controller: research_service.py left untouched per dirty-WIP; list_mine cultivable already false via author!=self.

## P2 Task 5: complete (commits 08f7266..2abe9a9, review clean)

Review: spec yes, quality Approved.

Minors deferred:
- no confirm dialog before spending print cost
- print API return type is Record<string, unknown>
- UI not click-tested in browser (controller may verify later)

⚠️ controller: vue-tsc claimed exit 0; browser path still unverified.

## P2 Task 6: complete (commits 2abe9a9..c786259, review clean)

Review: spec yes, quality Approved.

Minors deferred:
- P1/P2 plan markdown files still untracked (spec links them)
- pytest/vue-tsc evidence is implementer-reported (54 passed, vue-tsc 0)

## P2 whole-branch: complete (commits 2f98ff1..2b3919b)

Final review: With fixes. Fix wave `ac43b89` + live-use `2b3919b` (review Approved).

Fixes: unique tech_manual; list_mine chance; author id on hover; lab 「背包秘籍」使用.

Minors leftover:
- InventoryPanel 使用钮仍挂在未挂载组件
- 装备槽悬停无创作者 id
- 占用中秘籍按钮未禁用
- 印制无确认 / HTTP 印制未测 / 炼体印制费用未测
- P1/P2 plan md 仍可能 untracked
- 浏览器未点过印制/使用

Do not merge (user). P3/P4 not started.

---

# P1 (complete)

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

## Task 5: complete (commits fa48aea..0baab36, review clean)

Minors deferred:
- Illegal condition/slot paths untested; martial reroll untested; no HTTP tests
- `_draft_public` does not pad affix slots before first roll
- `weapon_allow`/`element_allow` not on AffixDef so weapon_limit does not shrink pool
- Changing conditions after roll does not reroll options
- `_affix_slot_count` hardcodes 1 if rank missing
- `conditions_confirmed` still missing — Task 6 must add it for finalize gate

## Task 6: complete (commits 0baab36..e2cc635, review clean)

Minors deferred:
- `can_finalize` DTO does not re-check affix-pool membership
- Missing-conditions / stale-affix 40222 untested; no HTTP finalize test
- CharacterTechnique.technique_id String(64) vs PrivateTechnique String(128)
- Duplicate _private_payload helpers; dead R2 body remains for Task 9
- GET drafts docstring omits finalized

## Task 7: complete (commits e2cc635..4829f61, review clean)

Minors deferred:
- Combat still multiplies custom stats by CharacterTechnique.level
- Over-cap 40223 not isolated from missing-rank 40223
- No HTTP cultivate tests; stat not an enum
- Weapon-limit bonus not in grants

## Task 8: complete (commits 4829f61..04788a2, review clean)

After fix: mine select hydrates affix_ids; idle-only main hint.

Minors deferred:
- Hard refresh still shows 0 base/upgrade_points until first cultivate POST
- First affix-upgrade after refresh can toast 成功 on a failed roll
- PrivateContentPublic type escape; unused ATTACK_EFFICACIES
- New-draft affixes shown as one empty column; loadDrafts errors swallowed

## Task 9: complete (commits 04788a2..2f98ff1, review clean)

Controller finished after implementer WIP (subagent channel down). GM grants 10 blank cards; 40201 leftover-session test; README/CHANGELOG/M8 one-liners; spec status P1 implemented.

Minors deferred:
- No dedicated GM blank-card quantity test
- Duplicate 40201 coverage in test_technique_craft.py
- Dead R2 bodies still in ResearchService after 40201 guards
- Historical README “M8 R2 已落地” bullet still describes old session API
- Commit message contains stray `EOF`

## Whole-branch

Subagent reviewer dispatch failed (proxy). Per-task reviews were Approved. P2–P4 not in this branch.

