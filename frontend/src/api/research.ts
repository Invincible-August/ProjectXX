/**
 * Compat re-export: lab HTTP lives in `api/cave.ts` (`/cave/lab/*`).
 */
export {
  createResearchSessionApi,
  fetchOpenResearchSessionsApi,
  fetchResearchCatalogApi,
  fetchResearchMineApi,
  fetchResearchSessionApi,
  finalizeResearchSessionApi,
  rerollResearchSessionApi,
  saveResearchDraftApi,
  submitResearchReviewApi,
} from './cave'
