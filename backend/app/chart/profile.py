"""结果画像：判断每一列是时间、数值还是类别（纯函数）。"""
import re
from dataclasses import dataclass
from typing import Any, Literal

ColumnKind = Literal["temporal", "numeric", "categorical"]

_TEMPORAL_VALUE = re.compile(
    r"^\d{4}(-\d{2}(-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?)?)?$"  # 2025 / 2025-06 / 2025-06-18 / 带时间
    r"|^\d{4}-(Q[1-4]|W\d{2})$"                              # 2025-Q2 / 2025-W23
)
# 值是 01~12 这类短数字串时，靠列名判断是否为时间
_TEMPORAL_NAMES = {"month", "day", "week", "quarter", "hour", "year",
                   "月", "月份", "日", "日期", "周", "小时", "季度", "年", "年份"}
_ID_NAME = re.compile(r"(^id$|_id$|编号$|ID$)")


@dataclass
class ColumnProfile:
    name: str
    kind: ColumnKind
    cardinality: int


@dataclass
class ResultProfile:
    columns: list[ColumnProfile]
    row_count: int

    def of_kind(self, kind: ColumnKind) -> list[ColumnProfile]:
        return [c for c in self.columns if c.kind == kind]

    @property
    def temporal(self) -> list[ColumnProfile]:
        return self.of_kind("temporal")

    @property
    def numeric(self) -> list[ColumnProfile]:
        return self.of_kind("numeric")

    @property
    def categorical(self) -> list[ColumnProfile]:
        return self.of_kind("categorical")


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _classify(name: str, values: list[Any]) -> ColumnKind:
    non_null = [v for v in values if v is not None]
    if not non_null:
        return "categorical"
    if _ID_NAME.search(name):
        return "categorical"
    if all(_is_number(v) for v in non_null):
        return "numeric"
    as_str = [str(v) for v in non_null]
    if all(_TEMPORAL_VALUE.match(s) for s in as_str):
        return "temporal"
    if name.lower() in _TEMPORAL_NAMES and all(s.isdigit() and len(s) <= 2 for s in as_str):
        return "temporal"
    return "categorical"


def profile(columns: list[str], rows: list[list[Any]]) -> ResultProfile:
    cols = []
    for i, name in enumerate(columns):
        values = [r[i] for r in rows]
        cols.append(ColumnProfile(name=name, kind=_classify(name, values),
                                  cardinality=len({v for v in values if v is not None})))
    return ResultProfile(columns=cols, row_count=len(rows))
