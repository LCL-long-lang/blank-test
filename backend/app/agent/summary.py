"""查询结果摘要（纯函数）：明细数据不回传给模型，只给摘要。"""
from typing import Any

from app.db.business import QueryResult


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.4f}".rstrip("0").rstrip(".") if abs(v) < 1 else f"{v:,.2f}"
    return "NULL" if v is None else str(v)


def _table(columns: list[str], rows: list[list[Any]]) -> str:
    lines = [" | ".join(columns)]
    lines += [" | ".join(_fmt(v) for v in r) for r in rows]
    return "\n".join(lines)


def _numeric_stats(columns: list[str], rows: list[list[Any]]) -> list[str]:
    stats = []
    for i, name in enumerate(columns):
        values = [r[i] for r in rows if isinstance(r[i], (int, float)) and not isinstance(r[i], bool)]
        if values and len(values) == len([r for r in rows if r[i] is not None]):
            stats.append(f"{name}：最小 {_fmt(min(values))}，最大 {_fmt(max(values))}，"
                         f"合计 {_fmt(sum(values))}，平均 {_fmt(sum(values) / len(values))}")
    return stats


def insight_summary(result: QueryResult, head: int = 20) -> str:
    """给结果解读用：行数、数值列统计、前 head 行。"""
    parts = [f"共 {result.total} 行{'（已截断）' if result.truncated else ''}，列：{', '.join(result.columns)}"]
    stats = _numeric_stats(result.columns, result.rows)
    if stats and result.total > 1:
        parts.append("数值列统计（基于全部返回行）：\n" + "\n".join(stats))
    shown = result.rows[:head]
    parts.append(f"前 {len(shown)} 行：\n" + _table(result.columns, shown))
    return "\n\n".join(parts)


def memory_summary(result: QueryResult, head: int = 5) -> str:
    """给上下文记忆用：列名 + 行数 + 前 head 行，尽量短。"""
    shown = result.rows[:head]
    more = f"\n……共 {result.total} 行" if result.total > head else ""
    return f"{result.total} 行；" + _table(result.columns, shown) + more
