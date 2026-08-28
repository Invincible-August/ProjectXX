# Task 8 Report: 前端研究室功法页

## Status

**DONE**

## Commits

- `73f6743` Rewrite lab technique page for card drafts and original cultivate.

## Summary

Rewrote the lab technique panel onto `/cave/lab/technique/*`. Multiple drafts, bag cards (use blank/type via existing `POST /inventory/use`), embed dropdown, two condition selects, affix pick-one-of-three / reroll, finalize. Finalized originals: three base-upgrade buttons, affix upgrade, breakthrough; hide “equip as main” hint for attack efficacies. Removed material multi-select and old session reroll. `research.ts.create({ kind: 'technique' })` now returns the backend 40201 copy.

Did not implement Task 9 (GM / docs). `cave.ts` isolation: dirty file copied to `.superpowers/sdd/cave.ts.wip`, HEAD restored, wrappers added, staged. After commit, wip restored and the same wrappers re-inserted; leftover dirty comment not committed.

## Test

**Command:** `cd frontend && npx vue-tsc -b --pretty false`

**Result:** exit 0

Browser E2E not run (no play server in this session; GM blank cards are Task 9).

## Files changed

| File | Action |
| --- | --- |
| `frontend/src/types/techniqueCraft.ts` | Created — DTOs, card ids, labels |
| `frontend/src/stores/techniqueCraft.ts` | Created — drafts + cultivate |
| `frontend/src/api/cave.ts` | Modified — technique-craft wrappers only |
| `frontend/src/components/research/TechniqueResearchPanel.vue` | Rewritten |
| `frontend/src/stores/research.ts` | Modified — reject technique `create` |
| `.superpowers/sdd/task-8-report.md` | This report |

Did not `git add -A`. Did not push. README/CHANGELOG left alone (Task 9).

## Self-review

- Inventory use API already existed; panel calls `inventoryStore.use`.
- Embed / affix-upgrade / breakthrough fail vs HTTP error distinguished by comparing draft/payload before and after 200.
- Draft name input is not wiped on embed/roll (watch draft id only).
- Formation / talisman still use `researchStore.create`.

## Concerns

1. `GET /cave/lab/mine` does not return base/affix slots; cultivate UI is complete after finalize (seeded from draft) or after the first cultivate POST. Picking an older original from mine shows zeros until a cultivate call returns payload.
2. Affix Chinese labels are a local map of YAML placeholders; unknown ids fall back to the id string.
3. `conditions_confirmed` is not on the draft DTO; the 确认 button is always available after both embeds.
