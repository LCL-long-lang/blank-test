import { describe, expect, it } from 'vitest'
import { themeOption } from './echartsTheme'
import { SERIES } from './tokens'

describe('themeOption', () => {
  it('只改外观不改数据：线宽 2px、柱宽 ≤ 24、系列色固定顺序', () => {
    const data = [1, 2, 3]
    const out = themeOption({
      title: { text: 't' },
      legend: { top: 28 },
      xAxis: { type: 'category', data: ['a', 'b', 'c'] },
      yAxis: { type: 'value' },
      series: [{ name: 's1', type: 'line', data }, { name: 's2', type: 'bar', data }],
    })
    const series = out.series as Array<Record<string, any>>
    expect(series[0].data).toBe(data)
    expect(series[0].lineStyle.width).toBe(2)
    expect(series[0].areaStyle).toBeUndefined() // 多系列不加面积
    expect(series[1].barMaxWidth).toBe(24)
    expect(series[1].itemStyle.borderRadius).toEqual([4, 4, 0, 0])
    expect(out.color).toEqual(SERIES)
    expect((out.title as any).show).toBe(false)
    expect((out.yAxis as any).splitLine.lineStyle.type).toBe('solid')
  })

  it('单系列折线加渐变面积；堆叠柱不加圆角', () => {
    const line = themeOption({ series: [{ type: 'line', data: [1] }] })
    expect((line.series as any)[0].areaStyle).toBeDefined()
    const stacked = themeOption({ series: [{ type: 'bar', stack: 'total', data: [1] }] })
    expect((stacked.series as any)[0].itemStyle.borderRadius).toBe(0)
  })
})
