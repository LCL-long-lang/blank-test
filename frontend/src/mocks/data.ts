/** Mock 数据：结构与后端真实返回一致（取自 Phase 2 的真实响应并精简） */
import type { ChartSpec, EChartsOption, SchemaOut } from '../types'
import type { Cell } from '../types'

export interface MockScenario {
  /** 命中关键词即使用该场景 */
  match: RegExp
  rewritten: string
  sql: string
  /** 第一次生成的错误 SQL：存在时模拟“自动修正”（attempt=2） */
  badSql?: { sql: string; error: string }
  columns: string[]
  rows: Cell[][]
  spec: ChartSpec
  option: EChartsOption
  answer: string
  title: string
}

const MONTHS = ['2026-05', '2026-06', '2026-07', '2026-08', '2026-09', '2026-10']
const CATEGORIES = ['手机数码', '家用电器', '服装鞋包', '美妆个护']
const BASE = [980_000, 640_000, 310_000, 220_000]
const WAVE = [1.0, 1.35, 0.92, 0.98, 1.06, 0.88]

const trendRows: Cell[][] = MONTHS.flatMap((m, i) =>
  CATEGORIES.map((c, j) => [m, c, Math.round(BASE[j] * WAVE[i] * (1 + j * 0.03 * i))]),
)

function lineOption(): EChartsOption {
  return {
    title: { text: '近 6 个月各品类销售额趋势' },
    tooltip: { trigger: 'axis' },
    legend: { top: 28, type: 'scroll' },
    xAxis: { type: 'category', data: MONTHS, boundaryGap: false },
    yAxis: { type: 'value' },
    series: CATEGORIES.map((c) => ({
      name: c,
      type: 'line',
      smooth: true,
      data: trendRows.filter((r) => r[1] === c).map((r) => r[2]),
    })),
  }
}

const memberRows: Cell[][] = [
  ['普通', 1190],
  ['银卡', 498],
  ['金卡', 234],
  ['钻石', 78],
]

const regionRows: Cell[][] = [
  ['华东', 9_213_071.66],
  ['华南', 6_026_578.19],
  ['华北', 5_102_334.2],
  ['华中', 3_410_220.75],
  ['西南', 2_250_116.4],
  ['东北', 1_161_816.42],
  ['西北', 1_185_539.9],
].sort((a, b) => (b[1] as number) - (a[1] as number))

