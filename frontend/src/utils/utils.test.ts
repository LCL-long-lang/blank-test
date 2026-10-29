import { describe, expect, it } from 'vitest'
import type { Session } from '../types'
import { compactNumber, formatNumber, groupSessions, localStamp, parseStamp, toCsv } from './format'
import { parseBlocks, parseInline } from './markdown'
import { prettySql, tokenizeSql } from './sql'

const s = (id: string, updated: string, pinned = false): Session => ({
  id, title: id, pinned, created_at: updated, updated_at: updated,
})

describe('groupSessions', () => {
  it('按 置顶 / 今天 / 近 7 天 / 更早 分组，空组不出现', () => {
    const now = new Date('2026-10-13T15:00:00')
    const groups = groupSessions(
      [s('p', '2025-01-01 00:00:00', true), s('t', '2026-10-13 09:00:00.123456'), s('w', '2026-10-08 10:00:00'), s('e', '2026-09-01 10:00:00')],
      now,
    )
    expect(groups.map((g) => [g.key, g.items.map((x) => x.id)])).toEqual([
      ['pinned', ['p']], ['today', ['t']], ['week', ['w']], ['earlier', ['e']],
    ])
    expect(groupSessions([s('t', '2026-10-13 01:00:00')], now).map((g) => g.key)).toEqual(['today'])
  })
})

describe('localStamp', () => {
  it('输出本地时间而不是 UTC，与后端格式一致', () => {
    const d = new Date(2026, 9, 13, 1, 5, 9) // 本地 2026-10-13 01:05:09
    expect(localStamp(d)).toBe('2026-10-13 01:05:09')
    expect(parseStamp(localStamp(d)).getTime()).toBe(d.getTime())
  })
})

describe('数字格式', () => {
  it('千分位 / 压缩 / 比例', () => {
    expect(formatNumber(1234567.891)).toBe('1,234,567.89')
    expect(formatNumber(null)).toBe('—')
    expect(compactNumber(2_946_923.8)).toBe('294.69万')
    expect(compactNumber(1.23e8)).toBe('1.23亿')
    expect(compactNumber(0.595)).toBe('59.5%')
    expect(compactNumber(820)).toBe('820')
  })
})

describe('toCsv', () => {
  it('转义逗号、引号和换行', () => {
    expect(toCsv(['a', 'b'], [['x,y', 'say "hi"'], [1, null]])).toBe('a,b\r\n"x,y","say ""hi"""\r\n1,')
  })
})

describe('markdown', () => {
  it('段落、无序 / 有序列表', () => {
    const b = parseBlocks('结论\n\n- 第一\n- 第二\n1. 甲\n2) 乙')
    expect(b).toEqual([
      { type: 'p', lines: ['结论'] },
      { type: 'ul', items: ['第一', '第二'] },
      { type: 'ol', items: ['甲', '乙'] },
    ])
  })
  it('行内加粗和代码；HTML 原样保留为文本', () => {
    expect(parseInline('华东 **9.2M** 占 `53%` <b>x</b>')).toEqual([
      { text: '华东 ', kind: null }, { text: '9.2M', kind: 'strong' }, { text: ' 占 ', kind: null },
      { text: '53%', kind: 'code' }, { text: ' <b>x</b>', kind: null },
    ])
  })
  it('流式中未闭合的 ** 不吞文字', () => {
    expect(parseInline('销售额 **9.2')).toEqual([{ text: '销售额 **9.2', kind: null }])
  })
})

describe('sql', () => {
  it('主要子句前换行', () => {
    expect(prettySql('SELECT a FROM t WHERE x = 1 AND y = 2 GROUP BY a LIMIT 10')).toBe(
      'SELECT a\nFROM t\nWHERE x = 1\n  AND y = 2\nGROUP BY a\nLIMIT 10',
    )
  })
  it('识别关键字、字符串、数字', () => {
    const kinds = tokenizeSql("SELECT name FROM t WHERE s = 'it''s' LIMIT 5").filter((t) => t.kind).map((t) => [t.kind, t.text])
    expect(kinds).toEqual([['kw', 'SELECT'], ['kw', 'FROM'], ['kw', 'WHERE'], ['str', "'it''s'"], ['kw', 'LIMIT'], ['num', '5']])
  })
})
