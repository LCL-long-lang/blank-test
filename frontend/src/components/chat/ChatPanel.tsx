import { MessageOutlined } from '@ant-design/icons'
import { App, Spin } from 'antd'
import { useEffect } from 'react'
import { useChartStore } from '../../stores/chartStore'
import { useChatStore } from '../../stores/chatStore'
import { useSessionStore } from '../../stores/sessionStore'
import type { ChatMessage } from '../../types'
import { ChatInput } from './ChatInput'
import { MessageList } from './MessageList'
import { WelcomeView } from './WelcomeView'
import './Chat.css'

const EMPTY: ChatMessage[] = []

export function ChatPanel() {
  const { message } = App.useApp()
  const activeId = useSessionStore((s) => s.activeId)
  const title = useSessionStore((s) => s.sessions.find((x) => x.id === s.activeId)?.title)
  const createSession = useSessionStore((s) => s.create)
  const messages = useChatStore((s) => (activeId ? s.messages[activeId] ?? EMPTY : EMPTY))
  const loading = useChatStore((s) => s.loadingSession === activeId && activeId !== null)
  const streaming = useChatStore((s) => s.streaming)
  const { load, send, stop, retry } = useChatStore.getState()
  const activeChartId = useChartStore((s) => s.activeId)
  const showChart = useChartStore((s) => s.load)

  useEffect(() => {
    if (activeId) void load(activeId)
    else useChartStore.getState().reset()
  }, [activeId, load])

  const ask = async (q: string) => {
    if (streaming) {
      message.warning('上一个问题还在生成中')
      return
    }
    let sid = activeId
    if (!sid) {
      try {
        sid = (await createSession()).id
      } catch (e) {
        message.error((e as Error).message)
        return
      }
    }
    void send(sid, q)
  }

  const busyHere = streaming !== null && streaming.sessionId === activeId
  const busyElsewhere = streaming !== null && !busyHere

  return (
    <section className="panel chat-panel" data-testid="panel-chat" aria-label="问答区域">
      <header className="panel-header">
        <MessageOutlined className="panel-header-icon" />
        <span className="panel-title">问答区域</span>
        {title && <span className="panel-subtitle" title={title}>· {title}</span>}
      </header>

      {loading && messages.length === 0 ? (
        <div className="panel-center"><Spin /></div>
      ) : messages.length === 0 ? (
        <WelcomeView onAsk={ask} disabled={busyElsewhere} />
      ) : (
        <MessageList
          messages={messages}
          activeChartId={activeChartId}
          onShowChart={(id) => void showChart(id)}
          onRetry={(id) => activeId && void retry(activeId, id)}
        />
      )}

      <div className="chat-input-wrap">
        {busyElsewhere && <div className="busy-tip">另一个会话正在生成，完成后才能继续提问</div>}
        <ChatInput streaming={busyHere} disabled={busyElsewhere} onSend={ask} onStop={stop} />
      </div>
    </section>
  )
}
