/**
 * M7 L3 邮件 / 赠送领域类型。
 */

/** 邮件附件 */
export interface MailAttachments {
  spirit_stones: number
  items: Array<{ item_id: string; quantity: number }>
}

/** 收件箱条目 */
export interface MailItem {
  id: number
  mail_kind: string
  mail_kind_label_zh: string
  reason: string
  subject_zh: string
  body_zh: string
  from_character_id: number | null
  from_name: string
  attachments: MailAttachments
  has_attachments: boolean
  is_read: boolean
  is_claimed: boolean
  can_claim: boolean
  created_at: string | null
  expires_at: string | null
}

/** GET /mail */
export interface MailListPayload {
  items: MailItem[]
  unread: number
}

/** POST /mail/{id}/claim */
export interface MailClaimResult {
  message?: string
  claimed?: MailAttachments
  mail?: MailItem
  character?: Record<string, unknown>
}

/** POST /gifts */
export interface GiftSendResult {
  message?: string
  mail_id?: number
  spirit_value?: number
  character?: Record<string, unknown>
}
