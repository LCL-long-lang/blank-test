"""agent 模块的输入输出结构（模块内部使用，对外的 SSE 契约在 common/schemas.py）。"""
from dataclasses import dataclass, field
from typing import Any, Literal

from app.common.schemas import ChartSpec
from app.db.business import QueryResult

Intent = Literal["query", "chitchat", "clarify"]


@dataclass
class Turn:
    """一轮历史问答（由 memory 模块提供）。"""
    question: str
    rewritten_question: str | None = None
    sql: str | None = None
    result_summary: str | None = None
    answer: str | None = None


@dataclass
class AgentInput:
    question: str
    history: list[Turn] = field(default_factory=list)
    summary: str = ""


@dataclass
class AgentOutcome:
    """一次问答的最终结果，供 ChatService 落库和写记忆。"""
    rewritten_question: str = ""
    intent: Intent = "query"
    sql: str | None = None
    attempts: int = 0
    result: QueryResult | None = None
    result_summary: str | None = None
    chart_spec: ChartSpec | None = None
    chart_option: dict[str, Any] | None = None
    answer: str = ""
    error_code: str | None = None
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.error_code is None


@dataclass
class AgentEvent:
    """event 为 SSE 事件名（step/sql/data/chart/text/error），data 为对应的 Pydantic 模型；
    最后一个事件固定是 event='final'，data 为 AgentOutcome（不推给前端）。"""
    event: str
    data: Any
