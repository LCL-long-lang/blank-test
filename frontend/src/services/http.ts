import type { ApiResponse } from '../types'

/** 所有接口走相对路径，开发环境由 Vite 代理到后端 */
export const API_BASE = '/api'

export class ApiError extends Error {
  readonly code: string
  readonly status: number

  constructor(code: string, message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

/** 基于 fetch 的请求封装：统一解包 {code, message, data}，非 OK 时抛 ApiError */
export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let resp: Response
  try {
    resp = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init.headers },
    })
  } catch {
    throw new ApiError('NETWORK_ERROR', '无法连接后端服务', 0)
  }

  let body: ApiResponse<T> | null = null
  try {
    body = (await resp.json()) as ApiResponse<T>
  } catch {
    // 非 JSON 响应（如代理返回的 502 页面）
  }

  if (!resp.ok || !body || body.code !== 'OK') {
    throw new ApiError(
      body?.code ?? `HTTP_${resp.status}`,
      body?.message ?? resp.statusText ?? '请求失败',
      resp.status,
    )
  }
  return body.data as T
}

export const http = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, data?: unknown) =>
    request<T>(path, { method: 'POST', body: data === undefined ? undefined : JSON.stringify(data) }),
  patch: <T>(path: string, data: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(data) }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}
