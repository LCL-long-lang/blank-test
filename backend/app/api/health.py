from fastapi import APIRouter

from app import __version__
from app.common.response import ApiResponse
from app.common.schemas import HealthOut
from app.config import settings
from app.db import business
from app.llm.client import is_configured

router = APIRouter(tags=["health"])


@router.get("/health", response_model=ApiResponse[HealthOut])
def health():
    return ApiResponse(
        data=HealthOut(
            version=__version__,
            business_db=business.is_available(),
            app_db=settings.app_db_path.exists(),
            llm_configured=is_configured(),
        )
    )
