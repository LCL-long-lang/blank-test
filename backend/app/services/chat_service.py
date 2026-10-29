"""编排一次问答：保存用户消息 → 加载记忆 → 运行 agent → 转发事件 → 落库 → 标题 / 记忆压缩。

产出 (event, data) 二元组，data 为 Pydantic 模型；api 层负责序列化成 SSE。
客户端断开时 api 层取消生成器，这里在 finally 中把消息标记为 cancelled。
"""
import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable

from pydantic import BaseModel

from app.agent import AgentInput, AgentOutcome, Pipeline
from app.agent.pipeline import AgentLLMs
from app.common.errors import NotFoundError
from app.common.schemas import DoneEvent, ErrorEvent, StartEvent, TitleEvent
from app.memory import MemoryService
from app.repository import ChartRepo, MessageRepo, SessionRepo
from app.services.session_service import SessionService

logger = logging.getLogger("app.chat")

ChatEvent = tuple[str, BaseModel]
_background: set[asyncio.Task] = set()


class ChatService:
    def __init__(self, pipeline_factory: Callable[[], Pipeline], llms: AgentLLMs,
                 sessions: SessionRepo | None = None, messages: MessageRepo | None = None,
                 charts: ChartRepo | None = None, memory: MemoryService | None = None):
        self.pipeline_factory = pipeline_factory
        self.llms = llms
        self.sessions = sessions or SessionRepo()
        self.messages = messages or MessageRepo()
        self.charts = charts or ChartRepo()
        self.memory = memory or MemoryService(self.sessions, self.messages)
        self.session_service = SessionService(self.sessions, self.messages)

    def prepare(self, session_id: str, question: str) -> tuple[str, str]:
        """流开始前同步执行：校验会话、写入用户消息和 AI 占位消息。会话不存在时抛 404。"""
        if self.sessions.get(session_id) is None:
            raise NotFoundError("会话不存在")
        user = self.messages.add(session_id, "user", question.strip())
        ai = self.messages.add(session_id, "assistant", "", status="streaming")
        self.sessions.touch(session_id)
        return user.id, ai.id

    async def stream(self, session_id: str, question: str,
                     user_message_id: str, message_id: str) -> AsyncIterator[ChatEvent]:
        started = time.perf_counter()
        outcome: AgentOutcome | None = None
        answer = ""
        finished = False
        yield "start", StartEvent(message_id=message_id, user_message_id=user_message_id)
        try:
            # 记忆排除当前这轮（它还没有完成，状态是 streaming）
            summary, history = self.memory.load_context(session_id)
            inp = AgentInput(question=question.strip(), history=history, summary=summary)

            async for ev in self.pipeline_factory().run(inp):
                if ev.event == "final":
                    outcome = ev.data
                    continue
                if ev.event == "text":
                    answer += ev.data.delta
                yield ev.event, ev.data

            elapsed = int((time.perf_counter() - started) * 1000)
            self._save(message_id, outcome, elapsed)
            finished = True

            if outcome and outcome.ok:
                title = await self.session_service.generate_title(session_id, question, self.llms.fast)
                if title:
                    yield "title", TitleEvent(session_id=session_id, title=title)
                # 记忆压缩放到后台，不阻塞 done；保留引用防止任务被 GC
                task = asyncio.create_task(self._compress(session_id))
                _background.add(task)
                task.add_done_callback(_background.discard)

            self.sessions.touch(session_id)
            yield "done", DoneEvent(message_id=message_id, elapsed_ms=elapsed)
        except Exception as exc:  # 未预期错误：推 error 并标记消息
            if isinstance(exc, (asyncio.CancelledError, GeneratorExit)):
                raise
            logger.exception("问答流程异常 session=%s", session_id)
            self.messages.finish(message_id, content=answer, status="error", error=str(exc),
                                 elapsed_ms=int((time.perf_counter() - started) * 1000))
            finished = True
            yield "error", ErrorEvent(code="INTERNAL_ERROR", message="服务器内部错误", retryable=True)
        finally:
            if not finished:  # 客户端断开 / 任务被取消
                self.messages.finish(message_id, content=answer, status="cancelled",
                                     elapsed_ms=int((time.perf_counter() - started) * 1000))
                logger.info("问答已取消 message=%s", message_id)

    def _save(self, message_id: str, out: AgentOutcome | None, elapsed_ms: int) -> None:
        if out is None:
            self.messages.finish(message_id, content="", status="error", error="未产生结果",
                                 elapsed_ms=elapsed_ms)
            return
        self.messages.finish(
            message_id, content=out.answer, status="done" if out.ok else "error",
            rewritten_query=out.rewritten_question or None, sql=out.sql,
            result_summary=out.result_summary, error=out.error_message, elapsed_ms=elapsed_ms,
        )
        if out.ok and out.result is not None and out.chart_spec is not None:
            self.charts.save(message_id, out.chart_spec.model_dump(), out.chart_option or {},
                             out.result.columns, out.result.rows)

    async def _compress(self, session_id: str) -> None:
        try:
            await self.memory.maybe_compress(session_id, self.llms.fast)
        except Exception:
            logger.exception("记忆压缩失败 session=%s", session_id)
