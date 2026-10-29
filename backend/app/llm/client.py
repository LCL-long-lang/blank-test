"""阿里云百炼 Qwen3 接入（OpenAI 兼容接口）。"""
from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.config import settings


def _build(model: str, temperature: float = 0, streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        temperature=temperature,
        streaming=streaming,
        max_retries=2,
        timeout=60,
        # Qwen3 混合思考模型：关闭思考以降低延迟
        extra_body={"enable_thinking": False},
    )


def is_configured() -> bool:
    return bool(settings.dashscope_api_key) and not settings.dashscope_api_key.startswith("sk-xxx")


@lru_cache
def get_sql_llm() -> ChatOpenAI:
    """SQL 生成：强模型、温度 0。"""
    return _build(settings.model_sql)


@lru_cache
def get_fast_llm() -> ChatOpenAI:
    """改写 / 意图 / 图表推荐 / 标题：快模型。"""
    return _build(settings.model_fast)


@lru_cache
def get_chat_llm() -> ChatOpenAI:
    """结果解读：流式输出。"""
    return _build(settings.model_fast, temperature=0.3, streaming=True)
