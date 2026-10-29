import {
  AreaChartOutlined, BarChartOutlined, DotChartOutlined, DownloadOutlined, FileImageOutlined,
  FullscreenExitOutlined, FullscreenOutlined, LineChartOutlined, NumberOutlined, PieChartOutlined, TableOutlined,
} from '@ant-design/icons'
import { Alert, App, Segmented, Spin, Tabs, Tooltip } from 'antd'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useChartStore } from '../../stores/chartStore'
import { useChatStore } from '../../stores/chatStore'
import type { Cell, ChartData, ChartType } from '../../types'
import { download, safeFilename, toCsv } from '../../utils/format'
import { SqlCode } from '../common/SqlCode'
import { ChartView, type ChartViewHandle } from './ChartView'
import { DataTable } from './DataTable'
import { KpiView } from './KpiView'
import './Chart.css'

const TYPE_OPTIONS: Array<{ value: ChartType; label: string; icon: ReactNode }> = [
  { value: 'line', label: '折线', icon: <LineChartOutlined /> },
  { value: 'bar', label: '柱状', icon: <BarChartOutlined /> },
  { value: 'stacked_bar', label: '堆叠', icon: <AreaChartOutlined /> },
  { value: 'pie', label: '饼图', icon: <PieChartOutlined /> },
  { value: 'scatter', label: '散点', icon: <DotChartOutlined /> },
  { value: 'kpi', label: '指标', icon: <NumberOutlined /> },
  { value: 'table', label: '表格', icon: <TableOutlined /> },
]

function ChartEmpty({ generating }: { generating: boolean }) {
  return (
    <div className="chart-empty" data-testid="chart-empty">
      <div className="empty-radar" aria-hidden />
      <div className="empty-title">{generating ? '正在分析数据…' : '等待查询结果'}</div>
      <div className="empty-sub">{generating ? '图表生成后会实时显示在这里' : '在中间提问，图表会实时渲染在这里'}</div>
    </div>
  )
}

interface ResultTabsProps {
  chartTab: ReactNode
  columns: string[]
  rows: Cell[][]
  sql: string | null
  tableHeight: number
}

function ResultTabs({ chartTab, columns, rows, sql, tableHeight }: ResultTabsProps) {
  const [tab, setTab] = useState('chart')
  return (
    <Tabs
      className="chart-tabs"
      activeKey={tab}
      onChange={setTab}
      items={[
        { key: 'chart', label: '图表', children: chartTab },
        {
          key: 'data',
          label: `数据表${columns.length ? ` · ${rows.length}` : ''}`,
          disabled: !columns.length,
          children: <div className="table-wrap"><DataTable columns={columns} rows={rows} height={tableHeight} /></div>,
        },
        {
          key: 'sql',
          label: 'SQL',
          disabled: !sql,
          children: sql ? <div className="sql-view"><SqlCode sql={sql} /></div> : null,
        },
      ]}
    />
  )
}

