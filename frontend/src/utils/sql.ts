/** SQL 展示用的纯函数：格式化换行、按关键字 / 字符串 / 数字切分 token */

const KEYWORDS = new Set(
  ('select from where group by order having limit join left right inner outer full on as and or not in is null ' +
    'case when then else end with distinct union all asc desc between like exists over partition count sum avg ' +
    'min max round strftime date datetime cast coalesce ifnull')
    .split(' '),
)

/** 把单行 SQL 在主要子句前换行，便于阅读 */
export function prettySql(sql: string): string {
  return sql
    .replace(/\s+/g, ' ')
    .replace(/\s+(FROM|WHERE|GROUP BY|ORDER BY|HAVING|LIMIT|LEFT JOIN|RIGHT JOIN|INNER JOIN|JOIN|UNION ALL|UNION)\s+/gi, '\n$1 ')
    .replace(/\s+(AND|OR)\s+/gi, '\n  $1 ')
    .trim()
}

export type SqlToken = { text: string; kind: 'kw' | 'str' | 'num' | null }

export function tokenizeSql(sql: string): SqlToken[] {
  const re = /('(?:[^']|'')*'|"[^"]*"|\b\d+(?:\.\d+)?\b|\b[A-Za-z_]+\b)/g
  const out: SqlToken[] = []
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(sql))) {
    if (m.index > last) out.push({ text: sql.slice(last, m.index), kind: null })
    const t = m[0]
    const kind = t.startsWith("'") || t.startsWith('"') ? 'str' : /^\d/.test(t) ? 'num' : KEYWORDS.has(t.toLowerCase()) ? 'kw' : null
    out.push({ text: t, kind })
    last = m.index + t.length
  }
  if (last < sql.length) out.push({ text: sql.slice(last), kind: null })
  return out
}
