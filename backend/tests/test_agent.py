"""Phase 2.4 Agent 管道：用假 LLM 覆盖各流程分支，不消耗 Token。"""
import asyncio
from datetime import date
from functools import partial

import pytest

from app.agent import AgentInput, Pipeline, Turn
from app.agent.pipeline import parse_chart_spec, parse_intent
from app.agent.summary import insight_summary, memory_summary
from app.db.business import QueryResult, run_readonly_query
from app.db.schema import build_catalog
from tests.fakes import FailingLLM, fake_llms

GOOD_SQL = "SELECT status, COUNT(*) AS order_count FROM orders GROUP BY status"


@pytest.fixture(scope="module")
def catalog(business_db):
    return build_catalog(business_db)


def make(catalog, business_db, **llm_kw) -> Pipeline:
    return Pipeline(llms=fake_llms(**llm_kw), catalog=catalog,
                    query_fn=partial(run_readonly_query, path=business_db),
                    today=lambda: date(2026, 10, 3))


def run(pipe: Pipeline, question: str, **kw):
    async def collect():
        return [ev async for ev in pipe.run(AgentInput(question=question, **kw))]
    events = asyncio.run(collect())
    assert events[-1].event == "final"
    return events[:-1], events[-1].data


def names(events, skip_steps=True):
    return [e.event for e in events if not (skip_steps and e.event == "step")]


def test_success_flow(catalog, business_db):
    pipe = make(catalog, business_db, fast=["query"], sql=[f"```sql\n{GOOD_SQL}\n```"],
                chat=["订单以已完成为主。"])
    events, out = run(pipe, "各状态订单数占比")
    seq = names(events)
    assert seq[:3] == ["sql", "data", "chart"] and set(seq[3:]) == {"text"}
    assert out.ok and out.attempts == 1 and out.sql.endswith("LIMIT 1000")
    assert out.chart_spec.chart_type == "pie"
    assert out.answer == "订单以已完成为主。"
    assert out.result.total == 3 and "3 行" in out.result_summary
    # 步骤：每个 running 之后都有 done
    steps = [(e.data.key, e.data.status) for e in events if e.event == "step"]
    assert ("rewrite", "done") in steps and ("insight", "done") in steps
    # 无历史时不调用改写，fast 只用于意图
    assert len(pipe.llms.fast.prompts) == 1
    # SQL Prompt 包含 Schema、日期和 Few-shot
    sql_prompt = pipe.llms.sql.prompts[0]
    assert "CREATE TABLE orders" in sql_prompt and "2026-10-03" in sql_prompt and "参考示例" in sql_prompt


def test_self_correction_after_exec_error(catalog, business_db):
    pipe = make(catalog, business_db, fast=["query"],
                sql=["SELECT create_time FROM orders", GOOD_SQL])
    events, out = run(pipe, "各状态订单数")
    sqls = [e.data for e in events if e.event == "sql"]
    assert [s.attempt for s in sqls] == [1, 2]
    assert out.ok and out.attempts == 2
    retry_prompt = pipe.llms.sql.prompts[1]
    assert "create_time" in retry_prompt and "no such column" in retry_prompt


def test_self_correction_after_guard_rejection(catalog, business_db):
    pipe = make(catalog, business_db, fast=["query"], sql=["DELETE FROM orders", GOOD_SQL])
    events, out = run(pipe, "删除再查")
    assert out.ok and out.attempts == 2
    # 被拒绝的 SQL 不推 sql 事件
    assert [e.data.attempt for e in events if e.event == "sql"] == [2]
    assert "只允许查询语句" in pipe.llms.sql.prompts[1]


def test_three_failures_yield_error(catalog, business_db):
    pipe = make(catalog, business_db, fast=["query"], sql=["SELECT nope FROM orders"] * 3)
    events, out = run(pipe, "x")
    assert names(events) == ["sql", "sql", "sql", "error"]
    err = events[-1].data
    assert err.code == "SQL_FAILED" and err.retryable and "no such column" in err.message
    assert not out.ok and out.attempts == 3


def test_destructive_question_never_executes(catalog, business_db):
    pipe = make(catalog, business_db, fast=["query"], sql=["DROP TABLE orders"] * 3)
    events, out = run(pipe, "删除所有订单")
    assert "sql" not in names(events) and out.error_code == "SQL_FAILED"
    assert run_readonly_query("SELECT COUNT(*) FROM orders", path=business_db).rows[0][0] == 2000


