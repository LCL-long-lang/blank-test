import { beforeEach, describe, expect, it } from 'vitest'
import { mockApi, mockConfig, resetMock } from '../mocks'
import type { ChatMessage, SSEEvent } from '../types'
import { useChartStore } from './chartStore'
import { applyEvent, useChatStore } from './chatStore'
import { ACTIVE_KEY, sortSessions, useSessionStore } from './sessionStore'

const blank = (): ChatMessage => ({
  id: 'tmp', role: 'assistant', content: '', status: 'streaming', createdAt: '', steps: [], sql: null,
  attempts: [], rowCount: null, hasChart: false, error: null, elapsedMs: null, question: 'q',
})

const reduce = (events: SSEEvent[]) => events.reduce(applyEvent, blank())

describe('applyEvent（纯函数）', () => {
  it('完整事件序列', () => {
    const m = reduce([
      { event: 'start', data: { message_id: 'm1', user_message_id: 'u1' } },
      { event: 'step', data: { key: 'rewrite', status: 'running', label: '理解问题', detail: null } },
      { event: 'step', data: { key: 'rewrite', status: 'done', label: '理解问题', detail: '改写后' } },
      { event: 'step', data: { key: 'intent', status: 'done', label: '识别意图', detail: '查询数据' } },
      { event: 'sql', data: { sql: 'SELECT 1', attempt: 1 } },
      { event: 'data', data: { columns: ['a'], rows: [[1]], total: 1, truncated: false } },
      { event: 'chart', data: { spec: { chart_type: 'kpi', title: 't', x_field: null, y_fields: ['a'], series_field: null, sort: null }, option: {} } },
      { event: 'text', data: { delta: '结果' } },
      { event: 'text', data: { delta: '是 1' } },
      { event: 'done', data: { message_id: 'm1', elapsed_ms: 1200 } },
    ])
    expect(m.id).toBe('m1')
    expect(m.steps.map((s) => [s.key, s.status, s.detail])).toEqual([['rewrite', 'done', '改写后'], ['intent', 'done', '查询数据']])
    expect(m.sql).toBe('SELECT 1')
    expect(m.rowCount).toBe(1)
    expect(m.hasChart).toBe(true)
    expect(m.content).toBe('结果是 1')
    expect(m.status).toBe('done')
    expect(m.elapsedMs).toBe(1200)
  })

  it('自动修正：保留每次尝试，sql 取最后一次', () => {
    const m = reduce([
      { event: 'sql', data: { sql: 'bad', attempt: 1 } },
      { event: 'step', data: { key: 'execute', status: 'error', label: '执行查询', detail: 'no such column' } },
      { event: 'sql', data: { sql: 'good', attempt: 2 } },
      { event: 'step', data: { key: 'execute', status: 'done', label: '执行查询', detail: '7 行' } },
    ])
    expect(m.attempts.map((a) => a.attempt)).toEqual([1, 2])
    expect(m.sql).toBe('good')
    expect(m.steps).toHaveLength(1)
    expect(m.steps[0].status).toBe('done')
  })

  it('error 之后的 done 不覆盖错误状态；running 步骤收尾为 done', () => {
    const m = reduce([
      { event: 'step', data: { key: 'generate_sql', status: 'running', label: '生成 SQL', detail: null } },
      { event: 'error', data: { code: 'SQL_FAILED', message: '失败', retryable: true } },
      { event: 'done', data: { message_id: 'm', elapsed_ms: 1 } },
    ])
    expect(m.status).toBe('error')
    expect(m.error?.code).toBe('SQL_FAILED')
    expect(m.steps[0].status).toBe('done')
  })
})

describe('sessionStore', () => {
  beforeEach(() => {
    resetMock()
    useSessionStore.setState({ sessions: [], activeId: null, keyword: '' })
  })

  it('置顶优先，再按更新时间倒序', () => {
    const list = sortSessions([
      { id: 'a', title: '', pinned: false, created_at: '', updated_at: '2026-01-02' },
      { id: 'b', title: '', pinned: true, created_at: '', updated_at: '2026-01-01' },
      { id: 'c', title: '', pinned: false, created_at: '', updated_at: '2026-01-03' },
    ])
    expect(list.map((s) => s.id)).toEqual(['b', 'c', 'a'])
  })

  it('新建 → 重命名 → 置顶 → 删除当前会话后切到相邻会话', async () => {
    const st = useSessionStore.getState()
    await st.fetch('')
    const created = await st.create()
    expect(useSessionStore.getState().activeId).toBe(created.id)
    await st.rename(created.id, '  新名字 ')
    expect(useSessionStore.getState().sessions.find((s) => s.id === created.id)?.title).toBe('新名字')
    await st.togglePin(created.id)
    expect(useSessionStore.getState().sessions[0].id).toBe(created.id)
    await st.remove(created.id)
    const after = useSessionStore.getState()
    expect(after.sessions.some((s) => s.id === created.id)).toBe(false)
    expect(after.activeId).toBe(after.sessions[0].id)
  })

  it('刷新后恢复上次的会话；该会话已删除时不恢复', async () => {
    localStorage.setItem(ACTIVE_KEY, 'mock-s2')
    await useSessionStore.getState().fetch('')
    expect(useSessionStore.getState().activeId).toBe('mock-s2')

    useSessionStore.setState({ sessions: [], activeId: null })
    localStorage.setItem(ACTIVE_KEY, 'deleted-id')
    await useSessionStore.getState().fetch('')
    expect(useSessionStore.getState().activeId).toBeNull()

    useSessionStore.getState().setActive('mock-s1')
    expect(localStorage.getItem(ACTIVE_KEY)).toBe('mock-s1')
    localStorage.removeItem(ACTIVE_KEY)
  })

  it('搜索', async () => {
    await useSessionStore.getState().fetch('会员')
    expect(useSessionStore.getState().sessions.map((s) => s.title)).toEqual(['会员等级占比'])
  })
})

