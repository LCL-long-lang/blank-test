/** SSE 事件契约，对应 backend/app/common/schemas.py 中的 SSE_EVENT_MODELS */
import type { Cell, ChartSpec, EChartsOption } from './chart'

export type StepKey =
  | 'rewrite'
  | 'intent'
  | 'schema'
  | 'generate_sql'
  | 'execute'
  | 'chart'
  | 'insight'

export interface StartEvent {
  message_id: string
  user_message_id: string
}

export interface StepEvent {
  key: StepKey
  status: 'running' | 'done' | 'error'
  label: string
  detail: string | null
}

export interface SqlEvent {
  sql: string
  attempt: number
}

export interface DataEvent {
  columns: string[]
  rows: Cell[][]
  total: number
  truncated: boolean
}

export interface ChartEvent {
  spec: ChartSpec
  option: EChartsOption
}

export interface TextEvent {
  delta: string
}

export interface TitleEvent {
  session_id: string
  title: string
}

export interface ErrorEvent {
  code: string
  message: string
  retryable: boolean
}

export interface DoneEvent {
  message_id: string
  elapsed_ms: number
}

/** event 名 → data 结构 */
export interface SSEEventMap {
  start: StartEvent
  step: StepEvent
  sql: SqlEvent
  data: DataEvent
  chart: ChartEvent
  text: TextEvent
  title: TitleEvent
  error: ErrorEvent
  done: DoneEvent
}

/** 可辨识联合：switch (e.event) 时 e.data 自动收窄 */
export type SSEEvent = {
  [K in keyof SSEEventMap]: { event: K; data: SSEEventMap[K] }
}[keyof SSEEventMap]
