/**
 * M7 L8 商业化 HTTP API。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type { CommerceMePayload, CommerceShopPayload } from '../types/commerce'

export async function fetchCommerceMe(): Promise<ApiResponse<CommerceMePayload>> {
  try {
    const response = await http.get<ApiResponse<CommerceMePayload>>('/commerce/me')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<CommerceMePayload>(error)
  }
}

export async function fetchCommerceShop(): Promise<ApiResponse<CommerceShopPayload>> {
  try {
    const response = await http.get<ApiResponse<CommerceShopPayload>>('/commerce/shop')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<CommerceShopPayload>(error)
  }
}

export async function activateMembership(
  tier: string,
): Promise<ApiResponse<{ membership?: unknown; message?: string; tiandao_points?: number }>> {
  try {
    const response = await http.post('/commerce/membership', { tier })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

export async function buyCommerceItem(
  itemId: string,
): Promise<ApiResponse<{ message?: string; tiandao_points?: number }>> {
  try {
    const response = await http.post('/commerce/shop/buy', { item_id: itemId })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

export async function sandboxGrantTiandao(
  amount: number,
): Promise<ApiResponse<{ tiandao_points?: number; granted?: number; message?: string }>> {
  try {
    const response = await http.post('/commerce/sandbox/grant-tiandao', { amount })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}
