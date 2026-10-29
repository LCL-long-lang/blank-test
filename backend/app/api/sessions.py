"""会话接口（第 5.1 节）。"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_session_service
from app.common.response import ApiResponse
from app.common.schemas import MessageOut, SessionCreate, SessionOut, SessionUpdate
from app.services.session_service import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])
Service = Annotated[SessionService, Depends(get_session_service)]


@router.post("", response_model=ApiResponse[SessionOut])
def create_session(svc: Service, body: SessionCreate | None = None):
    return ApiResponse(data=svc.create(body.title if body else None))


@router.get("", response_model=ApiResponse[list[SessionOut]])
def list_sessions(svc: Service, keyword: Annotated[str | None, Query(max_length=50)] = None):
    return ApiResponse(data=svc.list(keyword))


@router.patch("/{session_id}", response_model=ApiResponse[SessionOut])
def update_session(session_id: str, body: SessionUpdate, svc: Service):
    return ApiResponse(data=svc.update(session_id, title=body.title, pinned=body.pinned))


@router.delete("/{session_id}", response_model=ApiResponse[None])
def delete_session(session_id: str, svc: Service):
    svc.delete(session_id)
    return ApiResponse()


@router.get("/{session_id}/messages", response_model=ApiResponse[list[MessageOut]])
def list_messages(session_id: str, svc: Service):
    return ApiResponse(data=svc.list_messages(session_id))
