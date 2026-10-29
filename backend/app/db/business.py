"""业务库 business.db：只读访问。

三道防线中的前两道：文件级 mode=ro + 连接级 PRAGMA query_only（第三道是 sql_guard）。
每次查询新建连接，避免跨线程共享；超时用 progress handler 中断。
"""
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.common.errors import SQLExecError
from app.config import settings


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list[Any]]
    elapsed_ms: int
    truncated: bool = False
    total: int = field(init=False)

    def __post_init__(self) -> None:
        self.total = len(self.rows)


def connect_readonly(path: Path | None = None) -> sqlite3.Connection:
    """以只读模式打开业务库：文件级 mode=ro + 连接级 query_only 双重保护。"""
    db_path = Path(path or settings.business_db_path).resolve()
    if not db_path.exists():
        raise SQLExecError(f"业务库不存在：{db_path}，请先运行 scripts/seed_business_db.py")
    conn = sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True, check_same_thread=False)
    conn.execute("PRAGMA query_only = ON")
    return conn


def run_readonly_query(
    sql: str,
    *,
    max_rows: int | None = None,
    timeout_s: float | None = None,
    path: Path | None = None,
) -> QueryResult:
    """执行一条只读查询。超时、语法错误、写操作都统一抛 SQLExecError（错误信息会回传给模型用于纠错）。"""
    max_rows = max_rows or settings.sql_max_rows
    timeout_s = timeout_s or settings.sql_timeout_s
    conn = connect_readonly(path)
    started = time.perf_counter()
    deadline = time.monotonic() + timeout_s
    # 返回非 0 即中断当前语句，抛 OperationalError("interrupted")
    conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
    try:
        cur = conn.execute(sql)
        columns = [d[0] for d in cur.description or []]
        fetched = cur.fetchmany(max_rows + 1)
    except sqlite3.OperationalError as exc:
        if "interrupted" in str(exc):
            raise SQLExecError(f"查询超时（超过 {timeout_s:g} 秒）") from exc
        raise SQLExecError(str(exc)) from exc
    except sqlite3.Error as exc:
        raise SQLExecError(str(exc)) from exc
    finally:
        conn.close()

    truncated = len(fetched) > max_rows
    rows = [list(r) for r in fetched[:max_rows]]
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return QueryResult(columns=columns, rows=rows, elapsed_ms=elapsed_ms, truncated=truncated)


def is_available(path: Path | None = None) -> bool:
    """业务库文件存在且至少有一张表。"""
    try:
        conn = connect_readonly(path)
    except (SQLExecError, sqlite3.Error):
        return False
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()
        return row[0] > 0
    except sqlite3.Error:
        return False
    finally:
        conn.close()
