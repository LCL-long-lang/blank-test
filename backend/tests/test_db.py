"""Phase 2.1 数据层：只读执行、超时、截断、Schema 抽取与渲染。"""
import pytest

from app.common.errors import SQLExecError
from app.db.business import run_readonly_query
from app.db.schema import build_catalog, load_examples, render_schema_context

TABLES = {"regions", "customers", "categories", "products", "orders", "order_items"}


def test_query_returns_columns_and_rows(business_db):
    r = run_readonly_query("SELECT status, COUNT(*) AS n FROM orders GROUP BY status ORDER BY status",
                           path=business_db)
    assert r.columns == ["status", "n"]
    assert [row[0] for row in r.rows] == ["cancelled", "completed", "refunded"]
    assert r.total == 3 and not r.truncated


def test_query_truncates_at_max_rows(business_db):
    r = run_readonly_query("SELECT order_id FROM orders", max_rows=50, path=business_db)
    assert r.total == 50 and r.truncated


@pytest.mark.parametrize("sql", [
    "DELETE FROM orders",
    "UPDATE orders SET status='x'",
    "DROP TABLE orders",
    "INSERT INTO regions VALUES (999,'x','x')",
    "CREATE TABLE hack(x)",
])
def test_write_rejected_by_readonly_connection(business_db, sql):
    with pytest.raises(SQLExecError):
        run_readonly_query(sql, path=business_db)
    # 数据没有任何变化
    assert run_readonly_query("SELECT COUNT(*) FROM orders", path=business_db).rows[0][0] == 2000


def test_timeout_interrupts(business_db):
    slow = """
        WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n)
        SELECT COUNT(*) FROM n
    """
    with pytest.raises(SQLExecError, match="超时"):
        run_readonly_query(slow, timeout_s=0.3, path=business_db)


def test_syntax_error_message_is_kept(business_db):
    with pytest.raises(SQLExecError, match="no such column"):
        run_readonly_query("SELECT create_time FROM orders", path=business_db)


def test_missing_db_raises(tmp_path):
    with pytest.raises(SQLExecError, match="业务库不存在"):
        run_readonly_query("SELECT 1", path=tmp_path / "nope.db")


def test_catalog_tables_and_dictionary(business_db):
    cat = build_catalog(business_db)
    assert cat.table_names == TABLES
    orders = next(t for t in cat.tables if t.name == "orders")
    assert orders.label == "订单"
    status = next(c for c in orders.columns if c.name == "status")
    assert status.samples == ["cancelled", "completed", "refunded"]
    assert any(fk.ref_table == "customers" for fk in orders.foreign_keys)


def test_context_contains_all_tables_and_metrics(business_db):
    ctx = build_catalog(business_db).context
    for t in TABLES:
        assert f"CREATE TABLE {t} (" in ctx
    assert "REFERENCES customers(customer_id)" in ctx
    assert "-- 指标口径" in ctx and "销售额" in ctx
    # 字典中写了取值的列，不再重复追加样例
    assert ctx.count("华东") == 1


def test_render_is_pure_without_metrics(business_db):
    tables = build_catalog(business_db).tables
    assert "指标口径" not in render_schema_context(tables)


def test_examples_sql_all_executable(business_db):
    """示例集里每条标准 SQL 都能在业务库上执行（评测集和 Few-shot 的前提）。"""
    examples = load_examples()
    assert len(examples) >= 20
    assert len({e["id"] for e in examples}) == len(examples)
    for e in examples:
        run_readonly_query(e["sql"], path=business_db)
