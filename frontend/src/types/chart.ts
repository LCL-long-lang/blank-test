/** 对应 backend/app/common/schemas.py 的图表模型 */
export type ChartType = 'kpi' | 'line' | 'bar' | 'stacked_bar' | 'pie' | 'scatter' | 'table'

export type Cell = string | number | boolean | null

export interface ChartSpec {
  chart_type: ChartType
  title: string
  x_field: string | null
  y_fields: string[]
  series_field: string | null
  sort: 'asc' | 'desc' | null
}

/** ECharts option 由后端组装，前端原样传给 setOption */
export type EChartsOption = Record<string, unknown>

export interface ChartOut {
  message_id: string
  spec: ChartSpec
  option: EChartsOption
  columns: string[]
  rows: Cell[][]
}

export interface ChartRenderRequest {
  chart_type: ChartType
}
