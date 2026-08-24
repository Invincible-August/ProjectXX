/**
 * 玩家账号页 DTO。
 */
export interface AccountSummary {
  fate_luck: number
  total_recharge_amount: number
  ad_watch_count: number
}

export interface AccountTipItem {
  id: number
  paid_at: string | null
  amount: number
  order_no: string
  channel: string
}

export interface AccountTipList {
  items: AccountTipItem[]
  total: number
  page: number
  page_size: number
}
