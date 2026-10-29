import { create } from 'zustand'
import { api } from '../services'
import type { Session } from '../types'
import { localStamp } from '../utils/format'

/** 记住上次打开的会话，刷新页面后恢复 */
export const ACTIVE_KEY = 'nl2sql.activeSession'

function saveActive(id: string | null) {
  try {
    if (id) localStorage.setItem(ACTIVE_KEY, id)
    else localStorage.removeItem(ACTIVE_KEY)
  } catch {
    /* 隐私模式等禁用存储时忽略 */
  }
}

function loadActive(): string | null {
  try {
    return localStorage.getItem(ACTIVE_KEY)
  } catch {
    return null
  }
}

interface SessionState {
  sessions: Session[]
  activeId: string | null
  keyword: string
  loading: boolean
  error: string | null

  fetch: (keyword?: string) => Promise<void>
  create: () => Promise<Session>
  rename: (id: string, title: string) => Promise<void>
  togglePin: (id: string) => Promise<void>
  remove: (id: string) => Promise<void>
  setActive: (id: string | null) => void
  /** SSE title 事件 / 本地更新：只改内存，不请求接口 */
  patchLocal: (id: string, patch: Partial<Session>) => void
  /** 收到新消息后把会话挪到“今天”，置顶顺序不变 */
  touch: (id: string) => void
}

/** 与后端一致：置顶优先，再按更新时间倒序 */
export const sortSessions = (list: Session[]) =>
  [...list].sort((a, b) => Number(b.pinned) - Number(a.pinned) || b.updated_at.localeCompare(a.updated_at))

export const useSessionStore = create<SessionState>((set, get) => ({
  sessions: [],
  activeId: null,
  keyword: '',
  loading: false,
  error: null,

  async fetch(keyword = get().keyword) {
    set({ loading: true, keyword, error: null })
    try {
      const sessions = await api.listSessions(keyword || undefined)
      // 搜索结果过期（用户又输入了别的）时丢弃
      if (get().keyword !== keyword) return
      set({ sessions, loading: false })
      // 首次加载（无搜索词、尚未选中）：恢复上次的会话，它已被删除时不恢复
      if (!keyword && get().activeId === null) {
        const saved = loadActive()
        if (saved && sessions.some((s) => s.id === saved)) set({ activeId: saved })
      }
    } catch (e) {
      set({ loading: false, error: (e as Error).message })
    }
  },

  async create() {
    const s = await api.createSession()
    set((st) => ({ sessions: sortSessions([s, ...st.sessions]), activeId: s.id, keyword: '' }))
    saveActive(s.id)
    return s
  },

  async rename(id, title) {
    const t = title.trim()
    if (!t) return
    const updated = await api.updateSession(id, { title: t })
    get().patchLocal(id, updated)
  },

  async togglePin(id) {
    const cur = get().sessions.find((s) => s.id === id)
    if (!cur) return
    const updated = await api.updateSession(id, { pinned: !cur.pinned })
    set((st) => ({ sessions: sortSessions(st.sessions.map((s) => (s.id === id ? updated : s))) }))
  },

  async remove(id) {
    await api.deleteSession(id)
    set((st) => {
      const idx = st.sessions.findIndex((s) => s.id === id)
      const sessions = st.sessions.filter((s) => s.id !== id)
      // 删除当前会话：切到相邻的下一个
      const activeId = st.activeId === id ? (sessions[idx] ?? sessions[idx - 1] ?? null)?.id ?? null : st.activeId
      return { sessions, activeId }
    })
    saveActive(get().activeId)
  },

  setActive(id) {
    set({ activeId: id })
    saveActive(id)
  },

  patchLocal(id, patch) {
    set((st) => ({ sessions: st.sessions.map((s) => (s.id === id ? { ...s, ...patch } : s)) }))
  },

  touch(id) {
    set((st) => ({
      sessions: sortSessions(st.sessions.map((s) => (s.id === id ? { ...s, updated_at: localStamp() } : s))),
    }))
  },
}))
