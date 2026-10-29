from dataclasses import dataclass
from typing import Literal

from app.repository.base import BaseRepo, new_id, now

Role = Literal["user", "assistant"]
Status = Literal["streaming", "done", "error", "cancelled"]


@dataclass
class MessageRow:
    id: str
    session_id: str
    role: Role
    content: str
    rewritten_query: str | None
    sql: str | None
    result_summary: str | None
    status: Status
    error: str | None
    elapsed_ms: int | None
    created_at: str
    has_chart: bool = False


_SELECT = """
SELECT m.*, EXISTS (SELECT 1 FROM charts c WHERE c.message_id = m.id) AS has_chart
FROM messages m
"""


def _row(r) -> MessageRow:
    return MessageRow(
        id=r["id"], session_id=r["session_id"], role=r["role"], content=r["content"],
        rewritten_query=r["rewritten_query"], sql=r["sql"], result_summary=r["result_summary"],
        status=r["status"], error=r["error"], elapsed_ms=r["elapsed_ms"], created_at=r["created_at"],
        has_chart=bool(r["has_chart"]),
    )


class MessageRepo(BaseRepo):
    def add(self, session_id: str, role: Role, content: str, status: Status = "done") -> MessageRow:
        mid, ts = new_id(), now()
        with self.conn() as c:
            c.execute(
                "INSERT INTO messages (id, session_id, role, content, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (mid, session_id, role, content, status, ts),
            )
        return MessageRow(id=mid, session_id=session_id, role=role, content=content, rewritten_query=None,
                          sql=None, result_summary=None, status=status, error=None, elapsed_ms=None,
                          created_at=ts)

    def finish(self, message_id: str, *, content: str, status: Status,
               rewritten_query: str | None = None, sql: str | None = None,
               result_summary: str | None = None, error: str | None = None,
               elapsed_ms: int | None = None) -> None:
        """AI 消息生成结束（完成 / 出错 / 取消）时一次性写入全部字段。"""
        with self.conn() as c:
            c.execute(
                """UPDATE messages SET content = ?, status = ?, rewritten_query = ?, sql = ?,
                       result_summary = ?, error = ?, elapsed_ms = ? WHERE id = ?""",
                (content, status, rewritten_query, sql, result_summary, error, elapsed_ms, message_id),
            )

    def get(self, message_id: str) -> MessageRow | None:
        with self.conn() as c:
            r = c.execute(_SELECT + " WHERE m.id = ?", (message_id,)).fetchone()
        return _row(r) if r else None

    def list_by_session(self, session_id: str) -> list[MessageRow]:
        with self.conn() as c:
            return [_row(r) for r in c.execute(
                _SELECT + " WHERE m.session_id = ? ORDER BY m.created_at, m.rowid", (session_id,))]

    def count_by_session(self, session_id: str, role: Role | None = None) -> int:
        sql, params = "SELECT COUNT(*) FROM messages WHERE session_id = ?", [session_id]
        if role:
            sql += " AND role = ?"
            params.append(role)
        with self.conn() as c:
            return c.execute(sql, params).fetchone()[0]

    def delete_by_session(self, session_id: str) -> int:
        with self.conn() as c:
            return c.execute("DELETE FROM messages WHERE session_id = ?", (session_id,)).rowcount

    def mark_stale_streaming(self) -> int:
        """服务重启后，残留的 streaming 消息标记为 cancelled。"""
        with self.conn() as c:
            return c.execute(
                "UPDATE messages SET status = 'cancelled' WHERE status = 'streaming'").rowcount
