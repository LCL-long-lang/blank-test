"""流式问答 POST /api/chat/stream（第 5.2 节）。"""
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sse_starlette import EventSourceResponse, ServerSentEvent

from app.api.deps import get_chat_service
from app.common.schemas import ChatRequest
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])

PING_SECONDS = 15


def _sse(event: str, data) -> ServerSentEvent:
    return ServerSentEvent(event=event, data=json.dumps(data.model_dump(mode="json"), ensure_ascii=False,
                                                        default=str))


@router.post("/stream")
async def chat_stream(body: ChatRequest, request: Request,
                      svc: Annotated[ChatService, Depends(get_chat_service)]):
    # 会话校验和消息写入在流开始前完成：会话不存在时直接返回 404 JSON，而不是空流
    user_id, message_id = svc.prepare(body.session_id, body.question)

    async def events():
        async for event, data in svc.stream(body.session_id, body.question, user_id, message_id):
            if await request.is_disconnected():
                break  # 退出后生成器被关闭，ChatService 在 finally 中标记 cancelled
            yield _sse(event, data)

    return EventSourceResponse(events(), ping=PING_SECONDS, headers={"X-Accel-Buffering": "no"})
