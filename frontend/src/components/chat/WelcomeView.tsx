import { DatabaseOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { useEffect, useState } from 'react'
import { api } from '../../services'
import type { SchemaOut } from '../../types'

const FALLBACK_EXAMPLES = ['近 6 个月各品类销售额趋势', '今年各大区的销售额排名', '各会员等级的客户占比', '上个月的总销售额是多少？']

export function WelcomeView({ onAsk, disabled }: { onAsk: (q: string) => void; disabled?: boolean }) {
  const [schema, setSchema] = useState<SchemaOut | null>(null)

  useEffect(() => {
    let alive = true
    api.getSchema().then((s) => alive && setSchema(s)).catch(() => {})
    return () => {
      alive = false
    }
  }, [])

  const examples = schema?.examples.length ? schema.examples : FALLBACK_EXAMPLES

  return (
    <div className="welcome">
      <div className="welcome-orb" aria-hidden>
        <div className="orb-ring" />
        <div className="orb-ring r2" />
        <div className="orb-core"><ThunderboltOutlined /></div>
      </div>
      <h1 className="welcome-title">用一句话，洞察你的业务数据</h1>
      <p className="welcome-sub">自然语言 → SQL → 实时图表与解读，支持多轮追问</p>

      <div className="example-grid">
        {examples.map((q) => (
          <button key={q} type="button" className="example-card" disabled={disabled} onClick={() => onAsk(q)}>
            <span className="example-arrow" aria-hidden>›</span>
            {q}
          </button>
        ))}
      </div>

      {schema && (
        <div className="schema-chips" aria-label="可查询的数据表">
          <DatabaseOutlined />
          {schema.tables.map((t) => (
            <span key={t.name} className="chip" title={t.description || t.name}>
              {t.label || t.name}
              <em className="tabular">{t.row_count.toLocaleString('zh-CN')}</em>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
