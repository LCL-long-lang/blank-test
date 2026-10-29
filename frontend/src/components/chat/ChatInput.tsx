import { ArrowUpOutlined, PauseOutlined } from '@ant-design/icons'
import { Input, Tooltip } from 'antd'
import { useState } from 'react'

interface Props {
  streaming: boolean
  disabled?: boolean
  onSend: (q: string) => void
  onStop: () => void
}

export const MAX_QUESTION_LEN = 500

export function ChatInput({ streaming, disabled, onSend, onStop }: Props) {
  const [value, setValue] = useState('')
  const canSend = !streaming && !disabled && value.trim().length > 0

  const send = () => {
    if (!canSend) return
    onSend(value.trim())
    setValue('')
  }

  return (
    <div className={`chat-input${streaming ? ' busy' : ''}`}>
      <Input.TextArea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          // Enter 发送，Shift+Enter 换行；输入法组字中不触发
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault()
            send()
          }
        }}
        placeholder={disabled ? '请先在左侧新建或选择一个会话' : '用自然语言提问，例如：近 6 个月各品类销售额趋势'}
        autoSize={{ minRows: 1, maxRows: 6 }}
        maxLength={MAX_QUESTION_LEN}
        variant="borderless"
        disabled={disabled}
        aria-label="输入问题"
      />
      <div className="chat-input-bar">
        <span className="hint">Enter 发送 · Shift+Enter 换行</span>
        {streaming ? (
          <Tooltip title="停止生成">
            <button type="button" className="send-btn stop" aria-label="停止生成" onClick={onStop}>
              <PauseOutlined />
            </button>
          </Tooltip>
        ) : (
          <button type="button" className="send-btn" aria-label="发送" disabled={!canSend} onClick={send}>
            <ArrowUpOutlined />
          </button>
        )}
      </div>
    </div>
  )
}
