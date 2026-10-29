"""Phase 2.2 SQL 安全：纯函数测试，不依赖数据库。"""
import pytest

from app.common.errors import SQLGuardError
from app.sql_guard import strip_sql, validate_and_rewrite

ALLOWED = {"orders", "order_items", "customers", "regions", "products", "categories"}


def check(sql: str, max_rows: int = 1000) -> str:
    return validate_and_rewrite(sql, ALLOWED, max_rows)


@pytest.mark.parametrize("raw, expected", [
    ("```sql\nSELECT 1\n```", "SELECT 1"),
    ("```\nSELECT 1;\n```", "SELECT 1"),
    ("  SELECT 1 ;  ", "SELECT 1"),
])
def test_strip_sql(raw, expected):
    assert strip_sql(raw) == expected


def test_simple_select_gets_limit():
    assert check("SELECT * FROM orders").endswith("LIMIT 1000")


def test_existing_small_limit_kept():
    assert check("SELECT * FROM orders LIMIT 10").endswith("LIMIT 10")


def test_large_limit_capped():
    out = check("SELECT * FROM orders LIMIT 99999", max_rows=500)
    assert out.endswith("LIMIT 500") and "99999" not in out


def test_union_gets_outer_limit():
    out = check("SELECT order_id FROM orders UNION SELECT item_id FROM order_items")
    assert out.endswith("LIMIT 1000")


def test_cte_allowed_and_not_treated_as_table():
    out = check("WITH t AS (SELECT customer_id, COUNT(*) c FROM orders GROUP BY 1) SELECT * FROM t")
    assert "LIMIT 1000" in out


def test_subquery_and_join_allowed():
    check("""
        SELECT r.region_name, SUM(o.total_amount) FROM orders o
        JOIN customers c ON c.customer_id = o.customer_id
        JOIN regions r ON r.region_id = c.region_id
        WHERE o.order_id IN (SELECT order_id FROM order_items)
        GROUP BY 1
    """)


def test_markdown_wrapped_sql_accepted():
    assert check("```sql\nSELECT COUNT(*) FROM orders;\n```").startswith("SELECT COUNT(*)")


@pytest.mark.parametrize("sql", [
    "DROP TABLE orders",
    "DELETE FROM orders",
    "UPDATE orders SET status = 'x'",
    "INSERT INTO orders VALUES (1)",
    "REPLACE INTO orders VALUES (1)",
    "CREATE TABLE x (a INT)",
    "ALTER TABLE orders ADD COLUMN x INT",
    "PRAGMA table_info(orders)",
    "ATTACH DATABASE 'app.db' AS app",
    "DETACH DATABASE app",
    "VACUUM",
    "BEGIN TRANSACTION",
    "EXPLAIN SELECT 1",
])
def test_non_query_rejected(sql):
    with pytest.raises(SQLGuardError):
        check(sql)


@pytest.mark.parametrize("sql", [
    "SELECT 1; DROP TABLE orders",
    "SELECT * FROM orders; SELECT * FROM customers",
])
def test_multiple_statements_rejected(sql):
    with pytest.raises(SQLGuardError, match="一条"):
        check(sql)


@pytest.mark.parametrize("sql", [
    "SELECT * FROM sessions",
    "SELECT * FROM sqlite_master",
    "SELECT * FROM orders o JOIN messages m ON 1=1",
    "WITH t AS (SELECT * FROM charts) SELECT * FROM t",
])
def test_unknown_table_rejected(sql):
    with pytest.raises(SQLGuardError, match="不存在或不允许访问"):
        check(sql)


def test_cross_database_reference_rejected():
    with pytest.raises(SQLGuardError, match="跨库"):
        check("SELECT * FROM main.orders")


def test_empty_and_garbage_rejected():
    with pytest.raises(SQLGuardError):
        check("   ")
    with pytest.raises(SQLGuardError):
        check("SELECT FROM WHERE (")


def test_table_names_case_insensitive():
    check("SELECT * FROM Orders")


def test_chinese_alias_allowed():
    out = check("SELECT status AS 状态, COUNT(*) AS 订单数 FROM orders GROUP BY status")
    assert "订单数" in out


def test_all_example_sql_pass_guard():
    """示例集的标准 SQL 都应通过校验，否则 Few-shot 会教模型写出被拒绝的 SQL。"""
    from app.db.schema import load_examples

    for e in load_examples():
        check(e["sql"])
