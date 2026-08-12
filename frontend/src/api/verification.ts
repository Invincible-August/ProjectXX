/**
 * 核验 API 封装：短信 / 邮件发码与确认、身份证提交、模式查询。
 * 对应后端 `{API_PREFIX}/verification/*`。
 */
import { http } from './http'
import type { ApiResponse } from '../types/api'
import type { TicketData, VerificationModes } from '../types/verification'

/**
 * 查询当前核验模式（是否 DEBUG、身份证校验级别等）。
 */
export async function fetchVerificationModesApi(): Promise<
  ApiResponse<VerificationModes>
> {
  const response = await http.get<ApiResponse<VerificationModes>>(
    '/verification/modes',
  )
  return response.data
}

/**
 * 向手机号发送短信验证码。
 *
 * @param phone - 大陆 11 位手机号
 */
export async function sendSmsCodeApi(
  phone: string,
): Promise<ApiResponse<null>> {
  const response = await http.post<ApiResponse<null>>('/verification/sms/send', {
    phone,
  })
  return response.data
}

/**
 * 校验短信验证码并换取 sms_ticket。
 *
 * @param phone - 手机号
 * @param code - 验证码（DEBUG 默认 000000）
 */
export async function confirmSmsCodeApi(
  phone: string,
  code: string,
): Promise<ApiResponse<TicketData>> {
  const response = await http.post<ApiResponse<TicketData>>(
    '/verification/sms/confirm',
    { phone, code },
  )
  return response.data
}

/**
 * 向邮箱发送验证码。
 *
 * @param email - 邮箱地址
 */
export async function sendEmailCodeApi(
  email: string,
): Promise<ApiResponse<null>> {
  const response = await http.post<ApiResponse<null>>(
    '/verification/email/send',
    { email },
  )
  return response.data
}

/**
 * 校验邮箱验证码并换取 email_ticket。
 *
 * @param email - 邮箱
 * @param code - 验证码
 */
export async function confirmEmailCodeApi(
  email: string,
  code: string,
): Promise<ApiResponse<TicketData>> {
  const response = await http.post<ApiResponse<TicketData>>(
    '/verification/email/confirm',
    { email, code },
  )
  return response.data
}

/**
 * 提交实名 + 身份证，换取 id_ticket。
 *
 * @param realName - 真实姓名
 * @param idCard - 身份证号
 */
export async function submitIdVerifyApi(
  realName: string,
  idCard: string,
): Promise<ApiResponse<TicketData>> {
  const response = await http.post<ApiResponse<TicketData>>(
    '/verification/id/submit',
    { real_name: realName, id_card: idCard },
  )
  return response.data
}
