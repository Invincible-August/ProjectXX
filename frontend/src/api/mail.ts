/**
 * M7 L3 邮件 HTTP API（附物发信并入邮件）。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type {
  MailClaimResult,
  MailComposeOptions,
  MailItem,
  MailListPayload,
  MailSendResult,
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

/** GET /mail/compose-options */
export async function fetchMailComposeOptions(): Promise<
  ApiResponse<MailComposeOptions>
> {
  try {
    const response = await http.get<ApiResponse<MailComposeOptions>>(
      '/mail/compose-options',
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<MailComposeOptions>(error)
  }
}

/**
 * POST /mail — 玩家信（可附物 / 群发）。
 */
export async function sendMail(body: {
  to_name?: string | null
  to_character_id?: number | null
  subject_zh?: string
  body_zh?: string
  spirit_stones?: number
  items?: Array<{ item_id: string; quantity: number }>
  broadcast?: 'sect' | 'disciples' | null
}): Promise<ApiResponse<MailSendResult>> {
  try {
    const response = await http.post<ApiResponse<MailSendResult>>('/mail', body)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<MailSendResult>(error)
  }
}

/** POST /mail/{id}/read */
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

/** POST /mail/read-all */
export async function markMailReadAll(): Promise<
  ApiResponse<{ message?: string; marked?: number; unread?: number }>
> {
  try {
    const response = await http.post<
      ApiResponse<{ message?: string; marked?: number; unread?: number }>
    >('/mail/read-all')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /mail/{id}/claim */
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

/** POST /mail/claim-all */
export async function claimMailAll(): Promise<
  ApiResponse<{
    message?: string
    claimed_count?: number
    unread?: number
    character?: Record<string, unknown>
  }>
> {
  try {
    const response = await http.post<
      ApiResponse<{
        message?: string
        claimed_count?: number
        unread?: number
        character?: Record<string, unknown>
      }>
    >('/mail/claim-all')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /mail/{id}/delete */
export async function deleteMail(
  mailId: number,
): Promise<ApiResponse<{ message?: string; deleted?: number; unread?: number }>> {
  try {
    const response = await http.post<
      ApiResponse<{ message?: string; deleted?: number; unread?: number }>
    >(`/mail/${mailId}/delete`)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /mail/delete-all */
export async function deleteMailAll(): Promise<
  ApiResponse<{ message?: string; deleted?: number; unread?: number }>
> {
  try {
    const response = await http.post<
      ApiResponse<{ message?: string; deleted?: number; unread?: number }>
    >('/mail/delete-all')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}
