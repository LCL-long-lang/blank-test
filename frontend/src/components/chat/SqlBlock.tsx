import { CodeOutlined, CopyOutlined, DownOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { App, Tooltip } from 'antd'
import { useState } from 'react'
import type { SqlAttempt } from '../../types'
import { SqlCode } from '../common/SqlCode'

interface Props {
  sql: string
  attempts: SqlAttempt[]
}

/** 可折叠的 SQL 块；经过自动修正时显示标记 */
export function SqlBlock({ sql, attempts }: Props) {
  const { message } = App.useApp()
  const [open, setOpen] = useState(false)
  const fixed = attempts.length > 1

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(sql)
      message.success('SQL 已复制')
    } catch {
      message.error('复制失败，请手动选择复制')
    }
  }

  return (
    <div className={`sql-block${open ? ' open' : ''}`}>
      <div className="sql-head">
        <button type="button" className="sql-toggle" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          <CodeOutlined />
          <span>SQL</span>
          {fixed && (
            <span className="badge badge-warn" title={`共尝试 ${attempts.length} 次`}>
              <ThunderboltOutlined /> 已自动修正
            </span>
          )}
          <DownOutlined className="sql-caret" />
        </button>
        <Tooltip title="复制 SQL">
          <button type="button" className="icon-btn" aria-label="复制 SQL" onClick={copy}>
            <CopyOutlined />
          </button>
        </Tooltip>
      </div>
      {open && <SqlCode sql={sql} />}
    </div>
  )
}
