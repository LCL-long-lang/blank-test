/** 后端统一响应格式，对应 backend/app/common/response.py */
export interface ApiResponse<T> {
  code: string
  message: string
  data: T | null
}

export interface HealthOut {
  status: 'ok'
  version: string
  business_db: boolean
  app_db: boolean
  llm_configured: boolean
}
