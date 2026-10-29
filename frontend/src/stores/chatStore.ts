import { create } from 'zustand'
import { ApiError, api, streamChat } from '../services'
import type { ChatMessage, MessageOut, SSEEvent, StepView } from '../types'
import { localStamp } from '../utils/format'
import { useChartStore } from './chartStore'
import { useSessionStore } from './sessionStore'

const tempId = () => `tmp-${Math.random().toString(36).slice(2, 10)}`
/** 每次发送问题自增；load 用它判断请求期间是否有新消息写入 */
let sendSeq = 0
const nowStamp = () => localStamp()

export function fromMessageOut(m: MessageOut): ChatMessage {
  return {
    id: m.id, role: m.role, content: m.content, status: m.status, createdAt: m.created_at,
    steps: [], sql: m.sql, attempts: [], rowCount: null, hasChart: m.has_chart,
    error: m.error ? { code: 'SQL_FAILED', message: m.error, retryable: true } : null,
    elapsedMs: m.elapsed_ms,
  }
}

function blankAssistant(id: string, question: string): ChatMessage {
  return {
    id, role: 'assistant', content: '', status: 'streaming', createdAt: nowStamp(), steps: [],
    sql: null, attempts: [], rowCount: null, hasChart: false, error: null, elapsedMs: null, question,
  }
}

/** 同一 key 的步骤只保留最新状态，保持首次出现的顺序 */
function upsertStep(steps: StepView[], s: StepView): StepView[] {
  const i = steps.findIndex((x) => x.key === s.key)
  if (i < 0) return [...steps, s]
  const next = [...steps]
  next[i] = { ...s, detail: s.detail ?? (s.status === 'done' ? next[i].detail : null) }
  return next
}

/**
 * 纯函数：把一个 SSE 事件应用到 AI 消息上（不含 chart/data/title 这类跨 store 的副作用）。
 * start 事件会把临时 id 换成后端的 message_id。
 */
export function applyEvent(msg: ChatMessage, e: SSEEvent): ChatMessage {
  switch (e.event) {
    case 'start':
      return { ...msg, id: e.data.message_id }
    case 'step':
      return { ...msg, steps: upsertStep(msg.steps, e.data) }
    case 'sql':
      return { ...msg, sql: e.data.sql, attempts: [...msg.attempts, e.data] }
    case 'data':
      return { ...msg, rowCount: e.data.total }
    case 'chart':
      return { ...msg, hasChart: true }
    case 'text':
      return { ...msg, content: msg.content + e.data.delta }
    case 'error':
      return { ...msg, status: 'error', error: e.data }
    case 'done':
      return {
        ...msg, elapsedMs: e.data.elapsed_ms,
        status: msg.status === 'error' ? 'error' : 'done',
        // 收尾：仍在 running 的步骤视为完成
        steps: msg.steps.map((s) => (s.status === 'running' ? { ...s, status: 'done' } : s)),
      }
    case 'title':
      return msg
  }
}

interface ChatState {
  messages: Record<string, ChatMessage[]>
  loadingSession: string | null
  /** 正在生成的会话 / 消息 */
  streaming: { sessionId: string; messageId: string } | null
  controller: AbortController | null
  loadError: string | null

  load: (sessionId: string) => Promise<void>
  send: (sessionId: string, question: string) => Promise<void>
  stop: () => void
  retry: (sessionId: string, messageId: string) => Promise<void>
  drop: (sessionId: string) => void
}

