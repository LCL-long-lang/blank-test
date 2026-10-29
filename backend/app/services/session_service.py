"""会话管理：增删改查、历史消息、自动标题。仓储和 LLM 由构造参数注入。"""
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.common.errors import NotFoundError
from app.common.schemas import MessageOut, SessionOut
from app.repository import MessageRepo, SessionRepo, SessionRow
from app.repository.message_repo import MessageRow

DEFAULT_TITLE = "新对话"
TITLE_MAX_LEN = 15

TITLE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "为数据分析对话起一个标题：不超过 15 个字，概括用户的问题，不要标点和引号，只输出标题。"),
    ("human", "{question}"),
])


def to_session_out(s: SessionRow) -> SessionOut:
    return SessionOut(id=s.id, title=s.title, pinned=s.pinned, created_at=s.created_at, updated_at=s.updated_at)


def to_message_out(m: MessageRow) -> MessageOut:
    return MessageOut(id=m.id, session_id=m.session_id, role=m.role, content=m.content, sql=m.sql,
                      status=m.status, error=m.error, has_chart=m.has_chart, elapsed_ms=m.elapsed_ms,
                      created_at=m.created_at)


def clean_title(text: str, fallback: str) -> str:
    title = text.strip().splitlines()[0] if text.strip() else ""
    title = title.strip().strip("\"'“”《》「」。.!！?？：:").removeprefix("标题").strip("：: ")
    return (title or fallback)[:TITLE_MAX_LEN]


class SessionService:
    def __init__(self, sessions: SessionRepo | None = None, messages: MessageRepo | None = None):
        self.sessions = sessions or SessionRepo()
        self.messages = messages or MessageRepo()

    def _require(self, session_id: str) -> SessionRow:
        s = self.sessions.get(session_id)
        if s is None:
            raise NotFoundError("会话不存在")
        return s

    def create(self, title: str | None = None) -> SessionOut:
        return to_session_out(self.sessions.create((title or "").strip() or DEFAULT_TITLE))

    def list(self, keyword: str | None = None) -> list[SessionOut]:
        return [to_session_out(s) for s in self.sessions.list((keyword or "").strip() or None)]

    def get(self, session_id: str) -> SessionOut:
        return to_session_out(self._require(session_id))

    def update(self, session_id: str, *, title: str | None = None, pinned: bool | None = None) -> SessionOut:
        if title is not None:
            title = title.strip()
            if not title:
                title = None
        if not self.sessions.update(session_id, title=title, pinned=pinned):
            raise NotFoundError("会话不存在")
        return self.get(session_id)

    def delete(self, session_id: str) -> None:
        if not self.sessions.delete(session_id):
            raise NotFoundError("会话不存在")

    def list_messages(self, session_id: str) -> list[MessageOut]:
        self._require(session_id)
        return [to_message_out(m) for m in self.messages.list_by_session(session_id)]

    def needs_title(self, session_id: str) -> bool:
        """只有标题还是默认值（用户没改过）时才自动生成。"""
        s = self.sessions.get(session_id)
        return s is not None and s.title == DEFAULT_TITLE

    async def generate_title(self, session_id: str, question: str, llm: BaseChatModel) -> str | None:
        """用快模型生成标题并保存；模型失败时退回问题前 15 字，不影响主流程。"""
        if not self.needs_title(session_id):
            return None
        fallback = question.strip()[:TITLE_MAX_LEN]
        try:
            text = await (TITLE_PROMPT | llm | StrOutputParser()).ainvoke({"question": question})
            title = clean_title(text, fallback)
        except Exception:
            title = fallback
        self.sessions.update(session_id, title=title)
        return title
