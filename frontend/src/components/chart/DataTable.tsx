import { Table } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useMemo } from 'react'
import type { Cell } from '../../types'
import { formatNumber } from '../../utils/format'

type Row = Record<string, Cell> & { __key: number }

/** 数据表：图表的“表格视图”，每个值都能不依赖悬停读到 */
export function DataTable({ columns, rows, height }: { columns: string[]; rows: Cell[][]; height?: number }) {
  const data = useMemo<Row[]>(
    () => rows.map((r, i) => Object.fromEntries([...columns.map((c, j) => [c, r[j]]), ['__key', i]]) as Row),
    [columns, rows],
  )
  const cols = useMemo<ColumnsType<Row>>(
    () =>
      columns.map((c, j) => {
        const numeric = rows.length > 0 && rows.every((r) => r[j] === null || typeof r[j] === 'number')
        return {
          title: c,
          dataIndex: c,
          key: c,
          align: numeric ? 'right' : 'left',
          className: numeric ? 'tabular' : undefined,
          ellipsis: true,
          sorter: numeric
            ? (a: Row, b: Row) => ((a[c] as number) ?? 0) - ((b[c] as number) ?? 0)
            : (a: Row, b: Row) => String(a[c] ?? '').localeCompare(String(b[c] ?? ''), 'zh-CN'),
          render: (v: Cell) => formatNumber(v),
        }
      }),
    [columns, rows],
  )
  return (
    <Table<Row>
      className="data-table"
      size="small"
      rowKey="__key"
      columns={cols}
      dataSource={data}
      pagination={data.length > 50 ? { pageSize: 50, size: 'small', showSizeChanger: false } : false}
      scroll={{ x: 'max-content', y: height }}
    />
  )
}
