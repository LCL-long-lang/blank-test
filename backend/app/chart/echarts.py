"""ChartSpec + 数据 → ECharts option（纯函数）。

模型只出 Spec，option 由这里的确定性代码生成，保证前端拿到的配置一定能渲染。
"""
from typing import Any

from app.common.errors import ChartError
from app.common.schemas import ChartSpec

PALETTE = ["#5470c6", "#91cc75", "#fac858", "#ee6666", "#73c0de",
           "#3ba272", "#fc8452", "#9a60b4", "#ea7ccc", "#2f4554"]
DATAZOOM_THRESHOLD = 20


def _col(columns: list[str], name: str | None) -> int:
    if name is None or name not in columns:
        raise ChartError(f"图表字段 {name} 不在查询结果中")
    return columns.index(name)


def _num(v: Any) -> float | int | None:
    if v is None:
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _base(spec: ChartSpec) -> dict[str, Any]:
    return {
        "color": PALETTE,
        "title": {"text": spec.title, "left": "center", "textStyle": {"fontSize": 14}},
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 16, "right": 24, "top": 56, "bottom": 32, "containLabel": True},
    }


def _ordered_unique(values: list[Any]) -> list[Any]:
    seen: dict[Any, None] = {}
    for v in values:
        seen.setdefault(v, None)
    return list(seen)


def _cartesian(spec: ChartSpec, columns: list[str], rows: list[list[Any]]) -> dict[str, Any]:
    xi = _col(columns, spec.x_field)
    is_line = spec.chart_type == "line"
    stacked = spec.chart_type == "stacked_bar"
    series_type = "line" if is_line else "bar"

    if spec.series_field:
        yi, si = _col(columns, spec.y_fields[0]), _col(columns, spec.series_field)
        x_values = _ordered_unique([r[xi] for r in rows])
        s_values = _ordered_unique([r[si] for r in rows])
        grid = {(r[xi], r[si]): _num(r[yi]) for r in rows}
        series = [{
            "name": str(s), "type": series_type,
            "data": [grid.get((x, s)) for x in x_values],
            **({"stack": "total"} if stacked else {}),
            **({"smooth": True, "connectNulls": True} if is_line else {}),
        } for s in s_values]
    else:
        y_idx = [_col(columns, y) for y in spec.y_fields]
        data_rows = rows
        if spec.sort and len(y_idx) == 1:
            data_rows = sorted(rows, key=lambda r: (_num(r[y_idx[0]]) is None, _num(r[y_idx[0]]) or 0),
                               reverse=spec.sort == "desc")
            if spec.sort == "desc":  # reverse 后 None 会排到最前，挪回最后
                data_rows = [r for r in data_rows if _num(r[y_idx[0]]) is not None] + \
                            [r for r in data_rows if _num(r[y_idx[0]]) is None]
        x_values = [r[xi] for r in data_rows]
        series = [{
            "name": columns[i], "type": series_type,
            "data": [_num(r[i]) for r in data_rows],
            **({"smooth": True} if is_line else {}),
        } for i in y_idx]

    option = _base(spec)
    option["legend"] = {"top": 28, "type": "scroll"} if len(series) > 1 else {"show": False}
    option["xAxis"] = {"type": "category", "data": [str(x) for x in x_values],
                       "boundaryGap": not is_line, "axisLabel": {"hideOverlap": True}}
    option["yAxis"] = {"type": "value"}
    option["series"] = series
    if len(x_values) > DATAZOOM_THRESHOLD:
        option["dataZoom"] = [{"type": "inside"}, {"type": "slider", "height": 16, "bottom": 4}]
        option["grid"]["bottom"] = 48
    return option


def _pie(spec: ChartSpec, columns: list[str], rows: list[list[Any]]) -> dict[str, Any]:
    xi, yi = _col(columns, spec.x_field), _col(columns, spec.y_fields[0])
    totals: dict[Any, float] = {}
    for r in rows:  # 同名类别合并（切换类型时可能有系列列）
        totals[r[xi]] = totals.get(r[xi], 0) + (_num(r[yi]) or 0)
    option = _base(spec)
    option["tooltip"] = {"trigger": "item", "formatter": "{b}: {c} ({d}%)"}
    option["legend"] = {"top": 28, "type": "scroll"}
    option.pop("grid")
    option["series"] = [{
        "name": columns[yi], "type": "pie", "radius": ["35%", "65%"], "center": ["50%", "58%"],
        "data": [{"name": str(k), "value": v} for k, v in totals.items()],
        "label": {"formatter": "{b}\n{d}%"},
    }]
    return option


def _scatter(spec: ChartSpec, columns: list[str], rows: list[list[Any]]) -> dict[str, Any]:
    xi, yi = _col(columns, spec.x_field), _col(columns, spec.y_fields[0])
    option = _base(spec)
    option["tooltip"] = {"trigger": "item"}
    option["xAxis"] = {"type": "value", "name": columns[xi], "scale": True}
    option["yAxis"] = {"type": "value", "name": columns[yi], "scale": True}
    option["series"] = [{"type": "scatter", "symbolSize": 8,
                         "data": [[_num(r[xi]), _num(r[yi])] for r in rows]}]
    return option


def _kpi(spec: ChartSpec, columns: list[str], rows: list[list[Any]]) -> dict[str, Any]:
    """指标卡不是 ECharts 图形，返回约定结构，前端识别 kind='kpi' 后用卡片渲染。"""
    row = rows[0] if rows else [None] * len(columns)
    fields = spec.y_fields or columns
    return {
        "kind": "kpi",
        "title": {"text": spec.title},
        "items": [{"label": f, "value": _num(row[_col(columns, f)])} for f in fields],
    }


def _table(spec: ChartSpec, columns: list[str], _: list[list[Any]]) -> dict[str, Any]:
    """表格同样由前端用数据表组件渲染，option 只带标题和列。"""
    return {"kind": "table", "title": {"text": spec.title}, "columns": columns}


_BUILDERS = {
    "line": _cartesian, "bar": _cartesian, "stacked_bar": _cartesian,
    "pie": _pie, "scatter": _scatter, "kpi": _kpi, "table": _table,
}


def build_echarts_option(spec: ChartSpec, columns: list[str], rows: list[list[Any]]) -> dict[str, Any]:
    if spec.chart_type not in {"kpi", "table"} and not spec.y_fields:
        raise ChartError("图表缺少数值字段")
    return _BUILDERS[spec.chart_type](spec, columns, rows)
