"""图表推荐（纯函数）：规则优先，规则判断不了时返回 None，由 agent 决定是否交给 LLM。

规则：
- 0 行 → table
- 1 行且全是数值 → kpi
- 时间列 + 数值 → line（有 1 个类别列时按它分系列）
- 1 类别 + 1 数值，类别 ≤ 6 且问题含“占比/构成/分布/比例” → pie
- 1 类别 + 数值，类别 ≤ 30 → bar（单数值时降序）
- 2 类别 + 1 数值 → stacked_bar
- 只有 2 个数值列 → scatter
- 只有类别列 / 其余多维明细 → table
- 1 类别 + 数值但类别 > 30 → None（交给 LLM 判断，如取 Top N 画柱图或直接表格）
"""
import re

from app.common.errors import ChartError
from app.chart.profile import ResultProfile, profile
from app.common.schemas import ChartSpec, ChartType

PIE_MAX_SLICES = 6
BAR_MAX_CATEGORIES = 30
_PIE_WORDS = re.compile(r"占比|构成|分布|比例|份额|比重")


def make_title(question: str, limit: int = 30) -> str:
    title = question.strip().rstrip("？?。！!").strip()
    return title if len(title) <= limit else title[: limit - 1] + "…"


def recommend_by_rules(p: ResultProfile, question: str = "") -> ChartSpec | None:
    title = make_title(question) if question else "查询结果"
    num, cat, tmp = p.numeric, p.categorical, p.temporal

    def spec(chart_type: ChartType, **kw) -> ChartSpec:
        return ChartSpec(chart_type=chart_type, title=title, **kw)

    if p.row_count == 0:
        return spec("table")
    if p.row_count == 1 and num and len(num) == len(p.columns):
        return spec("kpi", y_fields=[c.name for c in num])
    if not num:
        return spec("table")

    if len(tmp) == 1 and len(cat) <= 1:
        if cat:
            return spec("line", x_field=tmp[0].name, y_fields=[num[0].name], series_field=cat[0].name)
        return spec("line", x_field=tmp[0].name, y_fields=[c.name for c in num])

    # 两个时间列（如 year + month 同比）：一个做横轴，另一个做系列
    if len(tmp) == 2 and not cat and len(num) == 1:
        x, s = sorted(tmp, key=lambda c: -c.cardinality)
        return spec("line", x_field=x.name, y_fields=[num[0].name], series_field=s.name)

    if not tmp and len(cat) == 1:
        c = cat[0]
        if c.cardinality <= PIE_MAX_SLICES and _PIE_WORDS.search(question):
            # 模型常同时返回“数量 + 比例”两列，饼图用第一个数值列，比例由 ECharts 自动计算
            return spec("pie", x_field=c.name, y_fields=[num[0].name])
        if c.cardinality <= BAR_MAX_CATEGORIES:
            sort = "desc" if len(num) == 1 else None
            return spec("bar", x_field=c.name, y_fields=[x.name for x in num], sort=sort)
        return None  # 类别太多：交给 LLM 或表格

    if not tmp and len(cat) == 2 and len(num) == 1:
        x, s = sorted(cat, key=lambda c: c.cardinality)  # 基数小的做横轴更易读
        return spec("stacked_bar", x_field=x.name, y_fields=[num[0].name], series_field=s.name)

    if not tmp and not cat and len(num) == 2:
        return spec("scatter", x_field=num[0].name, y_fields=[num[1].name])

    # 多维明细（如“前 10 位客户的姓名、等级、金额”）：表格最清楚
    return spec("table")


def recommend(columns: list[str], rows: list[list], question: str = "") -> ChartSpec | None:
    return recommend_by_rules(profile(columns, rows), question)


def switch_type(base: ChartSpec, chart_type: ChartType, columns: list[str], rows: list[list]) -> ChartSpec:
    """右栏切换图表类型：在原 Spec 的字段基础上推导新 Spec，数据不适合时抛 ChartError。"""
    p = profile(columns, rows)
    num = [c.name for c in p.numeric]
    dims = [c.name for c in p.columns if c.kind != "numeric"]
    title = base.title

    if chart_type == "table":
        return ChartSpec(chart_type="table", title=title)
    if chart_type == "kpi":
        if p.row_count != 1 or not num:
            raise ChartError("指标卡只适用于单行数值结果")
        return ChartSpec(chart_type="kpi", title=title, y_fields=num)
    if not num:
        raise ChartError("结果中没有数值列，无法绘制图表")

    if chart_type == "scatter":
        if len(num) < 2:
            raise ChartError("散点图需要至少两个数值列")
        return ChartSpec(chart_type="scatter", title=title, x_field=num[0], y_fields=[num[1]])

    x = base.x_field if base.x_field in dims else (dims[0] if dims else None)
    if x is None:
        raise ChartError("结果中没有可作为横轴的维度列")
    y = [f for f in base.y_fields if f in num] or num[:1]
    series = base.series_field if base.series_field in dims and base.series_field != x else None

    if chart_type == "pie":
        # 饼图只画一个指标，存在系列列时按横轴汇总
        return ChartSpec(chart_type="pie", title=title, x_field=x, y_fields=y[:1])
    if chart_type == "stacked_bar":
        if series is None:
            others = [d for d in dims if d != x]
            if not others:
                raise ChartError("堆叠柱状图需要两个维度列")
            series = others[0]
        return ChartSpec(chart_type="stacked_bar", title=title, x_field=x, y_fields=y[:1], series_field=series)
    # line / bar
    sort = "desc" if chart_type == "bar" and series is None and len(y) == 1 and x not in [c.name for c in p.temporal] else None
    return ChartSpec(chart_type=chart_type, title=title, x_field=x,
                     y_fields=y[:1] if series else y, series_field=series, sort=sort)
