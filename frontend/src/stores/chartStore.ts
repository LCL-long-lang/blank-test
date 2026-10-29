import { create } from 'zustand'
import { api } from '../services'
import type { ChartData, ChartType, DataEvent } from '../types'

interface ChartState {
  /** 右栏当前展示的消息 */
  activeId: string | null
  charts: Record<string, ChartData>
  /** 流式过程中 data 已到、chart 未到时暂存 */
  pendingData: Record<string, DataEvent & { sql: string | null }>
  loadingId: string | null
  switching: boolean
  error: string | null

  select: (messageId: string | null) => void
  setData: (messageId: string, data: DataEvent, sql: string | null) => void
  setChart: (messageId: string, chart: Pick<ChartData, 'spec' | 'option'>) => void
  /** 回看历史消息：本地没有则请求 /api/charts/{id} */
  load: (messageId: string) => Promise<void>
  switchType: (type: ChartType) => Promise<void>
  reset: () => void
}

export const useChartStore = create<ChartState>((set, get) => ({
  activeId: null,
  charts: {},
  pendingData: {},
  loadingId: null,
  switching: false,
  error: null,

  select(messageId) {
    set({ activeId: messageId, error: null })
  },

  setData(messageId, data, sql) {
    set((st) => ({ pendingData: { ...st.pendingData, [messageId]: { ...data, sql } }, activeId: messageId }))
  },

  setChart(messageId, { spec, option }) {
    set((st) => {
      const d = st.pendingData[messageId]
      const chart: ChartData = {
        messageId, spec, option,
        columns: d?.columns ?? [], rows: d?.rows ?? [], sql: d?.sql ?? null, truncated: d?.truncated ?? false,
      }
      return { charts: { ...st.charts, [messageId]: chart }, activeId: messageId }
    })
  },

  async load(messageId) {
    set({ activeId: messageId, error: null })
    if (get().charts[messageId]) return
    set({ loadingId: messageId })
    try {
      const c = await api.getChart(messageId)
      set((st) => ({
        charts: { ...st.charts, [messageId]: { messageId, spec: c.spec, option: c.option, columns: c.columns, rows: c.rows, sql: null, truncated: false } },
      }))
    } catch (e) {
      if (get().activeId === messageId) set({ error: (e as Error).message })
    } finally {
      if (get().loadingId === messageId) set({ loadingId: null })
    }
  },

  async switchType(type) {
    const id = get().activeId
    const cur = id ? get().charts[id] : null
    if (!id || !cur || cur.spec.chart_type === type) return
    set({ switching: true, error: null })
    try {
      const c = await api.renderChart(id, type)
      set((st) => ({ charts: { ...st.charts, [id]: { ...cur, spec: c.spec, option: c.option } } }))
    } catch (e) {
      set({ error: (e as Error).message })
      throw e
    } finally {
      set({ switching: false })
    }
  },

  reset() {
    set({ activeId: null, error: null, loadingId: null })
  },
}))
