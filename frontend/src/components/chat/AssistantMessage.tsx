import { BarChartOutlined, ReloadOutlined, RobotOutlined, StopOutlined, WarningOutlined } from '@ant-design/icons'
import { Button } from 'antd'
import type { ChatMessage } from '../../types'
import { MarkdownText } from './MarkdownText'
import { SqlBlock } from './SqlBlock'
import { StepTimeline } from './StepTimeline'

interface Props {
  message: ChatMessage
  chartActive: boolean
  onShowChart: (id: string) => void
  onRetry: (id: string) => void
}

export function AssistantMessage({ message: m, chartActive, onShowChart, onRetry }: Props) {
  const streaming = m.status === 'streaming'
  const thinking = streaming && !m.content && m.steps.length === 0

  return (
    <div className="msg msg-ai" data-testid={`msg-${m.id}`}>
      <div className={`avatar avatar-ai${streaming ? ' live' : ''}`} aria-hidden><RobotOutlined /></div>
      <div className="bubble-ai">
        {thinking && (
          <div className="thinking" aria-label="思考中">
            <span /><span /><span />
          </div>
        )}

        <StepTimeline steps={m.steps} />

        {m.sql && <SqlBlock sql={m.sql} attempts={m.attempts} />}

        {(m.hasChart || m.rowCount !== null) && (
          <div className="result-row">
            {m.rowCount !== null && <span className="badge">共 <b className="tabular">{m.rowCount}</b> 行</span>}
            {m.hasChart && (
              <button
                type="button"
                className={`result-badge${chartActive ? ' active' : ''}`}
                onClick={() => onShowChart(m.id)}
                aria-pressed={chartActive}
              >
                <BarChartOutlined /> {chartActive ? '正在右侧展示' : '查看图表'}
              </button>
            )}
          </div>
        )}

        {m.content && <MarkdownText text={m.content} streaming={streaming} />}

        {m.status === 'error' && m.error && (
          <div className="error-card" role="alert">
            <WarningOutlined />
            <div className="error-body">
              <div className="error-title">处理失败</div>
              <div className="error-msg">{m.error.message}</div>
            </div>
            {m.error.retryable && m.question && (
              <Button size="small" icon={<ReloadOutlined />} onClick={() => onRetry(m.id)}>重试</Button>
            )}
          </div>
        )}

        {m.status === 'cancelled' && (
          <div className="cancelled-note"><StopOutlined /> 已停止生成</div>
        )}

        {m.status === 'done' && m.elapsedMs !== null && (
          <div className="msg-meta tabular">耗时 {(m.elapsedMs / 1000).toFixed(1)}s</div>
        )}
      </div>
    </div>
  )
}
