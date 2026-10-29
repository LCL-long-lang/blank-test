"""系统库 app.db：连接与建表（会话 / 消息 / 图表）。"""
import sqlite3
from pathlib import Path

from app.config import settings

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '新对话',
    pinned      INTEGER NOT NULL DEFAULT 0,
    summary     TEXT,
    summarized_turns INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user','assistant')),
    content         TEXT NOT NULL,
    rewritten_query TEXT,
    sql             TEXT,
    result_summary  TEXT,
    status          TEXT NOT NULL DEFAULT 'done'
                    CHECK (status IN ('streaming','done','error','cancelled')),
    error           TEXT,
    elapsed_ms      INTEGER,
    created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);

CREATE TABLE IF NOT EXISTS charts (
    id              TEXT PRIMARY KEY,
    message_id      TEXT NOT NULL UNIQUE REFERENCES messages(id) ON DELETE CASCADE,
    chart_spec      TEXT NOT NULL,
    echarts_option  TEXT NOT NULL,
    columns         TEXT NOT NULL,
    rows            TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    """获取 app.db 连接；每个连接都要开启外键约束，否则级联删除不生效。"""
    db_path = Path(path or settings.app_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


# 增量迁移：(表, 列, 列定义)。旧库缺列时自动 ALTER TABLE 补上，新库由 SCHEMA_SQL 直接创建
MIGRATIONS = [
    ("sessions", "summarized_turns", "INTEGER NOT NULL DEFAULT 0"),
]


def _migrate(conn: sqlite3.Connection) -> None:
    for table, column, ddl in MIGRATIONS:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db(path: Path | None = None) -> None:
    conn = connect(path)
    try:
        conn.executescript(SCHEMA_SQL)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()
