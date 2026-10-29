/** 与 realApi / realStreamChat 同签名的 Mock：内存存储 + 定时器模拟流式事件 */
import type { ApiClient } from '../services/api'
import { ApiError } from '../services/http'
import type { StreamChat } from '../services/sse'
import { localStamp } from '../utils/format'
import type { ChartOut, ChartSpec, EChartsOption, MessageOut, SSEEvent, Session, StepEvent } from '../types'
import { MOCK_SCHEMA, SCENARIOS, type MockScenario } from './data'

/** 事件间隔（毫秒）；测试中设为 0 */
export const mockConfig = { delay: 120 }

const uid = () => Math.random().toString(36).slice(2, 12)
const now = () => localStamp()

interface Store {
  sessions: Session[]
  messages: MessageOut[]
  charts: Record<string, ChartOut>
}

function seed(): Store {
  const s: Store = { sessions: [], messages: [], charts: {} }
  const day = (offset: number) => localStamp(new Date(Date.now() - offset * 86_400_000))
  s.sessions.push(
    { id: 'mock-s1', title: '大区销售排名', pinned: true, created_at: day(3), updated_at: day(3) },
    { id: 'mock-s2', title: '会员等级占比', pinned: false, created_at: day(0), updated_at: day(0) },
    { id: 'mock-s3', title: '客户复购分析', pinned: false, created_at: day(12), updated_at: day(12) },
  )
  return s
}

let store = seed()

/** 测试用：重置内存数据 */
export function resetMock() {
  store = seed()
}

function sortSessions(list: Session[]) {
  return [...list].sort(
    (a, b) => Number(b.pinned) - Number(a.pinned) || b.updated_at.localeCompare(a.updated_at),
  )
}

function findSession(id: string) {
  const s = store.sessions.find((x) => x.id === id)
  if (!s) throw new ApiError('NOT_FOUND', '会话不存在', 404)
  return s
}

function switchSpec(spec: ChartSpec, chartType: ChartSpec['chart_type']): ChartSpec {
  return { ...spec, chart_type: chartType, sort: chartType === 'bar' ? spec.sort : null }
}

export const mockApi: ApiClient = {
  async health() {
    return { status: 'ok', version: 'mock', business_db: true, app_db: true, llm_configured: true }
  },
  async listSessions(keyword) {
    const k = keyword?.trim()
    return sortSessions(k ? store.sessions.filter((s) => s.title.includes(k)) : store.sessions)
  },
  async createSession(title) {
    const s: Session = { id: `mock-${uid()}`, title: title?.trim() || '新对话', pinned: false, created_at: now(), updated_at: now() }
    store.sessions.push(s)
    return s
  },
  async updateSession(id, patch) {
    const s = findSession(id)
    if (patch.title !== undefined) s.title = patch.title.trim() || s.title
    if (patch.pinned !== undefined) s.pinned = patch.pinned
    return { ...s }
  },
  async deleteSession(id) {
    findSession(id)
    store.sessions = store.sessions.filter((s) => s.id !== id)
    const removed = new Set(store.messages.filter((m) => m.session_id === id).map((m) => m.id))
    store.messages = store.messages.filter((m) => m.session_id !== id)
    removed.forEach((mid) => delete store.charts[mid])
  },
  async listMessages(sessionId) {
    findSession(sessionId)
    return store.messages.filter((m) => m.session_id === sessionId).map((m) => ({ ...m }))
  },
  async getChart(messageId) {
    const c = store.charts[messageId]
    if (!c) throw new ApiError('NOT_FOUND', '该消息没有图表', 404)
    return structuredClone(c)
  },
  async renderChart(messageId, chartType) {
    const c = await mockApi.getChart(messageId)
    if (chartType === 'kpi' && c.rows.length !== 1) {
      throw new ApiError('CHART_UNSUPPORTED', '指标卡只适用于单行数值结果', 400)
    }
    const spec = switchSpec(c.spec, chartType)
    // Mock 只做近似切换：真实接口由后端重新组装完整 option
    const option: EChartsOption = { ...c.option }
    if (chartType === 'table' || chartType === 'kpi') option.kind = chartType
    else delete option.kind
    const seriesType = chartType === 'stacked_bar' ? 'bar' : chartType
    if (Array.isArray(option.series)) {
      option.series = (option.series as Array<Record<string, unknown>>).map((s) => ({
        ...s, type: seriesType, ...(chartType === 'stacked_bar' ? { stack: 'total' } : {}),
      }))
    }
    const next: ChartOut = { ...c, spec, option }
    store.charts[messageId] = next
    return structuredClone(next)
  },
  async getSchema() {
    return MOCK_SCHEMA
  },
}

// ---------- 流式问答 ----------

function sleep(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal.aborted) return reject(new DOMException('aborted', 'AbortError'))
    const t = setTimeout(resolve, ms)
    signal.addEventListener('abort', () => {
      clearTimeout(t)
      reject(new DOMException('aborted', 'AbortError'))
    }, { once: true })
  })
}