export const useChatStore = create<ChatState>((set, get) => {
  const updateMsg = (sessionId: string, id: string, fn: (m: ChatMessage) => ChatMessage) =>
    set((st) => ({
      messages: { ...st.messages, [sessionId]: (st.messages[sessionId] ?? []).map((m) => (m.id === id ? fn(m) : m)) },
    }))

  return {
    messages: {},
    loadingSession: null,
    streaming: null,
    controller: null,
    loadError: null,

    async load(sessionId) {
      // 正在生成的会话保留本地状态，不被接口数据覆盖
      if (get().streaming?.sessionId === sessionId) return
      const seq = sendSeq
      set({ loadingSession: sessionId, loadError: null })
      try {
        const fetched = await api.listMessages(sessionId)
        // 请求期间用户已经发出了新问题（如新建会话后立即提问）：丢弃这次结果，避免覆盖本地消息
        if (seq !== sendSeq) return
        const list = fetched.map(fromMessageOut)
        // 给 AI 消息补上对应问题，便于重试
        list.forEach((m, i) => {
          if (m.role === 'assistant' && list[i - 1]?.role === 'user') m.question = list[i - 1].content
        })
        set((st) => ({ messages: { ...st.messages, [sessionId]: list } }))
        const lastChart = [...list].reverse().find((m) => m.hasChart)
        const chart = useChartStore.getState()
        if (lastChart) void chart.load(lastChart.id)
        else chart.reset()
      } catch (e) {
        set({ loadError: (e as Error).message })
      } finally {
        if (get().loadingSession === sessionId) set({ loadingSession: null })
      }
    },

    async send(sessionId, question) {
      const q = question.trim()
      if (!q || get().streaming) return
      sendSeq++
      const userMsg: ChatMessage = { ...blankAssistant(tempId(), q), role: 'user', content: q, status: 'done' }
      let aiId = tempId()
      const controller = new AbortController()
      set((st) => ({
        messages: { ...st.messages, [sessionId]: [...(st.messages[sessionId] ?? []), userMsg, blankAssistant(aiId, q)] },
        streaming: { sessionId, messageId: aiId },
        controller,
      }))
      useSessionStore.getState().touch(sessionId)
      const chart = useChartStore.getState()
      let lastSql: string | null = null

      const onEvent = (e: SSEEvent) => {
        if (e.event === 'start') {
          const realId = e.data.message_id
          updateMsg(sessionId, aiId, (m) => applyEvent(m, e))
          updateMsg(sessionId, userMsg.id, (m) => ({ ...m, id: e.data.user_message_id }))
          aiId = realId
          set({ streaming: { sessionId, messageId: realId } })
          return
        }
        if (e.event === 'sql') lastSql = e.data.sql
        if (e.event === 'data') chart.setData(aiId, e.data, lastSql)
        if (e.event === 'chart') chart.setChart(aiId, e.data)
        if (e.event === 'title') useSessionStore.getState().patchLocal(e.data.session_id, { title: e.data.title })
        updateMsg(sessionId, aiId, (m) => applyEvent(m, e))
      }

      try {
        await streamChat(sessionId, q, { onEvent, signal: controller.signal })
        if (controller.signal.aborted) {
          updateMsg(sessionId, aiId, (m) => ({
            ...m, status: 'cancelled',
            steps: m.steps.map((s) => (s.status === 'running' ? { ...s, status: 'error', detail: '已停止' } : s)),
          }))
        }
      } catch (err) {
        const ae = err instanceof ApiError ? err : new ApiError('NETWORK_ERROR', (err as Error).message, 0)
        updateMsg(sessionId, aiId, (m) => ({ ...m, status: 'error', error: { code: ae.code, message: ae.message, retryable: true } }))
      } finally {
        updateMsg(sessionId, aiId, (m) => (m.status === 'streaming' ? { ...m, status: 'done' } : m))
        set({ streaming: null, controller: null })
      }
    },

    stop() {
      get().controller?.abort()
    },

    async retry(sessionId, messageId) {
      const msg = get().messages[sessionId]?.find((m) => m.id === messageId)
      if (msg?.question) await get().send(sessionId, msg.question)
    },

    drop(sessionId) {
      set((st) => {
        const messages = { ...st.messages }
        delete messages[sessionId]
        return { messages }
      })
    },
  }
})
