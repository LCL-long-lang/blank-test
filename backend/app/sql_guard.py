"""SQL 安全校验（三道防线中的第三道，纯函数，不访问数据库）。

规则：
1. 去掉 Markdown 代码块包裹和结尾分号
2. 只允许 1 条语句
3. 根节点必须是查询（SELECT / UNION / INTERSECT / EXCEPT，WITH 包含在内）
4. 不能出现写操作、DDL、PRAGMA、ATTACH 等节点
5. 用到的表（排除 CTE 名）必须在白名单里，且不能跨库引用
6. 没有 LIMIT 时补上 LIMIT max_rows；LIMIT 超过上限时压到上限
"""
import re
from collections.abc import Iterable

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from app.common.errors import SQLGuardError

DIALECT = "sqlite"

_FORBIDDEN = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge,
    exp.Create, exp.Drop, exp.Alter, exp.TruncateTable,
    exp.Pragma, exp.Attach, exp.Detach, exp.Command,
    exp.Transaction, exp.Commit, exp.Rollback, exp.Into,
    exp.Set, exp.Use, exp.Analyze,
)
_QUERY_ROOTS = (exp.Select, exp.SetOperation)

_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*\n?(.*?)\n?```\s*$", re.S)


def strip_sql(text: str) -> str:
    """去掉 ```sql ... ``` 包裹、首尾空白和结尾分号。"""
    m = _FENCE_RE.match(text)
    sql = m.group(1) if m else text
    return sql.strip().rstrip(";").strip()


def _cte_names(tree: exp.Expression) -> set[str]:
    return {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}


def _apply_limit(tree: exp.Expression, max_rows: int) -> exp.Expression:
    limit = tree.args.get("limit")
    if limit is None:
        return tree.limit(max_rows)
    value = limit.expression
    if isinstance(value, exp.Literal) and not value.is_string and int(value.this) <= max_rows:
        return tree
    # LIMIT 过大或不是常量（如子查询）时一律压到上限
    limit.set("expression", exp.Literal.number(max_rows))
    return tree


def validate_and_rewrite(sql: str, allowed_tables: Iterable[str], max_rows: int) -> str:
    """校验通过返回改写后的 SQL（已补 LIMIT），否则抛 SQLGuardError，错误信息会回传给模型用于纠错。"""
    cleaned = strip_sql(sql)
    if not cleaned:
        raise SQLGuardError("SQL 为空")

    try:
        statements = [s for s in sqlglot.parse(cleaned, read=DIALECT) if s is not None]
    except ParseError as exc:
        raise SQLGuardError(f"SQL 解析失败：{exc}") from exc

    if len(statements) != 1:
        raise SQLGuardError("只允许执行一条 SQL 语句")
    tree = statements[0]

    if not isinstance(tree, _QUERY_ROOTS):
        raise SQLGuardError("只允许查询语句（SELECT），不允许修改数据或结构")

    for node in tree.walk():
        if isinstance(node, _FORBIDDEN):
            raise SQLGuardError(f"SQL 中包含不允许的操作：{type(node).__name__.upper()}")

    allowed = {t.lower() for t in allowed_tables}
    ctes = _cte_names(tree)
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        if not name:
            continue  # 表值函数等
        if table.args.get("db") or table.args.get("catalog"):
            raise SQLGuardError(f"不允许跨库引用表：{table.sql(dialect=DIALECT)}")
        if name in ctes:
            continue
        if name not in allowed:
            raise SQLGuardError(f"表 {table.name} 不存在或不允许访问，可用的表：{', '.join(sorted(allowed))}")

    return _apply_limit(tree, max_rows).sql(dialect=DIALECT)
