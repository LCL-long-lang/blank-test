import { EventStreamContentType, fetchEventSource } from '@microsoft/fetch-event-source'
import type { SSEEvent, SSEEventMap } from '../types'
import { API_BASE, ApiError } from './http'

export interface StreamHandlers {
  onEvent: (e: SSEEvent) => void
  signal: AbortSignal
}

/** 流式问答：POST /api/chat/stream。resolve 表示流正常结束；中途失败 reject ApiError；被 abort 时 resolve */
export type StreamChat = (sessionId: string, question: string, h: StreamHandlers) => Promise<void>

const KNOWN_EVENTS = new Set<keyof SSEEventMap>([
  'start', 'step', 'sql', 'data', 'chart', 'text', 'title', 'error', 'done',
])

/** 不可重试的错误：抛出后 fetchEventSource 停止自动重连 */
class FatalStreamError extends ApiError {}

export const realStreamChat: StreamChat = async (sessionId, question, { onEvent, signal }) => {
  try {
    await fetchEventSource(`${API_BASE}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, question }),
      signal,
      openWhenHidden: true, // 切到后台标签页时不断开（默认会断开重连，导致重复提问）
      async onopen(resp) {
        if (resp.ok && resp.headers.get('content-type')?.startsWith(EventStreamContentType)) return
        // 流开始前的业务错误（如会话不存在）返回的是 JSON
        let code = `HTTP_${resp.status}`
        let message = resp.statusText || '请求失败'
        try {
          const body = await resp.json()
          code = body.code ?? code
          message = body.message ?? message
        } catch {
          /* 非 JSON */
        }
        throw new FatalStreamError(code, message, resp.status)
      },
      onmessage(msg) {
        if (!KNOWN_EVENTS.has(msg.event as keyof SSEEventMap) || !msg.data) return // 忽略 ping 等
        onEvent({ event: msg.event, data: JSON.parse(msg.data) } as SSEEvent)
      },
      onclose() {
        // 服务端正常关闭：不重连
      },
      onerror(err) {
        // 抛出即终止，不让库自动重试（重试会重复提交问题）
        if (err instanceof ApiError) throw err
        throw new FatalStreamError('NETWORK_ERROR', '与服务器的连接中断', 0)
      },
    })
  } catch (err) {
    if (signal.aborted) return
    throw err
  }
}
