/**
 * M4 背包 API。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type { BagKind, InventoryBagsPayload, InventoryItem } from '../types/inventory'

/** GET /inventory */
export async function fetchInventory(): Promise<ApiResponse<InventoryBagsPayload>> {
  try {
    const response = await http.get<ApiResponse<InventoryBagsPayload>>('/inventory')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<InventoryBagsPayload>(error)
  }
}

/** POST /inventory/move-bag */
export async function moveInventoryBag(body: {
  item_uid: string
  target_bag: BagKind
}): Promise<ApiResponse<InventoryBagsPayload & { moved?: boolean; message?: string }>> {
  try {
    const response = await http.post<
      ApiResponse<InventoryBagsPayload & { moved?: boolean; message?: string }>
    >('/inventory/move-bag', body)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /inventory/use（可选） */
export async function useItem(body: {
  item_uid: string
  quantity?: number
}): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>(
      '/inventory/use',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<Record<string, unknown>>(error)
  }
}

export type { InventoryItem }
