"""图表回看与类型切换。"""
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_chart_service
from app.common.response import ApiResponse
from app.common.schemas import ChartOut, ChartRenderRequest
from app.services.chart_service import ChartService

router = APIRouter(prefix="/charts", tags=["charts"])
Service = Annotated[ChartService, Depends(get_chart_service)]


@router.get("/{message_id}", response_model=ApiResponse[ChartOut])
def get_chart(message_id: str, svc: Service):
    return ApiResponse(data=svc.get(message_id))


@router.post("/{message_id}/render", response_model=ApiResponse[ChartOut])
def render_chart(message_id: str, body: ChartRenderRequest, svc: Service):
    return ApiResponse(data=svc.render(message_id, body.chart_type))
