"""可查询的表和字段（前端欢迎页“可以问什么”）。"""
from fastapi import APIRouter

from app.common.response import ApiResponse
from app.common.schemas import SchemaColumnOut, SchemaOut, SchemaTableOut
from app.db.schema import get_catalog

router = APIRouter(tags=["schema"])

EXAMPLE_LIMIT = 6


@router.get("/schema", response_model=ApiResponse[SchemaOut])
def get_schema():
    cat = get_catalog()
    tables = [SchemaTableOut(
        name=t.name, label=t.label, description=t.description, row_count=t.row_count,
        columns=[SchemaColumnOut(name=c.name, type=c.type, description=c.description) for c in t.columns],
    ) for t in cat.tables]
    # 每类图表各取一个示例，欢迎页的问题更多样
    picked, seen = [], set()
    for e in cat.examples:
        if e.get("chart") not in seen:
            seen.add(e.get("chart"))
            picked.append(e["question"])
    return ApiResponse(data=SchemaOut(tables=tables, examples=picked[:EXAMPLE_LIMIT]))
