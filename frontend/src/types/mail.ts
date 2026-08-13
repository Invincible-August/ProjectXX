/**
 * M7 L3 邮件领域类型（附物发信并入邮件）。
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
  can_delete: boolean
  created_at: string | null
  expires_at: string | null
}

/** 限额提示 */
export interface MailLimits {
  max_attachment_lines: number
  max_attachment_spirit_stones: number
  max_body_len: number
  broadcast_max_recipients: number
  sect_broadcast_min_rank_order: number
}

/** GET /mail */
export interface MailListPayload {
  items: MailItem[]
  unread: number
  limits?: MailLimits
}

/** 写信快捷目标 */
export interface MailComposeTarget {
  character_id: number
  name: string
  rank?: string
  rank_label_zh?: string
  bond_id?: number
}

/** GET /mail/compose-options */
export interface MailComposeOptions {
  friends: MailComposeTarget[]
  sect_members: MailComposeTarget[]
  disciples: MailComposeTarget[]
  can_sect_broadcast: boolean
  can_disciple_broadcast: boolean
  my_sect_rank?: string | null
  my_sect_rank_label_zh?: string | null
  limits: MailLimits
}

/** POST /mail/{id}/claim */
export interface MailClaimResult {
  message?: string
  claimed?: MailAttachments
  mail?: MailItem
  character?: Record<string, unknown>
}

/** POST /mail 发送结果 */
export interface MailSendResult {
  message?: string
  mail_id?: number | null
  mail_ids?: number[]
  recipient_count?: number
  character?: Record<string, unknown>
}

/** 兼容旧赠送结果 */
export interface GiftSendResult extends MailSendResult {
  spirit_value?: number
}
