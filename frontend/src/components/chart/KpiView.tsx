import type { EChartsOption } from '../../types'
import { compactNumber, formatNumber } from '../../utils/format'

interface KpiItem {
  label: string
  value: number | null
}

/** 后端 kind='kpi' 的 option：{ items: [{label, value}] }。单个指标即“主数字”，按 dataviz 只放一个 */
export function KpiView({ option, title }: { option: EChartsOption; title: string }) {
  const items = (option.items as KpiItem[] | undefined) ?? []
  const [hero, ...rest] = items
  if (!hero) return <div className="chart-empty-inline">没有可展示的指标</div>
  return (
    <div className="kpi">
      <div className="kpi-label">{title}</div>
      <div className="kpi-hero" title={formatNumber(hero.value)}>
        {hero.value === null ? '—' : compactNumber(hero.value)}
      </div>
      <div className="kpi-exact tabular">{hero.label} = {formatNumber(hero.value)}</div>
      {rest.length > 0 && (
        <div className="kpi-grid">
          {rest.map((it) => (
            <div key={it.label} className="kpi-tile">
              <div className="kpi-tile-label">{it.label}</div>
              <div className="kpi-tile-value">{it.value === null ? '—' : compactNumber(it.value)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
