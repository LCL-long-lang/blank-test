"""LangChain 消息历史：基于 app.db 的 messages 表读写 HumanMessage / AIMessage。

AI 消息的 additional_kwargs 带上 rewritten_question、sql、result_summary，供记忆模块拼成 Turn。
只读取状态为 done 的消息：出错、取消、生成中的轮次不进入上下文，避免干扰追问改写。
"""
from collections.abc import Sequence

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.repository import MessageRepo


class SQLiteChatMessageHistory(BaseChatMessageHistory):
    def __init__(self, session_id: str, messages: MessageRepo | None = None):
        self.session_id = session_id
        self.repo = messages or MessageRepo()

    @property
    def messages(self) -> list[BaseMessage]:  # type: ignore[override]
        result: list[BaseMessage] = []
        for m in self.repo.list_by_session(self.session_id):
            if m.status != "done":
                continue
            if m.role == "user":
                result.append(HumanMessage(content=m.content, id=m.id))
            else:
                result.append(AIMessage(content=m.content, id=m.id, additional_kwargs={
                    "rewritten_question": m.rewritten_query,
                    "sql": m.sql,
                    "result_summary": m.result_summary,
                }))
        return result

    def add_messages(self, messages: Sequence[BaseMessage]) -> None:
        for msg in messages:
            role = "user" if isinstance(msg, HumanMessage) else "assistant"
            row = self.repo.add(self.session_id, role, str(msg.content))
            kw = msg.additional_kwargs
            if role == "assistant" and kw:
                self.repo.finish(row.id, content=str(msg.content), status="done",
                                 rewritten_query=kw.get("rewritten_question"), sql=kw.get("sql"),
                                 result_summary=kw.get("result_summary"))

    def clear(self) -> None:
        self.repo.delete_by_session(self.session_id)
