"""Phase 2.6 会话接口与自动标题。"""
import asyncio

from app.repository import ChartRepo, MessageRepo
from app.services.session_service import SessionService, clean_title
from tests.fakes import FailingLLM, fake


def data(resp):
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == "OK"
    return body["data"]


def test_create_default_and_custom_title(client):
    s = data(client.post("/api/sessions"))
    assert s["title"] == "新对话" and s["pinned"] is False
    assert data(client.post("/api/sessions", json={"title": "  区域分析 "}))["title"] == "区域分析"


def test_list_order_and_search(client):
    a = data(client.post("/api/sessions", json={"title": "销售趋势"}))
    b = data(client.post("/api/sessions", json={"title": "客户画像"}))
    data(client.patch(f"/api/sessions/{a['id']}", json={"pinned": True}))
    assert [s["id"] for s in data(client.get("/api/sessions"))] == [a["id"], b["id"]]
    assert [s["title"] for s in data(client.get("/api/sessions", params={"keyword": "客户"}))] == ["客户画像"]


def test_rename_and_pin(client):
    s = data(client.post("/api/sessions"))
    out = data(client.patch(f"/api/sessions/{s['id']}", json={"title": "新名字", "pinned": True}))
    assert out["title"] == "新名字" and out["pinned"] is True
    out = data(client.patch(f"/api/sessions/{s['id']}", json={"pinned": False}))
    assert out["title"] == "新名字" and out["pinned"] is False


def test_rename_validation(client):
    s = data(client.post("/api/sessions"))
    assert client.patch(f"/api/sessions/{s['id']}", json={"title": ""}).status_code == 422
    assert client.patch(f"/api/sessions/{s['id']}", json={"title": "x" * 51}).status_code == 422


def test_not_found(client):
    for resp in [client.patch("/api/sessions/nope", json={"title": "x"}),
                 client.delete("/api/sessions/nope"),
                 client.get("/api/sessions/nope/messages")]:
        assert resp.status_code == 404 and resp.json()["code"] == "NOT_FOUND"


def test_delete_cascades(client):
    s = data(client.post("/api/sessions"))
    msgs, charts = MessageRepo(), ChartRepo()
    m = msgs.add(s["id"], "assistant", "ok")
    charts.save(m.id, {}, {}, [], [])
    data(client.delete(f"/api/sessions/{s['id']}"))
    assert client.get(f"/api/sessions/{s['id']}/messages").status_code == 404
    assert charts.get_by_message(m.id) is None
    assert data(client.get("/api/sessions")) == []


def test_list_messages(client):
    s = data(client.post("/api/sessions"))
    msgs, charts = MessageRepo(), ChartRepo()
    msgs.add(s["id"], "user", "近 6 个月趋势")
    a = msgs.add(s["id"], "assistant", "", status="streaming")
    msgs.finish(a.id, content="上升", status="done", sql="SELECT 1", elapsed_ms=10)
    charts.save(a.id, {}, {}, [], [])
    out = data(client.get(f"/api/sessions/{s['id']}/messages"))
    assert [m["role"] for m in out] == ["user", "assistant"]
    assert out[1]["has_chart"] is True and out[1]["sql"] == "SELECT 1" and out[0]["has_chart"] is False
    assert "rewritten_query" not in out[1]  # 内部字段不对外


def test_generate_title(client):
    svc = SessionService()
    s = svc.create()
    assert asyncio.run(svc.generate_title(s.id, "近 6 个月各品类销售额趋势", fake("“品类销售趋势”。"))) == "品类销售趋势"
    assert svc.get(s.id).title == "品类销售趋势"
    # 已有标题不再覆盖
    assert asyncio.run(svc.generate_title(s.id, "x", fake("别的"))) is None


def test_generate_title_falls_back_on_llm_error(client):
    svc = SessionService()
    s = svc.create()
    title = asyncio.run(svc.generate_title(s.id, "今年各大区的销售额排名情况如何呢", FailingLLM()))
    assert title == "今年各大区的销售额排名情况如何"[:15]


def test_clean_title():
    assert clean_title("标题：区域对比\n解释……", "f") == "区域对比"
    assert clean_title("", "fallback") == "fallback"
    assert len(clean_title("一" * 30, "f")) == 15
