/** 前端视图模型：由后端 MessageOut 和 SSE 事件累积而成（不属于接口契约） */
import type { Cell, ChartSpec, EChartsOption } from './chart'
import type { MessageRole, MessageStatus } from './message'
import type { StepEvent } from './sse'

export interface StepView {
  key: StepEvent['key']
  label: string
  status: StepEvent['status']
  detail: string | null
}

export interface SqlAttempt {
  sql: string
  attempt: number
}

export interface ChatMessage {
  id: string
  role: MessageRole
  content: string
  status: MessageStatus
  createdAt: string
  steps: StepView[]
  /** 最终执行的 SQL（历史消息只有这个） */
  sql: string | null
  /** 本次流式过程中的每次 SQL 尝试 */
  attempts: SqlAttempt[]
  rowCount: number | null
  hasChart: boolean
  error: { code: string; message: string; retryable: boolean } | null
  elapsedMs: number | null
  /** 对应的用户问题，用于“重试” */
  question?: string
}

export interface ChartData {
  messageId: string
  spec: ChartSpec
  option: EChartsOption
  columns: string[]
  rows: Cell[][]
  sql: string | null
  truncated: boolean
}
