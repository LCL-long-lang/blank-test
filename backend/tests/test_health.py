import sqlite3

from app.db import app_db


def test_health_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == "OK"
    assert body["data"]["status"] == "ok"
    assert body["data"]["app_db"] is True          # lifespan 已建库
    assert body["data"]["business_db"] is False    # 临时目录下没有业务库


def test_app_db_tables_created(client, tmp_settings):
    conn = app_db.connect()
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"sessions", "messages", "charts"} <= tables


def test_cascade_delete(client):
    conn = app_db.connect()
    conn.execute("INSERT INTO sessions(id) VALUES ('s1')")
    conn.execute("INSERT INTO messages(id, session_id, role, content) VALUES ('m1','s1','user','hi')")
    conn.execute("DELETE FROM sessions WHERE id='s1'")
    left = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    conn.close()
    assert left == 0


def test_unknown_route_404(client):
    assert client.get("/api/not-exist").status_code == 404


def test_cors_preflight(client):
    resp = client.options(
        "/api/health",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
