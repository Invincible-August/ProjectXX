/**
 * M7 L3 邮件 / 赠送 HTTP API。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type {
  GiftSendResult,
  MailClaimResult,
  MailItem,
  MailListPayload,
} from '../types/mail'

/** GET /mail */
export async function listMail(): Promise<ApiResponse<MailListPayload>> {
  try {
    const response = await http.get<ApiResponse<MailListPayload>>('/mail')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<MailListPayload>(error)
  }
}

/**
 * POST /mail — 无附件玩家信。
 */
export async function sendMail(body: {
  to_name?: string | null
  to_character_id?: number | null
  subject_zh?: string
  body_zh?: string
}): Promise<ApiResponse<{ message?: string; mail_id?: number }>> {
  try {
    const response = await http.post<
      ApiResponse<{ message?: string; mail_id?: number }>
    >('/mail', body)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/**
 * POST /mail/{id}/read
 */
export async function markMailRead(
  mailId: number,
): Promise<ApiResponse<{ mail?: MailItem }>> {
  try {
    const response = await http.post<ApiResponse<{ mail?: MailItem }>>(
      `/mail/${mailId}/read`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/**
 * POST /mail/{id}/claim
 */
export async function claimMail(
  mailId: number,
): Promise<ApiResponse<MailClaimResult>> {
  try {
    const response = await http.post<ApiResponse<MailClaimResult>>(
      `/mail/${mailId}/claim`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<MailClaimResult>(error)
  }
}

/**
 * POST /gifts
 */
export async function sendGift(body: {
  to_name?: string | null
  to_character_id?: number | null
  spirit_stones?: number
  items?: Array<{ item_id: string; quantity: number }>
  note_zh?: string | null
}): Promise<ApiResponse<GiftSendResult>> {
  try {
    const response = await http.post<ApiResponse<GiftSendResult>>('/gifts', body)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<GiftSendResult>(error)
  }
}
