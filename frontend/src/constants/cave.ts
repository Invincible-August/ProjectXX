/**
 * Cave (洞府) page paths. Workshop / lab are secondary rooms.
 */
export const CAVE_PATH = '/cave'
export const CAVE_WORKSHOP_PATH = '/cave/workshop'
export const CAVE_LAB_PATH = '/cave/lab'

/** Hub room id → nested path (align with backend CAVE_ROOMS). */
export const CAVE_ROOM_PATHS: Readonly<Record<string, string>> = {
  workshop: CAVE_WORKSHOP_PATH,
  lab: CAVE_LAB_PATH,
}
