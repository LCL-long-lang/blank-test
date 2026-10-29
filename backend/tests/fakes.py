"""测试用假 LLM：按顺序返回预设回复，并记录收到的 Prompt，支持流式。"""
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.agent import AgentLLMs


class RecordingFakeLLM(FakeListChatModel):
    """FakeListChatModel 按顺序返回 responses；prompts 记录每次调用的完整 Prompt 文本。"""
    prompts: list[str] = []

    def _call(self, messages, stop=None, run_manager=None, **kwargs):
        self.prompts.append("\n".join(str(m.content) for m in messages))
        return super()._call(messages, stop, run_manager, **kwargs)

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        self.prompts.append("\n".join(str(m.content) for m in messages))
        yield from super()._stream(messages, stop, run_manager, **kwargs)

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        self.prompts.append("\n".join(str(m.content) for m in messages))
        async for chunk in super()._astream(messages, stop, run_manager, **kwargs):
            yield chunk


class FailingLLM(FakeListChatModel):
    """模拟网络异常：每次调用都抛 ConnectionError。"""
    responses: list[str] = ["unused"]

    def _call(self, *args, **kwargs):
        raise ConnectionError("network down")


def fake(*responses: str) -> RecordingFakeLLM:
    return RecordingFakeLLM(responses=list(responses) or ["ok"], prompts=[])


def fake_llms(sql=(), fast=(), chat=("分析完成。",)) -> AgentLLMs:
    return AgentLLMs(sql=fake(*sql), fast=fake(*fast), chat=fake(*chat))
