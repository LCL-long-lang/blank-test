/** 对应 backend/app/common/schemas.py 的消息与问答模型 */
export type MessageRole = 'user' | 'assistant'
export type MessageStatus = 'streaming' | 'done' | 'error' | 'cancelled'

export interface MessageOut {
  id: string
  session_id: string
  role: MessageRole
  content: string
  sql: string | null
  status: MessageStatus
  error: string | null
  has_chart: boolean
  elapsed_ms: number | null
  created_at: string
}

export interface ChatRequest {
  session_id: string
  question: string
}
