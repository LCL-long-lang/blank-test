"""路由依赖：服务实例的创建集中在这里，测试可用 app.dependency_overrides 替换。"""
from app.agent import Pipeline, default_llms
from app.agent.pipeline import AgentLLMs
from app.db.schema import get_catalog
from app.services.chart_service import ChartService
from app.services.chat_service import ChatService
from app.services.session_service import SessionService


def get_session_service() -> SessionService:
    return SessionService()


def get_chart_service() -> ChartService:
    return ChartService()


def get_llms() -> AgentLLMs:
    return default_llms()


def get_chat_service() -> ChatService:
    llms = get_llms()
    return ChatService(pipeline_factory=lambda: Pipeline(llms=llms, catalog=get_catalog()), llms=llms)
