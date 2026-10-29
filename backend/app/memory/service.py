"""两级上下文记忆：短期窗口（最近 N 轮原样）+ 长期摘要（更早的轮次压缩成一段文字）。

- 每轮问答由 ChatService 写入 messages 表；本模块只负责读取和压缩，不重复写消息。
- sessions.summarized_turns 记录摘要已覆盖到第几轮，压缩是增量的：旧摘要 + 新滑出窗口的轮次 → 新摘要。
"""
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.agent.prompts import format_history
from app.agent.schemas import Turn
from app.config import settings
from app.memory.history import SQLiteChatMessageHistory
from app.repository import MessageRepo, SessionRepo

logger = logging.getLogger("app.memory")

SUMMARY_MAX_LEN = 300

COMPRESS_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "你负责压缩数据分析对话的历史，供后续追问时参考。\n"
     "把“已有摘要”和“新的对话”合并成一段不超过 200 字的摘要，保留：用户关注的指标、维度、"
     "时间范围、筛选条件和关键结论；去掉寒暄和重复内容。只输出摘要。"),
    ("human", "已有摘要：{summary}\n\n新的对话：\n{turns}"),
])


def messages_to_turns(messages: list[BaseMessage]) -> list[Turn]:
    """把 Human/AI 消息按顺序配对成 Turn；没有对应回答的问题（出错/取消）被跳过。"""
    turns: list[Turn] = []
    pending: HumanMessage | None = None
    for m in messages:
        if isinstance(m, HumanMessage):
            pending = m
        elif isinstance(m, AIMessage) and pending is not None:
            kw = m.additional_kwargs
            turns.append(Turn(question=str(pending.content), rewritten_question=kw.get("rewritten_question"),
                              sql=kw.get("sql"), result_summary=kw.get("result_summary"),
                              answer=str(m.content)))
            pending = None
    return turns


class MemoryService:
    def __init__(self, sessions: SessionRepo | None = None, messages: MessageRepo | None = None,
                 window: int | None = None):
        self.sessions = sessions or SessionRepo()
        self.messages = messages or MessageRepo()
        self.window = window or settings.memory_window

    def history(self, session_id: str) -> SQLiteChatMessageHistory:
        return SQLiteChatMessageHistory(session_id, self.messages)

    def all_turns(self, session_id: str) -> list[Turn]:
        return messages_to_turns(self.history(session_id).messages)

    def load_context(self, session_id: str) -> tuple[str, list[Turn]]:
        """返回 (长期摘要, 最近 window 轮)。"""
        s = self.sessions.get(session_id)
        summary = (s.summary or "") if s else ""
        return summary, self.all_turns(session_id)[-self.window:]

    def needs_compress(self, session_id: str) -> bool:
        s = self.sessions.get(session_id)
        if s is None:
            return False
        return len(self.all_turns(session_id)) - self.window > s.summarized_turns

    async def maybe_compress(self, session_id: str, llm: BaseChatModel) -> bool:
        """有轮次滑出窗口且尚未摘要时压缩。失败只记日志，不影响问答。返回是否更新了摘要。"""
        s = self.sessions.get(session_id)
        if s is None:
            return False
        turns = self.all_turns(session_id)
        upto = len(turns) - self.window
        if upto <= s.summarized_turns:
            return False
        new_turns = turns[s.summarized_turns:upto]
        try:
            text = await (COMPRESS_PROMPT | llm | StrOutputParser()).ainvoke({
                "summary": s.summary or "（无）",
                "turns": format_history(new_turns, with_sql=False),
            })
        except Exception:
            logger.exception("记忆压缩失败 session=%s", session_id)
            return False
        self.sessions.set_summary(session_id, text.strip()[:SUMMARY_MAX_LEN], upto)
        return True
