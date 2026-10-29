import { PlusOutlined, RadarChartOutlined, SearchOutlined } from '@ant-design/icons'
import { App, Button, Input, Spin } from 'antd'
import { useEffect, useMemo, useRef, useState } from 'react'
import { USE_MOCK } from '../../services'
import { useChatStore } from '../../stores/chatStore'
import { useSessionStore } from '../../stores/sessionStore'
import { GROUP_LABELS, groupSessions } from '../../utils/format'
import { BackendStatus } from '../common/BackendStatus'
import { SessionItem } from './SessionItem'
import './Sidebar.css'

const SEARCH_DEBOUNCE_MS = 250

export function SessionSidebar() {
  const { message } = App.useApp()
  const { sessions, activeId, loading, fetch, create, rename, togglePin, remove, setActive } = useSessionStore()
  const streamingSession = useChatStore((s) => s.streaming?.sessionId ?? null)
  const dropMessages = useChatStore((s) => s.drop)
  const [keyword, setKeyword] = useState('')
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)

  useEffect(() => {
    void fetch('')
  }, [fetch])

  const onSearch = (v: string) => {
    setKeyword(v)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => void fetch(v.trim()), SEARCH_DEBOUNCE_MS)
  }

  const groups = useMemo(() => groupSessions(sessions), [sessions])

  const run = async (fn: () => Promise<unknown>, okText?: string) => {
    try {
      await fn()
      if (okText) message.success(okText)
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  return (
    <div className="sidebar">
      <div className="brand">
        <div className="brand-logo"><RadarChartOutlined /></div>
        <div>
          <div className="brand-name">智能数据分析</div>
          <div className="brand-sub">AI · NL2SQL · Insight</div>
        </div>
      </div>

      <Button
        type="primary"
        icon={<PlusOutlined />}
        className="new-chat"
        block
        onClick={() => run(async () => { await create(); setKeyword('') })}
      >
        新建对话
      </Button>

      <Input
        allowClear
        prefix={<SearchOutlined style={{ color: 'var(--text-muted)' }} />}
        placeholder="搜索会话"
        value={keyword}
        onChange={(e) => onSearch(e.target.value)}
        aria-label="搜索会话"
      />

      <nav className="session-list" aria-label="会话列表">
        {loading && sessions.length === 0 ? (
          <div className="session-empty"><Spin size="small" /></div>
        ) : groups.length === 0 ? (
          <div className="session-empty">{keyword ? '没有匹配的会话' : '还没有会话，点击上方新建'}</div>
        ) : (
          groups.map((g) => (
            <section key={g.key} aria-label={GROUP_LABELS[g.key]}>
              <div className="session-group-label">{GROUP_LABELS[g.key]}</div>
              {g.items.map((s) => (
                <SessionItem
                  key={s.id}
                  session={s}
                  active={s.id === activeId}
                  streaming={s.id === streamingSession}
                  onSelect={setActive}
                  onRename={(id, t) => run(() => rename(id, t))}
                  onTogglePin={(id) => run(() => togglePin(id))}
                  onDelete={(id) =>
                    run(async () => {
                      await remove(id)
                      dropMessages(id)
                    }, '已删除')
                  }
                />
              ))}
            </section>
          ))
        )}
      </nav>

      <div className="sidebar-footer">
        <BackendStatus />
        {USE_MOCK && <span className="mock-tag" title="VITE_USE_MOCK=true">MOCK</span>}
      </div>
    </div>
  )
}