export function ChartPanel() {
  const { message } = App.useApp()
  const { activeId, charts, pendingData, loadingId, switching, error, switchType } = useChartStore()
  const streamingId = useChatStore((s) => s.streaming?.messageId ?? null)
  const sqlFromChat = useChatStore((s) => {
    if (!activeId) return null
    for (const list of Object.values(s.messages)) {
      const m = list.find((x) => x.id === activeId)
      if (m) return m.sql
    }
    return null
  })
  const [fullscreen, setFullscreen] = useState(false)
  const chartRef = useRef<ChartViewHandle>(null)

  const chart: ChartData | undefined = activeId ? charts[activeId] : undefined
  const pending = activeId && !chart ? pendingData[activeId] : undefined
  const generating = activeId !== null && activeId === streamingId && !chart
  const sql = chart?.sql ?? pending?.sql ?? sqlFromChat

  useEffect(() => {
    if (!fullscreen) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setFullscreen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [fullscreen])

  const exportPng = () => {
    const url = chartRef.current?.toDataURL()
    if (!url || !chart) return message.warning('当前视图不支持导出图片')
    const a = document.createElement('a')
    a.href = url
    a.download = `${safeFilename(chart.spec.title)}.png`
    a.click()
  }

  const exportCsv = () => {
    const cols = chart?.columns ?? pending?.columns
    const rows = chart?.rows ?? pending?.rows
    if (!cols?.length) return message.warning('没有可导出的数据')
    download(`${safeFilename(chart?.spec.title ?? '查询结果')}.csv`, toCsv(cols, rows ?? []))
  }

  const onSwitch = async (t: ChartType) => {
    try {
      await switchType(t)
    } catch (e) {
      message.warning((e as Error).message)
    }
  }

  const kind = chart?.option.kind
  const canvasType = chart && kind !== 'kpi' && kind !== 'table'

  let content: ReactNode
  if (!activeId || (!chart && !pending && !generating && loadingId !== activeId)) {
    content = <ChartEmpty generating={false} />
  } else if (loadingId === activeId && !chart) {
    content = <div className="chart-empty"><Spin /></div>
  } else {
    const columns = chart?.columns ?? pending?.columns ?? []
    const rows = chart?.rows ?? pending?.rows ?? []
    const seriesCount = Array.isArray(chart?.option.series) ? (chart.option.series as unknown[]).length : 0
    const chartTab = chart ? (
      // data-* 供端到端测试读取（canvas 内容无法直接断言）
      <div className="chart-frame" data-chart-type={chart.spec.chart_type} data-series-count={seriesCount}>
        {kind === 'kpi' ? (
          <KpiView option={chart.option} title={chart.spec.title} />
        ) : kind === 'table' ? (
          <div className="table-wrap"><DataTable columns={columns} rows={rows} /></div>
        ) : (
          <ChartView ref={chartRef} option={chart.option} dimmed={switching} />
        )}
      </div>
    ) : (
      <div className="chart-frame"><div className="scanline" /><ChartEmpty generating /></div>
    )
    // key：每次选中一条结果都重新挂载，标签页回到“图表”
    content = (
      <ResultTabs
        key={activeId}
        chartTab={chartTab}
        columns={columns}
        rows={rows}
        sql={sql}
        tableHeight={fullscreen ? 640 : 420}
      />
    )
  }

  return (
    <section className={`panel chart-panel${fullscreen ? ' fullscreen' : ''}`} data-testid="panel-chart" aria-label="可视化图表">
      <header className="panel-header">
        <BarChartOutlined className="panel-header-icon" />
        <span className="panel-title">可视化图表</span>
        <span className="spacer" />
        <Tooltip title="导出 PNG">
          <button type="button" className="icon-btn" aria-label="导出 PNG" disabled={!canvasType} onClick={exportPng}>
            <FileImageOutlined />
          </button>
        </Tooltip>
        <Tooltip title="导出 CSV">
          <button type="button" className="icon-btn" aria-label="导出 CSV" disabled={!chart && !pending} onClick={exportCsv}>
            <DownloadOutlined />
          </button>
        </Tooltip>
        <Tooltip title={fullscreen ? '退出全屏 (Esc)' : '全屏'}>
          <button type="button" className="icon-btn" aria-label={fullscreen ? '退出全屏' : '全屏'} onClick={() => setFullscreen((v) => !v)}>
            {fullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
          </button>
        </Tooltip>
      </header>

      {chart && (
        <>
          <div className="chart-title-bar">
            <div className="chart-title" data-testid="chart-title">{chart.spec.title}</div>
            <div className="chart-meta tabular">
              {chart.rows.length} 行{chart.truncated ? '（已截断）' : ''} · {chart.columns.join(' / ')}
            </div>
          </div>
          <div className="chart-toolbar">
            <Segmented<ChartType>
              size="small"
              value={chart.spec.chart_type}
              disabled={switching}
              onChange={onSwitch}
              options={TYPE_OPTIONS.map((o) => ({ value: o.value, label: <Tooltip title={o.label}><span aria-label={o.label}>{o.icon}</span></Tooltip> }))}
              aria-label="图表类型"
            />
            {switching && <Spin size="small" />}
          </div>
        </>
      )}

      {error && <Alert className="chart-error" type="warning" showIcon message={error} />}

      <div className="chart-body">{content}</div>
    </section>
  )
}
