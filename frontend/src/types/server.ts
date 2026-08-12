/**
 * 后端健康检查 `GET /health`（或 `/api/v1/health`）返回的 data 字段。
 */
export interface ServerHealth {
  /** 整体状态：ok / degraded */
  status: string
  /** 应用名称 */
  app: string
  /** 运行环境，如 development */
  env: string
  /** 数据库探测结果：ok / error */
  db: string
  /** UTC 时间戳字符串 */
  time: string
}
