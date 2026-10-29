"""前后端接口契约（与 frontend/src/types 一一对应，字段统一 snake_case）。"""
from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------- 会话 ----------

class SessionCreate(BaseModel):
    title: str | None = None


class SessionUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=50)
    pinned: bool | None = None


class SessionOut(BaseModel):
    id: str
    title: str
    pinned: bool
    created_at: str
    updated_at: str


# ---------- 消息 ----------

MessageRole = Literal["user", "assistant"]
MessageStatus = Literal["streaming", "done", "error", "cancelled"]


class MessageOut(BaseModel):
    id: str
    session_id: str
    role: MessageRole
    content: str
    sql: str | None = None
    status: MessageStatus = "done"
    error: str | None = None
    has_chart: bool = False
    elapsed_ms: int | None = None
    created_at: str


# ---------- 图表 ----------

ChartType = Literal["kpi", "line", "bar", "stacked_bar", "pie", "scatter", "table"]


class ChartSpec(BaseModel):
    chart_type: ChartType
    title: str
    x_field: str | None = None
    y_fields: list[str] = Field(default_factory=list)
    series_field: str | None = None
    sort: Literal["asc", "desc"] | None = None


class ChartOut(BaseModel):
    message_id: str
    spec: ChartSpec
    option: dict[str, Any]
    columns: list[str]
    rows: list[list[Any]]


class ChartRenderRequest(BaseModel):
    chart_type: ChartType


# ---------- 问答 ----------

class ChatRequest(BaseModel):
    session_id: str
    question: str = Field(..., min_length=1, max_length=500)


# ---------- SSE 事件（event 名 → data 结构） ----------

class StartEvent(BaseModel):
    message_id: str
    user_message_id: str


class StepEvent(BaseModel):
    key: Literal["rewrite", "intent", "schema", "generate_sql", "execute", "chart", "insight"]
    status: Literal["running", "done", "error"]
    label: str
    detail: str | None = None


class SqlEvent(BaseModel):
    sql: str
    attempt: int = 1


class DataEvent(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    total: int
    truncated: bool = False


class ChartEvent(BaseModel):
    spec: ChartSpec
    option: dict[str, Any]


class TextEvent(BaseModel):
    delta: str


class TitleEvent(BaseModel):
    session_id: str
    title: str


class ErrorEvent(BaseModel):
    code: str
    message: str
    retryable: bool = True


class DoneEvent(BaseModel):
    message_id: str
    elapsed_ms: int


SSE_EVENT_MODELS: dict[str, type[BaseModel]] = {
    "start": StartEvent,
    "step": StepEvent,
    "sql": SqlEvent,
    "data": DataEvent,
    "chart": ChartEvent,
    "text": TextEvent,
    "title": TitleEvent,
    "error": ErrorEvent,
    "done": DoneEvent,
}


# ---------- 可查询的数据（/api/schema） ----------

class SchemaColumnOut(BaseModel):
    name: str
    type: str
    description: str = ""


class SchemaTableOut(BaseModel):
    name: str
    label: str = ""
    description: str = ""
    row_count: int
    columns: list[SchemaColumnOut]


class SchemaOut(BaseModel):
    tables: list[SchemaTableOut]
    examples: list[str]  # 示例问题，前端欢迎页展示


# ---------- 健康检查 ----------

class HealthOut(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    business_db: bool
    app_db: bool
    llm_configured: bool
