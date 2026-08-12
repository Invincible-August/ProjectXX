/**
 * 核验相关 DTO（对接 `/api/v1/verification/*`）。
 */

/** GET /verification/modes 返回的当前配置。 */
export interface VerificationModes {
  debug: boolean
  id_verify_mode: string
  sms_provider: string
  email_provider: string
  id_two_factor_provider: string
  id_real_person_provider: string
  /** 注册是否强制手机号 + 短信验证码 */
  register_require_phone: boolean
  /** 注册是否强制真实姓名 + 身份证 */
  register_require_real_name: boolean
  /** 注册是否弹窗校验邮箱验证码 */
  register_require_email_code: boolean
}

/** 确认发码 / 身份核验成功后的一次性票据。 */
export interface TicketData {
  ticket: string
}
