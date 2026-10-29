"""REST 接口统一响应格式：{code, message, data}。"""
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: str = "OK"
    message: str = "success"
    data: T | None = None


def ok(data: Any = None) -> dict:
    return {"code": "OK", "message": "success", "data": data}


def fail(code: str, message: str) -> dict:
    return {"code": code, "message": message, "data": None}
