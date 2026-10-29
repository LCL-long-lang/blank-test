import { DeleteOutlined, EditOutlined, MessageOutlined, PushpinFilled, PushpinOutlined } from '@ant-design/icons'
import { Input, Popconfirm, Tooltip, type InputRef } from 'antd'
import { useEffect, useRef, useState } from 'react'
import type { Session } from '../../types'

interface Props {
  session: Session
  active: boolean
  streaming: boolean
  onSelect: (id: string) => void
  onRename: (id: string, title: string) => Promise<void> | void
  onTogglePin: (id: string) => void
  onDelete: (id: string) => void
}

export function SessionItem({ session, active, streaming, onSelect, onRename, onTogglePin, onDelete }: Props) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(session.title)
  const inputRef = useRef<InputRef>(null)

  useEffect(() => {
    if (editing) inputRef.current?.focus({ cursor: 'all' })
  }, [editing])

  const commit = async () => {
    const t = draft.trim()
    setEditing(false)
    if (t && t !== session.title) await onRename(session.id, t)
    else setDraft(session.title)
  }

  if (editing) {
    return (
      <div className="session-item editing">
        <Input
          ref={inputRef}
          size="small"
          value={draft}
          maxLength={50}
          aria-label="会话名称"
          onChange={(e) => setDraft(e.target.value)}
          onPressEnter={commit}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              setDraft(session.title)
              setEditing(false)
            }
          }}
        />
      </div>
    )
  }

  return (
    <div
      className={`session-item${active ? ' active' : ''}`}
      role="button"
      tabIndex={0}
      aria-current={active ? 'true' : undefined}
      data-testid={`session-${session.id}`}
      onClick={() => onSelect(session.id)}
      onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onSelect(session.id)}
    >
      {streaming ? <span className="session-pulse" aria-label="生成中" /> : <MessageOutlined className="session-icon" />}
      <span className="session-title" title={session.title}>{session.title}</span>
      <span className="session-actions" onClick={(e) => e.stopPropagation()}>
        <Tooltip title={session.pinned ? '取消置顶' : '置顶'}>
          <button type="button" aria-label={session.pinned ? '取消置顶' : '置顶'} onClick={() => onTogglePin(session.id)}>
            {session.pinned ? <PushpinFilled /> : <PushpinOutlined />}
          </button>
        </Tooltip>
        <Tooltip title="重命名">
          <button type="button" aria-label="重命名" onClick={() => { setDraft(session.title); setEditing(true) }}>
            <EditOutlined />
          </button>
        </Tooltip>
        <Popconfirm
          title="删除这个会话？"
          description="会话中的消息和图表会一并删除"
          okText="删除"
          cancelText="取消"
          okButtonProps={{ danger: true }}
          onConfirm={() => onDelete(session.id)}
        >
          <button type="button" aria-label="删除" className="danger">
            <DeleteOutlined />
          </button>
        </Popconfirm>
      </span>
    </div>
  )
}
