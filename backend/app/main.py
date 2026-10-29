"""FastAPI 入口：路由注册、CORS、全局异常处理、启动初始化。"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import charts, chat, health, schema, sessions
from app.common.errors import AppError
from app.common.response import fail
from app.config import settings
from app.db import business
from app.db.app_db import init_db
from app.db.schema import get_catalog
from app.repository import MessageRepo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    stale = MessageRepo().mark_stale_streaming()
    if stale:
        logger.info("已将 %d 条中断的消息标记为 cancelled", stale)
    if business.is_available():
        get_catalog.cache_clear()
        logger.info("已加载业务库 Schema：%d 张表", len(get_catalog().tables))
    else:
        logger.warning("业务库不可用，请先运行 scripts/seed_business_db.py")
    yield


app = FastAPI(title="智能数据分析系统", version=__version__, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def handle_app_error(_: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content=fail(exc.code, exc.message))


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content=fail("VALIDATION_ERROR", str(exc.errors())))


@app.exception_handler(Exception)
async def handle_unexpected(_: Request, exc: Exception):
    logger.exception("未处理的异常")
    return JSONResponse(status_code=500, content=fail("INTERNAL_ERROR", "服务器内部错误"))


for module in (health, sessions, chat, charts, schema):
    app.include_router(module.router, prefix="/api")
