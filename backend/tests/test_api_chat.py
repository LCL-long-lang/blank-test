"""Phase 2.8 流式问答 / 图表 / Schema 接口：假 LLM + 小业务库，断言事件顺序和落库结果。"""
import asyncio
import json
from datetime import date
from functools import partial

import pytest

from app.agent import Pipeline
from app.api import deps
from app.db.business import run_readonly_query
from app.db.schema import build_catalog, get_catalog
from app.main import app
from app.repository import ChartRepo, MessageRepo
from app.services.chat_service import ChatService
from tests.fakes import fake_llms

GOOD_SQL = "SELECT status, COUNT(*) AS order_count FROM orders GROUP BY status"


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        event, data = None, []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].lstrip())
        if event:
            events.append((event, json.loads("\n".join(data))))
    return events


@pytest.fixture
def chat_env(client, business_db, monkeypatch):
    """把 ChatService 的 LLM 和业务库换成假的；返回一个设置 LLM 回复的函数。"""
    catalog = build_catalog(business_db)
    monkeypatch.setattr("app.api.schema.get_catalog", lambda: catalog)
    state = {}

    def configure(**llm_kw):
        state["llms"] = fake_llms(**llm_kw)

    def factory():
        llms = state["llms"]
        return ChatService(
            pipeline_factory=lambda: Pipeline(llms=llms, catalog=catalog,
                                              query_fn=partial(run_readonly_query, path=business_db),
                                              today=lambda: date(2026, 10, 3)),
            llms=llms)

    app.dependency_overrides[deps.get_chat_service] = factory
    yield configure, state
    app.dependency_overrides.clear()


def new_session(client) -> str:
    return client.post("/api/sessions").json()["data"]["id"]


def ask(client, sid, question="各状态订单数占比"):
    resp = client.post("/api/chat/stream", json={"session_id": sid, "question": question})
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/event-stream")
    return parse_sse(resp.text)