const step = (key: StepEvent['key'], label: string, status: StepEvent['status'] = 'done', detail: string | null = null): SSEEvent => ({
  event: 'step',
  data: { key, label, status, detail },
})

function chunk(text: string, size = 6) {
  const out: string[] = []
  for (let i = 0; i < text.length; i += size) out.push(text.slice(i, i + size))
  return out
}

function plan(question: string, sc: MockScenario | null): SSEEvent[] {
  if (!sc) {
    const reply = '你好！我是数据分析助手，可以用自然语言查询订单、商品、客户和地区数据，并自动生成图表。试试问：**近 6 个月各品类销售额趋势**'
    return [step('rewrite', '理解问题', 'done', question), step('intent', '识别意图', 'done', '闲聊'),
      ...chunk(reply).map((delta): SSEEvent => ({ event: 'text', data: { delta } }))]
  }
  if (/错误|失败/.test(question)) {
    return [
      step('rewrite', '理解问题', 'done', question), step('intent', '识别意图', 'done', '查询数据'),
      step('schema', '定位数据表', 'done', '6 张表'),
      ...[1, 2, 3].flatMap((attempt): SSEEvent[] => [
        { event: 'sql', data: { sql: 'SELECT nope FROM orders LIMIT 1000', attempt } },
        step('execute', '执行查询', 'error', 'no such column: nope'),
      ]),
      { event: 'error', data: { code: 'SQL_FAILED', message: 'SQL 连续 3 次执行失败：no such column: nope', retryable: true } },
    ]
  }
  const events: SSEEvent[] = [
    step('rewrite', '理解问题', 'running'), step('rewrite', '理解问题', 'done', sc.rewritten),
    step('intent', '识别意图', 'done', '查询数据'), step('schema', '定位数据表', 'done', '6 张表'),
    step('generate_sql', '生成 SQL', 'running'),
  ]
  let attempt = 1
  if (sc.badSql) {
    events.push({ event: 'sql', data: { sql: sc.badSql.sql, attempt } },
      step('execute', '执行查询', 'error', sc.badSql.error), step('generate_sql', '生成 SQL', 'running', '第 2 次'))
    attempt = 2
  }
  events.push(
    { event: 'sql', data: { sql: sc.sql, attempt } }, step('generate_sql', '生成 SQL'),
    step('execute', '执行查询', 'running'),
    { event: 'data', data: { columns: sc.columns, rows: sc.rows, total: sc.rows.length, truncated: false } },
    step('execute', '执行查询', 'done', `${sc.rows.length} 行，38 ms`),
    step('chart', '生成图表', 'running'),
    { event: 'chart', data: { spec: sc.spec, option: sc.option } },
    step('chart', '生成图表', 'done', sc.spec.chart_type),
    step('insight', '解读结果', 'running'),
    ...chunk(sc.answer).map((delta): SSEEvent => ({ event: 'text', data: { delta } })),
    step('insight', '解读结果'),
  )
  return events
}

export const mockStreamChat: StreamChat = async (sessionId, question, { onEvent, signal }) => {
  const session = findSession(sessionId)
  const started = Date.now()
  const user: MessageOut = { id: `mock-${uid()}`, session_id: sessionId, role: 'user', content: question, sql: null, status: 'done', error: null, has_chart: false, elapsed_ms: null, created_at: now() }
  const ai: MessageOut = { id: `mock-${uid()}`, session_id: sessionId, role: 'assistant', content: '', sql: null, status: 'streaming', error: null, has_chart: false, elapsed_ms: null, created_at: now() }
  store.messages.push(user, ai)
  session.updated_at = now()

  const sc = /你好|您好|你是谁|能做什么|hello|hi/i.test(question) ? null : SCENARIOS.find((s) => s.match.test(question))!
  const emit = (e: SSEEvent) => {
    if (e.event === 'text') ai.content += e.data.delta
    if (e.event === 'sql') ai.sql = e.data.sql
    if (e.event === 'error') { ai.status = 'error'; ai.error = e.data.message }
    if (e.event === 'chart' && sc) {
      ai.has_chart = true
      store.charts[ai.id] = { message_id: ai.id, spec: e.data.spec, option: e.data.option, columns: sc.columns, rows: sc.rows }
    }
    onEvent(e)
  }

  try {
    emit({ event: 'start', data: { message_id: ai.id, user_message_id: user.id } })
    for (const e of plan(question, sc)) {
      await sleep(e.event === 'text' ? mockConfig.delay / 3 : mockConfig.delay, signal)
      emit(e)
    }
    if (ai.status !== 'error') ai.status = 'done'
    if (ai.status === 'done' && session.title === '新对话' && sc) {
      session.title = sc.title
      emit({ event: 'title', data: { session_id: sessionId, title: sc.title } })
    }
    ai.elapsed_ms = Date.now() - started
    emit({ event: 'done', data: { message_id: ai.id, elapsed_ms: ai.elapsed_ms } })
  } catch (err) {
    if (signal.aborted) {
      ai.status = 'cancelled'
      return
    }
    throw err
  }
}