def test_empty_result_retried_once(catalog, business_db):
    empty = "SELECT order_id FROM orders WHERE status = '不存在'"
    pipe = make(catalog, business_db, fast=["query"], sql=[empty, empty])
    events, out = run(pipe, "x")
    assert out.ok and out.attempts == 2 and out.result.total == 0
    assert "0 行" in pipe.llms.sql.prompts[1]
    assert "没有查询到" in out.answer


def test_cannot_answer(catalog, business_db):
    pipe = make(catalog, business_db, fast=["query"], sql=["CANNOT_ANSWER: 数据中没有天气信息"])
    events, out = run(pipe, "明天天气")
    assert names(events) == ["text"] and "天气信息" in out.answer
    assert out.ok and out.result is None


@pytest.mark.parametrize("intent", ["chitchat", "clarify"])
def test_non_query_intents_skip_sql(catalog, business_db, intent):
    pipe = make(catalog, business_db, fast=[intent], chat=["你好，我可以帮你分析数据。"])
    events, out = run(pipe, "你好")
    assert set(names(events)) == {"text"} and out.intent == intent
    assert pipe.llms.sql.prompts == []


def test_followup_rewrite_uses_history(catalog, business_db):
    history = [Turn(question="2025 年各区域销售额", sql="SELECT region_name ...", result_summary="7 行")]
    pipe = make(catalog, business_db, fast=["2025 年华东区每月的销售额", "query"], sql=[GOOD_SQL])
    events, out = run(pipe, "那华东按月拆一下", history=history, summary="一直在看 2025 年")
    assert out.rewritten_question == "2025 年华东区每月的销售额"
    rewrite_prompt = pipe.llms.fast.prompts[0]
    assert "2025 年各区域销售额" in rewrite_prompt and "一直在看 2025 年" in rewrite_prompt
    sql_prompt = pipe.llms.sql.prompts[0]
    assert "SELECT region_name" in sql_prompt and "2025 年华东区每月的销售额" in sql_prompt


def test_llm_chart_fallback(catalog, business_db):
    many = "SELECT product_name, SUM(quantity) AS qty FROM order_items JOIN products USING(product_id) GROUP BY 1"
    pipe = make(catalog, business_db, fast=["query", '{"chart_type":"bar","x_field":"product_name","y_fields":["qty"],"sort":"desc"}'],
                sql=[many])
    _, out = run(pipe, "各商品销量")
    assert out.chart_spec.chart_type == "bar" and out.chart_spec.sort == "desc"


def test_llm_chart_bad_fields_fall_back_to_table(catalog, business_db):
    many = "SELECT product_name, SUM(quantity) AS qty FROM order_items JOIN products USING(product_id) GROUP BY 1"
    pipe = make(catalog, business_db, fast=["query", '{"chart_type":"bar","x_field":"nope","y_fields":["qty"]}'],
                sql=[many])
    _, out = run(pipe, "各商品销量")
    assert out.chart_spec.chart_type == "table"


def test_llm_failure_becomes_error_event(catalog, business_db):
    pipe = make(catalog, business_db, fast=["query"])
    pipe.llms.sql = FailingLLM()
    events, out = run(pipe, "x")
    assert events[-1].event == "error" and events[-1].data.code == "LLM_ERROR"
    assert "network down" in out.error_message


@pytest.mark.parametrize("text, expected", [
    ("query", "query"), (" Chitchat\n", "chitchat"), ("意图：clarify", "clarify"), ("??", "query"),
])
def test_parse_intent(text, expected):
    assert parse_intent(text) == expected


def test_parse_chart_spec():
    assert parse_chart_spec('好的：{"chart_type":"pie","x_field":"a","y_fields":["b"]}', "t").chart_type == "pie"
    assert parse_chart_spec("no json", "t") is None
    assert parse_chart_spec('{"chart_type":"radar"}', "t") is None


def test_summaries():
    r = QueryResult(columns=["region", "sales"], rows=[["华东", 1234.5], ["华南", 99.0]], elapsed_ms=1)
    s = insight_summary(r)
    assert "共 2 行" in s and "最大 1,234.50" in s and "华东 | 1,234.50" in s
    assert memory_summary(r, head=1).endswith("……共 2 行")