def test_full_event_order_and_persistence(client, chat_env):
    configure, _ = chat_env
    # fast: 意图 → 标题；chat: 解读
    configure(fast=["query", "订单状态占比"], sql=[GOOD_SQL], chat=["已完成订单占多数。"])
    sid = new_session(client)
    events = ask(client, sid)
    names = [e for e, _ in events if e != "step"]
    assert names[0] == "start" and names[-1] == "done"
    assert names[1:4] == ["sql", "data", "chart"]
    assert "text" in names and names[-2] == "title"
    assert names.index("text") < names.index("title")

    start = events[0][1]
    chart = next(d for e, d in events if e == "chart")
    assert chart["spec"]["chart_type"] == "pie"
    assert next(d for e, d in events if e == "title")["title"] == "订单状态占比"
    step_keys = {d["key"] for e, d in events if e == "step"}
    assert {"rewrite", "intent", "schema", "generate_sql", "execute", "chart", "insight"} <= step_keys

    msgs = client.get(f"/api/sessions/{sid}/messages").json()["data"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    ai = msgs[1]
    assert ai["id"] == start["message_id"] and ai["status"] == "done" and ai["has_chart"]
    assert ai["content"] == "已完成订单占多数。" and ai["sql"].endswith("LIMIT 1000")
    assert client.get("/api/sessions").json()["data"][0]["title"] == "订单状态占比"

    # 图表回看与切换类型
    c = client.get(f"/api/charts/{ai['id']}").json()["data"]
    assert c["spec"]["chart_type"] == "pie" and len(c["rows"]) == 3
    r = client.post(f"/api/charts/{ai['id']}/render", json={"chart_type": "bar"}).json()["data"]
    assert r["spec"]["chart_type"] == "bar" and r["option"]["series"][0]["type"] == "bar"
    assert client.get(f"/api/charts/{ai['id']}").json()["data"]["spec"]["chart_type"] == "bar"
    bad = client.post(f"/api/charts/{ai['id']}/render", json={"chart_type": "kpi"})
    assert bad.status_code == 400 and bad.json()["code"] == "CHART_UNSUPPORTED"


def test_followup_uses_memory_and_title_only_once(client, chat_env):
    configure, state = chat_env
    sid = new_session(client)
    configure(fast=["query", "订单状态"], sql=[GOOD_SQL], chat=["第一轮"])
    ask(client, sid)
    configure(fast=["只看已完成订单的数量", "query"], sql=["SELECT COUNT(*) AS n FROM orders WHERE status='completed'"],
              chat=["第二轮"])
    events = ask(client, sid, "那只看已完成的呢")
    assert "title" not in [e for e, _ in events]
    rewrite_prompt = state["llms"].fast.prompts[0]
    assert "各状态订单数占比" in rewrite_prompt and "GROUP BY status" in rewrite_prompt
    assert next(d for e, d in events if e == "chart")["spec"]["chart_type"] == "kpi"


def test_sql_failure_marks_message_error(client, chat_env):
    configure, _ = chat_env
    configure(fast=["query"], sql=["SELECT nope FROM orders"] * 3)
    sid = new_session(client)
    events = ask(client, sid)
    names = [e for e, _ in events if e != "step"]
    assert names == ["start", "sql", "sql", "sql", "error", "done"]
    msgs = client.get(f"/api/sessions/{sid}/messages").json()["data"]
    assert msgs[1]["status"] == "error" and "no such column" in msgs[1]["error"]
    assert not msgs[1]["has_chart"]
    # 失败的轮次不生成标题
    assert client.get("/api/sessions").json()["data"][0]["title"] == "新对话"


def test_chitchat_has_no_sql_or_chart(client, chat_env):
    configure, _ = chat_env
    configure(fast=["chitchat", "打招呼"], chat=["你好！"])
    sid = new_session(client)
    names = {e for e, _ in ask(client, sid, "你好")}
    assert not names & {"sql", "data", "chart"} and "text" in names


def test_unknown_session_returns_404(client, chat_env):
    configure, _ = chat_env
    configure()
    resp = client.post("/api/chat/stream", json={"session_id": "nope", "question": "x"})
    assert resp.status_code == 404 and resp.json()["code"] == "NOT_FOUND"


@pytest.mark.parametrize("body", [{"session_id": "x", "question": ""},
                                  {"session_id": "x", "question": "x" * 501},
                                  {"question": "x"}])
def test_request_validation(client, body):
    assert client.post("/api/chat/stream", json=body).status_code == 422


def test_cancel_marks_message_cancelled(client, chat_env):
    """模拟客户端中途断开：关闭生成器后，消息状态为 cancelled，已输出的文字保留。"""
    configure, state = chat_env
    configure(fast=["query"], sql=[GOOD_SQL], chat=["一段比较长的解读文字"])
    sid = new_session(client)
    svc = app.dependency_overrides[deps.get_chat_service]()

    async def run_until_text():
        user_id, mid = svc.prepare(sid, "各状态订单数")
        gen = svc.stream(sid, "各状态订单数", user_id, mid)
        async for event, _ in gen:
            if event == "text":
                break
        await gen.aclose()
        return mid

    mid = asyncio.run(run_until_text())
    m = MessageRepo().get(mid)
    assert m.status == "cancelled" and m.content  # 已推送的部分文字被保存
    assert ChartRepo().get_by_message(mid) is None


def test_chart_not_found(client):
    resp = client.get("/api/charts/nope")
    assert resp.status_code == 404 and resp.json()["code"] == "NOT_FOUND"


def test_schema_endpoint(client, chat_env):
    data = client.get("/api/schema").json()["data"]
    assert {t["name"] for t in data["tables"]} == {"regions", "customers", "categories", "products",
                                                    "orders", "order_items"}
    orders = next(t for t in data["tables"] if t["name"] == "orders")
    assert orders["label"] == "订单" and any(c["description"] for c in orders["columns"])
    assert 1 <= len(data["examples"]) <= 6


def test_openapi_lists_all_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    for p in ["/api/sessions", "/api/sessions/{session_id}", "/api/sessions/{session_id}/messages",
              "/api/chat/stream", "/api/charts/{message_id}", "/api/charts/{message_id}/render",
              "/api/schema", "/api/health"]:
        assert p in paths, p