describe('chatStore + chartStore（Mock 流）', () => {
  beforeEach(() => {
    resetMock()
    mockConfig.delay = 0
    useChatStore.setState({ messages: {}, streaming: null, controller: null })
    useChartStore.setState({ activeId: null, charts: {}, pendingData: {}, error: null })
    useSessionStore.setState({ sessions: [], activeId: null })
  })

  it('发送问题：消息 id 替换为后端 id，图表进入 chartStore，标题更新', async () => {
    const s = await useSessionStore.getState().create()
    await useChatStore.getState().send(s.id, '近 6 个月各品类销售额趋势')
    const msgs = useChatStore.getState().messages[s.id]
    expect(msgs.map((m) => m.role)).toEqual(['user', 'assistant'])
    const ai = msgs[1]
    expect(ai.id.startsWith('mock-')).toBe(true)
    expect(ai.status).toBe('done')
    expect(ai.hasChart).toBe(true)
    expect(ai.content).toContain('手机数码')
    const chart = useChartStore.getState()
    expect(chart.activeId).toBe(ai.id)
    expect(chart.charts[ai.id].spec.chart_type).toBe('line')
    expect(chart.charts[ai.id].rows.length).toBe(24)
    expect(chart.charts[ai.id].sql).toContain('SELECT')
    expect(useSessionStore.getState().sessions[0].title).toBe('品类销售趋势')
    expect(useChatStore.getState().streaming).toBeNull()
  })

  it('自动修正场景：两次 SQL 尝试', async () => {
    const s = await useSessionStore.getState().create()
    await useChatStore.getState().send(s.id, '今年各大区的销售额排名')
    const ai = useChatStore.getState().messages[s.id][1]
    expect(ai.attempts.map((a) => a.attempt)).toEqual([1, 2])
    expect(useChartStore.getState().charts[ai.id].spec.chart_type).toBe('bar')
  })

  it('错误场景：状态为 error，可重试', async () => {
    const s = await useSessionStore.getState().create()
    await useChatStore.getState().send(s.id, '故意让它失败')
    const ai = useChatStore.getState().messages[s.id][1]
    expect(ai.status).toBe('error')
    expect(ai.error?.retryable).toBe(true)
    expect(ai.question).toBe('故意让它失败')
  })

  it('停止生成：状态为 cancelled，进行中的步骤标记为已停止', async () => {
    mockConfig.delay = 20
    const s = await useSessionStore.getState().create()
    const p = useChatStore.getState().send(s.id, '近 6 个月各品类销售额趋势')
    await new Promise((r) => setTimeout(r, 70))
    useChatStore.getState().stop()
    await p
    const ai = useChatStore.getState().messages[s.id][1]
    expect(ai.status).toBe('cancelled')
    expect(ai.steps.some((x) => x.status === 'running')).toBe(false)
    expect(useChatStore.getState().streaming).toBeNull()
  })

  it('生成中不能再次发送', async () => {
    mockConfig.delay = 10
    const s = await useSessionStore.getState().create()
    const p = useChatStore.getState().send(s.id, '近 6 个月各品类销售额趋势')
    await useChatStore.getState().send(s.id, '另一个问题')
    await p
    expect(useChatStore.getState().messages[s.id]).toHaveLength(2)
  })

  it('加载历史会话后右栏回看最后一张图；切换图表类型', async () => {
    const s = await useSessionStore.getState().create()
    await useChatStore.getState().send(s.id, '各会员等级的客户占比')
    const aiId = useChatStore.getState().messages[s.id][1].id
    // 模拟刷新：清空本地状态后重新加载
    useChatStore.setState({ messages: {} })
    useChartStore.setState({ activeId: null, charts: {}, pendingData: {} })
    await useChatStore.getState().load(s.id)
    await new Promise((r) => setTimeout(r, 0))
    expect(useChartStore.getState().activeId).toBe(aiId)
    expect(useChartStore.getState().charts[aiId].spec.chart_type).toBe('pie')
    await useChartStore.getState().switchType('bar')
    expect(useChartStore.getState().charts[aiId].spec.chart_type).toBe('bar')
    expect((await mockApi.getChart(aiId)).spec.chart_type).toBe('bar')
  })

  it('新建会话后立即提问，迟到的历史加载结果不会覆盖新消息', async () => {
    const s = await useSessionStore.getState().create()
    const loading = useChatStore.getState().load(s.id) // 请求发出但尚未返回
    await useChatStore.getState().send(s.id, '各会员等级的客户占比')
    await loading
    expect(useChatStore.getState().messages[s.id].map((m) => m.role)).toEqual(['user', 'assistant'])
  })

  it('切换类型失败时保留原图并给出错误', async () => {
    const s = await useSessionStore.getState().create()
    await useChatStore.getState().send(s.id, '各会员等级的客户占比')
    await expect(useChartStore.getState().switchType('kpi')).rejects.toThrow('指标卡')
    const st = useChartStore.getState()
    expect(st.charts[st.activeId!].spec.chart_type).toBe('pie')
    expect(st.error).toContain('指标卡')
  })
})
