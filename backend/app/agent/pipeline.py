"""NL2SQL 显式管道：改写 → 意图 → Schema → SQL 生成 → 校验 → 执行 →（纠错 ≤3）→ 图表 → 解读。

- 以异步生成器产出 AgentEvent，每完成一步就推一个事件，由 ChatService 转成 SSE。
- LLM、Catalog、查询函数都通过构造参数注入：测试时换成假实现，不访问网络和真实数据库。
- 本模块不读写 app.db，不感知会话；落库和记忆由上层 services 负责。
"""
import json
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import date

from fastapi.concurrency import run_in_threadpool
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser

from app.agent import prompts
from app.agent.schemas import AgentEvent, AgentInput, AgentOutcome, Intent
from app.agent.summary import insight_summary, memory_summary
from app.chart import build_echarts_option, make_title, recommend
from app.common.errors import AppError, ChartError, LLMError, SQLExecError, SQLGuardError
from app.common.schemas import (ChartEvent, ChartSpec, DataEvent, ErrorEvent, SqlEvent,
                                StepEvent, TextEvent)
from app.config import settings
from app.db.business import QueryResult, run_readonly_query
from app.db.schema import Catalog
from app.sql_guard import strip_sql, validate_and_rewrite

MAX_ATTEMPTS = 3
_CANNOT = re.compile(r"^\s*CANNOT_ANSWER\s*[:：]\s*(.*)", re.S)
_JSON = re.compile(r"\{.*\}", re.S)

STEP_LABELS = {
    "rewrite": "理解问题",
    "intent": "识别意图",
    "schema": "定位数据表",
    "generate_sql": "生成 SQL",
    "execute": "执行查询",
    "chart": "生成图表",
    "insight": "解读结果",
}


@dataclass
class AgentLLMs:
    sql: BaseChatModel
    fast: BaseChatModel
    chat: BaseChatModel


def default_llms() -> AgentLLMs:
    from app.llm.client import get_chat_llm, get_fast_llm, get_sql_llm

    return AgentLLMs(sql=get_sql_llm(), fast=get_fast_llm(), chat=get_chat_llm())


def _step(key: str, status: str = "done", detail: str | None = None) -> AgentEvent:
    return AgentEvent("step", StepEvent(key=key, status=status, label=STEP_LABELS[key], detail=detail))


def parse_intent(text: str) -> Intent:
    t = text.strip().lower()
    for intent in ("chitchat", "clarify", "query"):
        if intent in t:
            return intent
    return "query"


def parse_chart_spec(text: str, title: str) -> ChartSpec | None:
    m = _JSON.search(text)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        data["title"] = title
        return ChartSpec.model_validate(data)
    except (ValueError, TypeError):
        return None


