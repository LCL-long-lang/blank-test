/**
 * 前端统一覆盖后端 option 的“外观”部分（颜色、坐标轴、提示框、线宽、柱宽），不改数据。
 * 规则来自 dataviz：线宽 2px、柱宽 ≤ 24px 且顶端圆角 4px、网格线 1px 实线、坐标轴文字用文本色而非系列色。
 */
import type { EChartsOption } from '../types'
import { SERIES, colors } from './tokens'

type Obj = Record<string, unknown>
const asArray = (v: unknown): Obj[] => (Array.isArray(v) ? (v as Obj[]) : v ? [v as Obj] : [])

const axisStyle = {
  axisLine: { lineStyle: { color: colors.axis } },
  axisTick: { show: false },
  axisLabel: { color: colors.textMuted, fontSize: 11 },
  splitLine: { lineStyle: { color: colors.grid, width: 1, type: 'solid' } },
  nameTextStyle: { color: colors.textMuted },
}

function styleSeries(s: Obj, idx: number, total: number): Obj {
  const color = SERIES[idx % SERIES.length]
  switch (s.type) {
    case 'line':
      return {
        ...s,
        symbol: 'circle',
        symbolSize: 7,
        showSymbol: false,
        lineStyle: { width: 2, cap: 'round', join: 'round' },
        itemStyle: { borderColor: colors.surface, borderWidth: 2 },
        emphasis: { focus: 'series' },
        // 单系列加一层 10% 透明度的面积，多系列不加（避免叠色）
        ...(total === 1
          ? { areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [{ offset: 0, color: `${color}33` }, { offset: 1, color: `${color}00` }] } } }
          : {}),
      }
    case 'bar': {
      const stacked = Boolean(s.stack)
      return {
        ...s,
        barMaxWidth: 24,
        itemStyle: { borderRadius: stacked ? 0 : [4, 4, 0, 0], borderColor: colors.surface, borderWidth: stacked ? 1 : 0 },
        emphasis: { focus: 'series' },
      }
    }
    case 'pie':
      return {
        ...s,
        itemStyle: { borderColor: colors.surface, borderWidth: 2, borderRadius: 4 },
        label: { ...(s.label as Obj), color: colors.textSecondary },
        labelLine: { lineStyle: { color: colors.axis } },
      }
    case 'scatter':
      return { ...s, symbolSize: 9, itemStyle: { borderColor: colors.surface, borderWidth: 2, opacity: 0.9 } }
    default:
      return s
  }
}

export function themeOption(option: EChartsOption): EChartsOption {
  const series = asArray(option.series)
  const title = option.title as Obj | undefined
  const legend = option.legend as Obj | undefined
  return {
    ...option,
    backgroundColor: 'transparent',
    color: SERIES,
    textStyle: { fontFamily: 'inherit', color: colors.textSecondary },
    // 标题由面板头部展示，图表内隐藏，留出空间
    title: { ...title, show: false },
    legend: legend
      ? { ...legend, top: 4, textStyle: { color: colors.textSecondary }, icon: 'roundRect', itemWidth: 12, itemHeight: 4,
          pageTextStyle: { color: colors.textMuted }, pageIconColor: colors.accent, pageIconInactiveColor: colors.axis }
      : legend,
    grid: option.grid ? { ...(option.grid as Obj), top: legend && legend.show !== false ? 40 : 16 } : option.grid,
    tooltip: {
      ...(option.tooltip as Obj),
      backgroundColor: 'rgba(10, 16, 30, 0.94)',
      borderColor: colors.borderStrong,
      borderWidth: 1,
      textStyle: { color: colors.text, fontSize: 12 },
      extraCssText: 'box-shadow: 0 0 24px rgba(56,219,255,0.18); border-radius: 8px; backdrop-filter: blur(6px);',
      axisPointer: { type: 'line', lineStyle: { color: colors.borderStrong, width: 1 } },
    },
    xAxis: asArray(option.xAxis).map((a) => ({ ...a, ...axisStyle, splitLine: { show: false } }))[0] ?? option.xAxis,
    yAxis: asArray(option.yAxis).map((a) => ({ ...a, ...axisStyle }))[0] ?? option.yAxis,
    series: series.map((s, i) => styleSeries(s, i, series.length)),
    dataZoom: asArray(option.dataZoom).map((z) =>
      z.type === 'slider'
        ? { ...z, borderColor: colors.axis, fillerColor: 'rgba(56,219,255,0.12)', handleStyle: { color: colors.accent },
            textStyle: { color: colors.textMuted }, dataBackground: { lineStyle: { color: colors.axis }, areaStyle: { color: colors.grid } } }
        : z,
    ),
    animationDuration: 600,
    animationEasing: 'cubicOut',
  }
}
