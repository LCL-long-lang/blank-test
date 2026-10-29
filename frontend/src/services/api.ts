import type {
  ChartOut,
  ChartType,
  HealthOut,
  MessageOut,
  SchemaOut,
  Session,
  SessionUpdate,
} from '../types'
import { http } from './http'

/** REST 接口，对应后端第 5.1 节。组件和 store 只通过 services/index.ts 拿到它（或同签名的 Mock） */
export interface ApiClient {
  health(): Promise<HealthOut>
  listSessions(keyword?: string): Promise<Session[]>
  createSession(title?: string): Promise<Session>
  updateSession(id: string, patch: SessionUpdate): Promise<Session>
  deleteSession(id: string): Promise<void>
  listMessages(sessionId: string): Promise<MessageOut[]>
  getChart(messageId: string): Promise<ChartOut>
  renderChart(messageId: string, chartType: ChartType): Promise<ChartOut>
  getSchema(): Promise<SchemaOut>
}

const enc = encodeURIComponent

export const realApi: ApiClient = {
  health: () => http.get('/health'),
  listSessions: (keyword) =>
    http.get(keyword ? `/sessions?keyword=${enc(keyword)}` : '/sessions'),
  createSession: (title) => http.post('/sessions', title ? { title } : {}),
  updateSession: (id, patch) => http.patch(`/sessions/${enc(id)}`, patch),
  deleteSession: async (id) => {
    await http.delete<null>(`/sessions/${enc(id)}`)
  },
  listMessages: (sessionId) => http.get(`/sessions/${enc(sessionId)}/messages`),
  getChart: (messageId) => http.get(`/charts/${enc(messageId)}`),
  renderChart: (messageId, chartType) =>
    http.post(`/charts/${enc(messageId)}/render`, { chart_type: chartType }),
  getSchema: () => http.get('/schema'),
}