@dataclass
class Pipeline:
    llms: AgentLLMs
    catalog: Catalog
    query_fn: Callable[[str], QueryResult] = field(default=run_readonly_query)
    max_rows: int = field(default_factory=lambda: settings.sql_max_rows)
    today: Callable[[], date] = date.today

    # ---------- LLM 调用（统一转 LLMError） ----------

    async def _invoke(self, llm: BaseChatModel, prompt, **kw) -> str:
        try:
            return await (prompt | llm | StrOutputParser()).ainvoke(kw)
        except AppError:
            raise
        except Exception as exc:  # 网络、鉴权、限流等
            raise LLMError(f"大模型调用失败：{exc}") from exc

    async def _stream(self, prompt, **kw) -> AsyncIterator[str]:
        try:
            async for chunk in (prompt | self.llms.chat | StrOutputParser()).astream(kw):
                if chunk:
                    yield chunk
        except Exception as exc:
            raise LLMError(f"大模型调用失败：{exc}") from exc

    @property
    def _table_labels(self) -> str:
        return "、".join(f"{t.label or t.name}（{t.name}）" for t in self.catalog.tables)

    # ---------- 各步骤 ----------

    async def rewrite(self, inp: AgentInput) -> str:
        if not inp.history and not inp.summary:
            return inp.question
        text = await self._invoke(
            self.llms.fast, prompts.REWRITE_PROMPT,
            summary_block=prompts.format_summary_block(inp.summary),
            history=prompts.format_history(inp.history),
            question=inp.question,
        )
        return text.strip().strip("\"'“”") or inp.question

    async def classify(self, question: str) -> Intent:
        text = await self._invoke(self.llms.fast, prompts.INTENT_PROMPT,
                                  table_labels=self._table_labels, question=question)
        return parse_intent(text)

    async def generate_sql(self, question: str, inp: AgentInput,
                           last_sql: str | None, last_error: str | None) -> str:
        return await self._invoke(
            self.llms.sql, prompts.SQL_PROMPT,
            schema=self.catalog.context,
            few_shots=prompts.format_few_shots(self.catalog.examples),
            today=self.today().isoformat(),
            history_block=prompts.format_history_block(inp.history, inp.summary),
            question=question,
            retry_block=prompts.format_retry_block(last_sql, last_error),
        )

    async def recommend_chart(self, question: str, result: QueryResult) -> tuple[ChartSpec, dict]:
        spec = recommend(result.columns, result.rows, question)
        if spec is None:
            text = await self._invoke(self.llms.fast, prompts.CHART_PROMPT,
                                      question=question, result=insight_summary(result, head=10))
            spec = parse_chart_spec(text, make_title(question))
        if spec is not None:
            try:
                return spec, build_echarts_option(spec, result.columns, result.rows)
            except ChartError:
                pass  # 模型给的字段不对：退回表格
        spec = ChartSpec(chart_type="table", title=make_title(question))
        return spec, build_echarts_option(spec, result.columns, result.rows)

    # ---------- 编排 ----------

    async def run(self, inp: AgentInput) -> AsyncIterator[AgentEvent]:
        out = AgentOutcome()
        try:
            async for ev in self._run(inp, out):
                yield ev
        except AppError as exc:
            out.error_code, out.error_message = exc.code, exc.message
            yield AgentEvent("error", ErrorEvent(code=exc.code, message=exc.message,
                                                 retryable=not isinstance(exc, SQLGuardError)))
        yield AgentEvent("final", out)

    async def _answer(self, prompt, out: AgentOutcome, **kw) -> AsyncIterator[AgentEvent]:
        async for delta in self._stream(prompt, **kw):
            out.answer += delta
            yield AgentEvent("text", TextEvent(delta=delta))

    async def _run(self, inp: AgentInput, out: AgentOutcome) -> AsyncIterator[AgentEvent]:
        # 1. 改写
        yield _step("rewrite", "running")
        question = await self.rewrite(inp)
        out.rewritten_question = question
        yield _step("rewrite", detail=question)

        # 2. 意图
        out.intent = await self.classify(question)
        yield _step("intent", detail={"query": "查询数据", "chitchat": "闲聊",
                                      "clarify": "需要补充信息"}[out.intent])
        if out.intent != "query":
            prompt = prompts.CHITCHAT_PROMPT if out.intent == "chitchat" else prompts.CLARIFY_PROMPT
            async for ev in self._answer(prompt, out, table_labels=self._table_labels, question=question):
                yield ev
            return

        # 3. Schema 上下文（表少，全量注入）
        yield _step("schema", detail=f"{len(self.catalog.tables)} 张表")

        # 4~7. 生成 → 校验 → 执行，失败带错误重试
        async for ev in self._query_with_retry(question, inp, out):
            yield ev
        if out.result is None:
            return  # CANNOT_ANSWER，已输出说明

        # 8. 图表
        yield _step("chart", "running")
        spec, option = await self.recommend_chart(question, out.result)
        out.chart_spec, out.chart_option = spec, option
        yield AgentEvent("chart", ChartEvent(spec=spec, option=option))
        yield _step("chart", detail=spec.chart_type)

        # 9. 解读
        yield _step("insight", "running")
        if out.result.total == 0:
            msg = "没有查询到符合条件的数据，可以尝试放宽时间范围或筛选条件。"
            out.answer = msg
            yield AgentEvent("text", TextEvent(delta=msg))
        else:
            async for ev in self._answer(prompts.INSIGHT_PROMPT, out, question=question,
                                         summary=insight_summary(out.result)):
                yield ev
        yield _step("insight")

    async def _query_with_retry(self, question: str, inp: AgentInput,
                                out: AgentOutcome) -> AsyncIterator[AgentEvent]:
        last_sql: str | None = None
        last_error: str | None = None
        empty_retried = False
        for attempt in range(1, MAX_ATTEMPTS + 1):
            out.attempts = attempt
            yield _step("generate_sql", "running", detail=f"第 {attempt} 次" if attempt > 1 else None)
            raw = await self.generate_sql(question, inp, last_sql, last_error)

            cannot = _CANNOT.match(strip_sql(raw))
            if cannot:
                reason = cannot.group(1).strip() or "现有数据无法回答这个问题"
                yield _step("generate_sql", detail="无法用现有数据回答")
                msg = f"抱歉，{reason}。可以换个问法，或询问订单、商品、客户、地区相关的数据。"
                out.answer = msg
                yield AgentEvent("text", TextEvent(delta=msg))
                return

            try:
                sql = validate_and_rewrite(raw, self.catalog.table_names, self.max_rows)
            except SQLGuardError as exc:
                last_sql, last_error = strip_sql(raw), exc.message
                yield _step("generate_sql", "error", detail=exc.message)
                continue

            out.sql = sql
            yield AgentEvent("sql", SqlEvent(sql=sql, attempt=attempt))
            yield _step("generate_sql")

            yield _step("execute", "running")
            try:
                result = await run_in_threadpool(self.query_fn, sql)
            except SQLExecError as exc:
                last_sql, last_error = sql, exc.message
                yield _step("execute", "error", detail=exc.message)
                continue

            # 0 行视为软错误，重试一次；再次为空则接受
            if result.total == 0 and not empty_retried and attempt < MAX_ATTEMPTS:
                empty_retried = True
                last_sql, last_error = sql, prompts.EMPTY_RESULT_HINT
                yield _step("execute", "error", detail="结果为空，尝试调整条件")
                continue

            out.result = result
            out.result_summary = memory_summary(result)
            yield AgentEvent("data", DataEvent(columns=result.columns, rows=result.rows,
                                               total=result.total, truncated=result.truncated))
            yield _step("execute", detail=f"{result.total} 行，{result.elapsed_ms} ms")
            return

        raise SQLExecError(f"SQL 连续 {MAX_ATTEMPTS} 次执行失败：{last_error}")