export const SCENARIOS: MockScenario[] = [
  {
    match: /占比|会员/,
    rewritten: '各会员等级的客户数量占比',
    sql: 'SELECT member_level, COUNT(*) AS customer_count FROM customers GROUP BY member_level ORDER BY customer_count DESC LIMIT 1000',
    columns: ['member_level', 'customer_count'],
    rows: memberRows,
    spec: { chart_type: 'pie', title: '各会员等级的客户占比', x_field: 'member_level', y_fields: ['customer_count'], series_field: null, sort: null },
    option: {
      title: { text: '各会员等级的客户占比' },
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: { top: 28, type: 'scroll' },
      series: [{ name: 'customer_count', type: 'pie', radius: ['35%', '65%'], center: ['50%', '58%'],
        data: memberRows.map(([name, value]) => ({ name, value })), label: { formatter: '{b}\n{d}%' } }],
    },
    answer: '普通会员占比最高，达 **59.50%**（1,190 人），钻石会员仅 **3.90%**。\n\n- 普通与银卡合计 **84.40%**，是客户主体\n- 高价值会员稀缺，建议重点关注留存',
    title: '会员等级占比',
  },
  {
    match: /上个月|总销售额/,
    rewritten: '上个月的总销售额',
    sql: "SELECT ROUND(SUM(oi.quantity * oi.unit_price), 2) AS sales FROM orders AS o JOIN order_items AS oi ON oi.order_id = o.order_id WHERE o.status = 'completed' AND STRFTIME('%Y-%m', o.order_date) = STRFTIME('%Y-%m', DATE('now', 'start of month', '-1 month')) LIMIT 1000",
    columns: ['sales'],
    rows: [[2_946_923.8]],
    spec: { chart_type: 'kpi', title: '上个月的总销售额是多少', x_field: null, y_fields: ['sales'], series_field: null, sort: null },
    option: { kind: 'kpi', title: { text: '上个月的总销售额是多少' }, items: [{ label: 'sales', value: 2_946_923.8 }] },
    answer: '上个月总销售额为 **2,946,923.80** 元，单月营收接近 300 万。',
    title: '上月销售额',
  },
  {
    match: /大区|区域|排名/,
    rewritten: '今年各大区的销售额排名',
    sql: "SELECT r.region_name, ROUND(SUM(o.total_amount), 2) AS sales FROM orders AS o JOIN customers AS c ON c.customer_id = o.customer_id JOIN regions AS r ON r.region_id = c.region_id WHERE o.status = 'completed' GROUP BY r.region_name ORDER BY sales DESC LIMIT 1000",
    badSql: {
      sql: "SELECT region, SUM(total_amount) AS sales FROM orders GROUP BY region LIMIT 1000",
      error: 'no such column: region',
    },
    columns: ['region_name', 'sales'],
    rows: regionRows,
    spec: { chart_type: 'bar', title: '今年各大区的销售额排名', x_field: 'region_name', y_fields: ['sales'], series_field: null, sort: 'desc' },
    option: {
      title: { text: '今年各大区的销售额排名' },
      tooltip: { trigger: 'axis' },
      legend: { show: false },
      xAxis: { type: 'category', data: regionRows.map((r) => r[0]) },
      yAxis: { type: 'value' },
      series: [{ name: 'sales', type: 'bar', data: regionRows.map((r) => r[1]) }],
    },
    answer: '今年销售额 **华东第一**，西北、东北垫底。\n\n1. 华东与华南合计占比约 **53.8%**\n2. 西北仅为华东的 **12.9%**，区域发展不均衡',
    title: '大区销售排名',
  },
  {
    match: /.*/,
    rewritten: '近 6 个月各品类销售额趋势',
    sql: "SELECT STRFTIME('%Y-%m', o.order_date) AS month, c.category_name, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS sales FROM orders AS o JOIN order_items AS oi ON oi.order_id = o.order_id JOIN products AS p ON p.product_id = oi.product_id JOIN categories AS c ON c.category_id = p.category_id WHERE o.status = 'completed' AND o.order_date >= DATE('now', 'start of month', '-5 months') GROUP BY month, c.category_name ORDER BY month, c.category_name LIMIT 1000",
    columns: ['month', 'category_name', 'sales'],
    rows: trendRows,
    spec: { chart_type: 'line', title: '近 6 个月各品类销售额趋势', x_field: 'month', y_fields: ['sales'], series_field: 'category_name', sort: null },
    option: lineOption(),
    answer: '近 6 个月 **手机数码** 始终领先，**2026-06** 受 618 带动达到峰值。\n\n- 家用电器稳居第二\n- 7 月整体回落，随后逐步回升',
    title: '品类销售趋势',
  },
]

export const MOCK_SCHEMA: SchemaOut = {
  tables: [
    { name: 'orders', label: '订单', description: '订单主表', row_count: 20000, columns: [] },
    { name: 'order_items', label: '订单明细', description: '', row_count: 35223, columns: [] },
    { name: 'products', label: '商品', description: '', row_count: 200, columns: [] },
    { name: 'categories', label: '品类', description: '', row_count: 8, columns: [] },
    { name: 'customers', label: '客户', description: '', row_count: 2000, columns: [] },
    { name: 'regions', label: '地区', description: '', row_count: 29, columns: [] },
  ],
  examples: [
    '近 6 个月各品类销售额趋势',
    '今年各大区的销售额排名',
    '各会员等级的客户占比',
    '上个月的总销售额是多少？',
  ],
}
