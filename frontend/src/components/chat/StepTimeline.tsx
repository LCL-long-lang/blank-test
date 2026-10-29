import { CheckOutlined, CloseOutlined, LoadingOutlined } from '@ant-design/icons'
import type { StepView } from '../../types'

const ICON = {
  running: <LoadingOutlined />,
  done: <CheckOutlined />,
  error: <CloseOutlined />,
}

/** 处理步骤：每一步一个“节点胶囊”，状态由图标 + 文字表达（不只靠颜色） */
export function StepTimeline({ steps }: { steps: StepView[] }) {
  if (!steps.length) return null
  return (
    <ol className="steps" aria-label="处理步骤">
      {steps.map((s) => (
        <li key={s.key} className={`step step-${s.status}`} title={s.detail ?? undefined}>
          <span className="step-icon" aria-label={s.status === 'done' ? '完成' : s.status === 'error' ? '失败' : '进行中'}>
            {ICON[s.status]}
          </span>
          <span className="step-label">{s.label}</span>
          {s.detail && <span className="step-detail">{s.detail}</span>}
        </li>
      ))}
    </ol>
  )
}
