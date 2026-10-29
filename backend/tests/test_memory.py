"""Phase 2.7 上下文记忆：消息历史、滑动窗口、增量摘要压缩（假 LLM）。"""
import asyncio

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.db.app_db import init_db
from app.memory import MemoryService, SQLiteChatMessageHistory
from app.repository import MessageRepo, SessionRepo
from tests.fakes import FailingLLM, fake


@pytest.fixture
def env(tmp_path):
    path = tmp_path / "app.db"
    init_db(path)
    sessions, messages = SessionRepo(path), MessageRepo(path)
    return sessions, messages, sessions.create().id


def add_turn(messages: MessageRepo, sid: str, i: int, status: str = "done"):
    messages.add(sid, "user", f"问题{i}")
    a = messages.add(sid, "assistant", "", status="streaming")
    messages.finish(a.id, content=f"回答{i}", status=status, sql=f"SELECT {i}",
                    rewritten_query=f"完整问题{i}", result_summary=f"{i} 行")


def test_history_roundtrip(env):
    _, messages, sid = env
    h = SQLiteChatMessageHistory(sid, messages)
    h.add_messages([HumanMessage("各区域销售额"),
                    AIMessage("华东最高", additional_kwargs={"sql": "SELECT 1", "result_summary": "7 行"})])
    got = h.messages
    assert [type(m) for m in got] == [HumanMessage, AIMessage]
    assert got[1].additional_kwargs["sql"] == "SELECT 1"
    h.clear()
    assert h.messages == []


def test_failed_and_cancelled_turns_excluded(env):
    sessions, messages, sid = env
    add_turn(messages, sid, 1)
    add_turn(messages, sid, 2, status="error")
    add_turn(messages, sid, 3, status="cancelled")
    add_turn(messages, sid, 4)
    _, turns = MemoryService(sessions, messages).load_context(sid)
    assert [t.question for t in turns] == ["问题1", "问题4"]
    assert turns[1].sql == "SELECT 4" and turns[1].rewritten_question == "完整问题4"


def test_window_truncation(env):
    sessions, messages, sid = env
    for i in range(1, 9):
        add_turn(messages, sid, i)
    summary, turns = MemoryService(sessions, messages, window=3).load_context(sid)
    assert summary == "" and [t.question for t in turns] == ["问题6", "问题7", "问题8"]


def test_compress_is_incremental(env):
    sessions, messages, sid = env
    mem = MemoryService(sessions, messages, window=2)
    for i in range(1, 3):
        add_turn(messages, sid, i)
    assert not mem.needs_compress(sid)
    assert asyncio.run(mem.maybe_compress(sid, fake("不该调用"))) is False

    for i in range(3, 5):
        add_turn(messages, sid, i)                 # 共 4 轮，前 2 轮滑出窗口
    llm = fake("用户在看 2025 年各区域销售额")
    assert asyncio.run(mem.maybe_compress(sid, llm)) is True
    s = sessions.get(sid)
    assert s.summary == "用户在看 2025 年各区域销售额" and s.summarized_turns == 2
    assert "完整问题1" in llm.prompts[0] and "完整问题2" in llm.prompts[0] and "完整问题3" not in llm.prompts[0]

    # 没有新轮次滑出：不重复压缩
    assert asyncio.run(mem.maybe_compress(sid, fake("x"))) is False

    add_turn(messages, sid, 5)                     # 第 3 轮滑出
    llm2 = fake("合并后的摘要")
    assert asyncio.run(mem.maybe_compress(sid, llm2)) is True
    assert "用户在看 2025 年各区域销售额" in llm2.prompts[0] and "完整问题3" in llm2.prompts[0]
    assert "完整问题1" not in llm2.prompts[0]
    summary, turns = mem.load_context(sid)
    assert summary == "合并后的摘要" and [t.question for t in turns] == ["问题4", "问题5"]
    assert sessions.get(sid).summarized_turns == 3


def test_compress_failure_keeps_old_summary(env):
    sessions, messages, sid = env
    mem = MemoryService(sessions, messages, window=1)
    for i in range(1, 4):
        add_turn(messages, sid, i)
    assert asyncio.run(mem.maybe_compress(sid, FailingLLM())) is False
    assert sessions.get(sid).summary is None and sessions.get(sid).summarized_turns == 0


def test_migration_adds_column_to_old_db(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT '新对话', "
                 "pinned INTEGER NOT NULL DEFAULT 0, summary TEXT, created_at TEXT, updated_at TEXT)")
    conn.execute("INSERT INTO sessions (id, created_at, updated_at) VALUES ('s1', 'x', 'x')")
    conn.commit()
    conn.close()
    init_db(path)
    assert SessionRepo(path).get("s1").summarized_turns == 0
