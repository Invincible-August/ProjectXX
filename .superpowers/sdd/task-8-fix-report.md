# Task 8 review-fix report

## Status

**DONE**

## What you implemented

Review of `4829f61..f396cd3` flagged two frontend bugs in the lab technique cultivate UI.

1. **Mine re-select wiped cultivate state.** `selectOriginalFromMine` zeroed `base` / `upgrade_points` and built empty affix slots, so affix-upgrade stayed disabled after refresh. Same-session after finalize worked only while the current original stayed selected.

   - Map `GET /cave/lab/mine` `affix_ids` into slots with `chosen_id` so upgrade is clickable without a new GET.
   - Cache last cultivate payload (`base`, `affixes`, `upgrade_points`, `major_rank`) keyed by `technique_id`. Switching away and back restores hydrate.
   - Finalize and successful cultivate POSTs write the cache. 40223 / missing payload does not merge, so cached slots stay.

2. **Equip-as-main hint.** Spec: only `idle_spirit` / `idle_body` can be main. Hint now shows for those two only (hidden for attack **and** buff).

Did not add a backend GET. Did not implement Task 9.

## What you tested and test results

**Required** (cwd `frontend`):

```
npx vue-tsc -b --pretty false
```

**Result:** exit 0 (no output, ~19s)

Browser E2E not run (no play server in this session).

## Files changed

| File | Action |
| --- | --- |
| `frontend/src/types/techniqueCraft.ts` | Modified — `IDLE_EFFICACIES`, `affix_ids` on mine DTO, `affixSlotsFromIds` |
| `frontend/src/stores/techniqueCraft.ts` | Modified — mine hydrate + cultivate cache; empty 40223 payload keeps slots |
| `frontend/src/components/research/TechniqueResearchPanel.vue` | Modified — idle-only main-equip hint |
| `.superpowers/sdd/task-8-fix-report.md` | Created — this report |

Staged **only** these files. Did not `git add -A`. Did not push. Did not touch `cave.ts`.

## Self-review findings

- Mine already returns `affix_ids`; no new backend endpoint.
- Cache is session-memory only: after a full page refresh, levels/upgrade_points show 0 until the first successful cultivate POST, but affix-upgrade is enabled from `affix_ids`.
- `mergeCultivate` keeps previous affixes/base when the POST returns an empty payload (40223 cap/breakthrough).

## Concerns

1. Refresh still cannot show true `chosen_level` / `upgrade_points` / `base` until a cultivate POST hydrates; mine list has no those fields.
2. `ATTACK_EFFICACIES` remains exported but unused by the panel (hint now uses `IDLE_EFFICACIES`).

## Commits

- `04788a2` Fix Task 8: hydrate original cultivate state from mine list.
