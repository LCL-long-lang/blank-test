/** SQL 只读高亮（不引入第三方高亮库）。全部生成 React 节点，不使用 innerHTML */
import { prettySql, tokenizeSql } from '../../utils/sql'

export function SqlCode({ sql, pretty = true }: { sql: string; pretty?: boolean }) {
  const tokens = tokenizeSql(pretty ? prettySql(sql) : sql)
  return (
    <pre className="sql-code">
      <code>
        {tokens.map((t, i) => (t.kind ? <span key={i} className={`tok-${t.kind}`}>{t.text}</span> : t.text))}
      </code>
    </pre>
  )
}
