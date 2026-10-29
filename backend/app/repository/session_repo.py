from dataclasses import dataclass

from app.repository.base import BaseRepo, new_id, now


@dataclass
class SessionRow:
    id: str
    title: str
    pinned: bool
    summary: str | None
    created_at: str
    updated_at: str
    summarized_turns: int = 0


def _row(r) -> SessionRow:
    return SessionRow(id=r["id"], title=r["title"], pinned=bool(r["pinned"]), summary=r["summary"],
                      created_at=r["created_at"], updated_at=r["updated_at"],
                      summarized_turns=r["summarized_turns"])


class SessionRepo(BaseRepo):
    def create(self, title: str = "新对话") -> SessionRow:
        sid, ts = new_id(), now()
        with self.conn() as c:
            c.execute("INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                      (sid, title, ts, ts))
        return SessionRow(id=sid, title=title, pinned=False, summary=None, created_at=ts, updated_at=ts)

    def get(self, session_id: str) -> SessionRow | None:
        with self.conn() as c:
            r = c.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return _row(r) if r else None

    def list(self, keyword: str | None = None) -> list[SessionRow]:
        """置顶优先，再按更新时间倒序；keyword 匹配标题。"""
        sql = "SELECT * FROM sessions"
        params: tuple = ()
        if keyword:
            # 转义 LIKE 通配符，用户输入的 % _ 按字面匹配
            escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            sql += " WHERE title LIKE ? ESCAPE '\\'"
            params = (f"%{escaped}%",)
        sql += " ORDER BY pinned DESC, updated_at DESC"
        with self.conn() as c:
            return [_row(r) for r in c.execute(sql, params)]

    def update(self, session_id: str, *, title: str | None = None, pinned: bool | None = None) -> bool:
        """重命名 / 置顶。置顶不刷新 updated_at，避免打乱“今天 / 近 7 天”分组。"""
        sets, params = [], []
        if title is not None:
            sets.append("title = ?")
            params.append(title)
        if pinned is not None:
            sets.append("pinned = ?")
            params.append(int(pinned))
        if not sets:
            return self.get(session_id) is not None
        with self.conn() as c:
            cur = c.execute(f"UPDATE sessions SET {', '.join(sets)} WHERE id = ?", (*params, session_id))
        return cur.rowcount > 0

    def touch(self, session_id: str) -> None:
        with self.conn() as c:
            c.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now(), session_id))

    def set_summary(self, session_id: str, summary: str, summarized_turns: int) -> None:
        with self.conn() as c:
            c.execute("UPDATE sessions SET summary = ?, summarized_turns = ? WHERE id = ?",
                      (summary, summarized_turns, session_id))

    def delete(self, session_id: str) -> bool:
        """级联删除消息和图表（依赖 PRAGMA foreign_keys=ON）。"""
        with self.conn() as c:
            cur = c.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        return cur.rowcount > 0
