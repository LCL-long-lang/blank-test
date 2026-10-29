// 用 ESM 入口：lib/core 是 CommonJS，浏览器里默认导出会变成 { default } 对象导致渲染报错
import ReactEChartsCore from 'echarts-for-react/esm/core'
import type { EChartsInstance } from 'echarts-for-react'
import { forwardRef, useImperativeHandle, useMemo, useRef } from 'react'
import { themeOption } from '../../theme/echartsTheme'
import type { EChartsOption } from '../../types'
import { echarts } from './echarts'

export interface ChartViewHandle {
  /** 导出为 PNG data URL */
  toDataURL: () => string | null
}

/** 渲染后端 option（套上前端主题）；容器尺寸变化时自动 resize */
export const ChartView = forwardRef<ChartViewHandle, { option: EChartsOption; dimmed?: boolean }>(
  function ChartView({ option, dimmed }, ref) {
    const inst = useRef<EChartsInstance | null>(null)
    const themed = useMemo(() => themeOption(option), [option])

    useImperativeHandle(ref, () => ({
      toDataURL: () => inst.current?.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#0f1626' }) ?? null,
    }))

    return (
      <div className={`chart-canvas${dimmed ? ' dimmed' : ''}`} data-testid="chart-canvas">
        <ReactEChartsCore
          echarts={echarts}
          option={themed}
          notMerge
          lazyUpdate
          autoResize
          style={{ width: '100%', height: '100%' }}
          onChartReady={(i) => {
            inst.current = i
          }}
        />
      </div>
    )
  },
)
