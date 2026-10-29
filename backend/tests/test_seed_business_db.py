import sqlite3
from datetime import date

import pytest

from app.db import business
from scripts.seed_business_db import build, months_back


def test_months_back():
    assert months_back(date(2026, 10, 3), 24) == date(2024, 11, 1)
    assert months_back(date(2026, 1, 15), 1) == date(2026, 1, 1)
    assert months_back(date(2026, 1, 15), 2) == date(2025, 12, 1)


def test_seed_counts(business_db):
    conn = sqlite3.connect(business_db)
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ["regions", "customers", "categories", "products", "orders", "order_items"]}
    conn.close()
    assert counts["regions"] == 29
    assert counts["categories"] == 8
    assert counts["products"] == 200
    assert counts["customers"] == 2000
    assert counts["orders"] == 2000
    assert counts["order_items"] > counts["orders"]


def test_seed_consistency(business_db):
    conn = sqlite3.connect(business_db)
    # 订单金额 = 明细金额之和
    diff = conn.execute("""
        SELECT MAX(ABS(o.total_amount - s.amt)) FROM orders o
        JOIN (SELECT order_id, SUM(quantity * unit_price) amt FROM order_items GROUP BY order_id) s
          ON s.order_id = o.order_id
    """).fetchone()[0]
    span = conn.execute("SELECT MIN(order_date), MAX(order_date) FROM orders").fetchone()
    conn.close()
    assert diff < 0.05
    assert span[0] >= "2025-11-01" and span[1] < "2026-10-04"


def test_seed_reproducible(tmp_path):
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    build(a, 300, 6, date(2026, 10, 3))
    build(b, 300, 6, date(2026, 10, 3))
    q = "SELECT SUM(total_amount) FROM orders"
    assert sqlite3.connect(a).execute(q).fetchone() == sqlite3.connect(b).execute(q).fetchone()


def test_readonly_connection_rejects_write(business_db):
    assert business.is_available(business_db)
    conn = business.connect_readonly(business_db)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM orders")
    conn.close()
