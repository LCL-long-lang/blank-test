import { UserOutlined } from '@ant-design/icons'
import { useEffect, useLayoutEffect, useRef } from 'react'
import type { ChatMessage } from '../../types'
import { AssistantMessage } from './AssistantMessage'

interface Props {
  messages: ChatMessage[]
  activeChartId: string | null
  onShowChart: (id: string) => void
  onRetry: (id: string) => void
}

/** 距离底部小于该值视为“在底部”，新内容到达时才自动滚动 */
const STICK_THRESHOLD = 80

export function MessageList({ messages, activeChartId, onShowChart, onRetry }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const stick = useRef(true)

  const onScroll = () => {
    const el = ref.current
    if (el) stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < STICK_THRESHOLD
  }

  // 切换会话时回到底部
  const firstId = messages[0]?.id
  useLayoutEffect(() => {
    stick.current = true
    const el = ref.current
    if (el) el.scrollTop = el.scrollHeight
  }, [firstId])

  // 流式内容更新：用户没有向上翻时跟随到底部
  const last = messages[messages.length - 1]
  useEffect(() => {
    const el = ref.current
    if (el && stick.current) el.scrollTop = el.scrollHeight
  }, [messages.length, last?.content, last?.steps.length, last?.status])

  return (
    <div className="message-list" ref={ref} onScroll={onScroll} role="log" aria-live="polite" aria-label="对话消息">
      <div className="message-list-inner">
        {messages.map((m) =>
          m.role === 'user' ? (
            <div key={m.id} className="msg msg-user">
              <div className="bubble-user">{m.content}</div>
              <div className="avatar avatar-user" aria-hidden><UserOutlined /></div>
            </div>
          ) : (
            <AssistantMessage
              key={m.id}
              message={m}
              chartActive={m.id === activeChartId}
              onShowChart={onShowChart}
              onRetry={onRetry}
            />
          ),
        )}
      </div>
    </div>
  )
}
