/**
 * Cave (洞府) DTO — align with backend app.schemas.cave.
 */
export interface CaveRoomPublic {
  id: string
  label_zh: string
  summary_zh: string
}

export interface CaveOverviewPublic {
  label_zh: string
  rooms: CaveRoomPublic[]
}
