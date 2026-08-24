/**
 * 玩家账号页：摘要与打赏账单。
 */
import { http } from './http'
import type { ApiResponse } from '../types/api'
import type { AccountSummary, AccountTipList } from '../types/account'

/**
 * 仙缘余额、累计打赏、累计观看广告次数。
 */
export async function fetchAccountSummaryApi(): Promise<ApiResponse<AccountSummary>> {
  const response = await http.get<ApiResponse<AccountSummary>>('/account/summary')
  return response.data
}

/**
 * 打赏记录账单。
 *
 * @param page - 页码
 * @param pageSize - 每页条数
 */
export async function fetchAccountTipsApi(
  page = 1,
  pageSize = 20,
): Promise<ApiResponse<AccountTipList>> {
  const response = await http.get<ApiResponse<AccountTipList>>('/account/tips', {
    params: { page, page_size: pageSize },
  })
  return response.data
}
