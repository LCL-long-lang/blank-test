"""Phase 2.5 数据仓储：每个测试用独立的临时 app.db。"""
import pytest

from app.db.app_db import init_db
from app.repository import ChartRepo, MessageRepo, SessionRepo


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "app.db"
    init_db(path)
    return path


@pytest.fixture
def repos(db):
    return SessionRepo(db), MessageRepo(db), ChartRepo(db)


def test_session_crud(repos):
    sessions, _, _ = repos
    s = sessions.create()
    assert s.title == "新对话" and not s.pinned
    assert sessions.update(s.id, title="品类趋势", pinned=True)
    got = sessions.get(s.id)
    assert got.title == "品类趋势" and got.pinned
    assert sessions.delete(s.id) and sessions.get(s.id) is None
    assert not sessions.delete(s.id)
    assert not sessions.update("missing", title="x")


def test_list_order_pinned_first_then_updated(repos):
    sessions, _, _ = repos
    a, b, c = sessions.create("A"), sessions.create("B"), sessions.create("C")
    sessions.touch(a.id)                        # A 最新
    sessions.update(c.id, pinned=True)          # C 置顶
    assert [s.title for s in sessions.list()] == ["C", "A", "B"]


def test_pin_does_not_change_updated_at(repos):
    sessions, _, _ = repos
    s = sessions.create()
    sessions.update(s.id, pinned=True)
    assert sessions.get(s.id).updated_at == s.updated_at


def test_list_keyword_escapes_wildcards(repos):
    sessions, _, _ = repos
    sessions.create("销售额趋势")
    sessions.create("100% 完成率")
    sessions.create("客户分析")
    assert [s.title for s in sessions.list("销售")] == ["销售额趋势"]
    assert [s.title for s in sessions.list("%")] == ["100% 完成率"]
    assert sessions.list("_") == []


def test_messages_order_and_finish(repos):
    sessions, messages, _ = repos
    s = sessions.create()
    u = messages.add(s.id, "user", "近 6 个月趋势")
    a = messages.add(s.id, "assistant", "", status="streaming")
    messages.finish(a.id, content="趋势平稳", status="done", sql="SELECT 1", elapsed_ms=120,
                    rewritten_query="近 6 个月销售额趋势", result_summary="1 行")
    rows = messages.list_by_session(s.id)
    assert [m.id for m in rows] == [u.id, a.id]
    assert rows[1].status == "done" and rows[1].sql == "SELECT 1" and rows[1].elapsed_ms == 120
    assert messages.count_by_session(s.id, "user") == 1


def test_mark_stale_streaming(repos):
    sessions, messages, _ = repos
    s = sessions.create()
    m = messages.add(s.id, "assistant", "", status="streaming")
    assert messages.mark_stale_streaming() == 1
    assert messages.get(m.id).status == "cancelled"


def test_chart_save_get_and_render_update(repos):
    sessions, messages, charts = repos
    s = sessions.create()
    a = messages.add(s.id, "assistant", "ok")
    charts.save(a.id, {"chart_type": "line"}, {"series": []}, ["month", "销售额"], [["2026-05", 1.5]])
    assert messages.get(a.id).has_chart
    c = charts.get_by_message(a.id)
    assert c.columns == ["month", "销售额"] and c.rows == [["2026-05", 1.5]]
    assert charts.update_render(a.id, {"chart_type": "bar"}, {"series": [1]})
    assert charts.get_by_message(a.id).chart_spec == {"chart_type": "bar"}
    # 同一消息再次保存：覆盖而不是报唯一约束错误
    charts.save(a.id, {"chart_type": "pie"}, {}, ["x"], [[1]])
    assert charts.get_by_message(a.id).chart_spec == {"chart_type": "pie"}


def test_cascade_delete(repos):
    sessions, messages, charts = repos
    s = sessions.create()
    a = messages.add(s.id, "assistant", "ok")
    charts.save(a.id, {}, {}, [], [])
    sessions.delete(s.id)
    assert messages.list_by_session(s.id) == []
    assert charts.get_by_message(a.id) is None


def test_message_requires_existing_session(repos):
    import sqlite3

    _, messages, _ = repos
    with pytest.raises(sqlite3.IntegrityError):
        messages.add("missing", "user", "x")
