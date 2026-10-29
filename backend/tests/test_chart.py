"""Phase 2.3 图表：结果画像、规则推荐、option 组装、类型切换（纯函数）。"""
import pytest

from app.chart import build_echarts_option, profile, recommend, switch_type
from app.common.errors import ChartError
from app.common.schemas import ChartSpec

MONTHS = ["2026-05", "2026-06", "2026-07"]


def test_profile_kinds():
    p = profile(["month", "category_name", "sales", "customer_id"],
                [["2026-05", "手机数码", 100.5, 1], ["2026-06", "家用电器", 80, 2]])
    assert [c.kind for c in p.columns] == ["temporal", "categorical", "numeric", "categorical"]


def test_profile_short_month_by_name():
    assert profile(["month"], [["01"], ["02"]]).columns[0].kind == "temporal"
    assert profile(["code"], [["01"], ["02"]]).columns[0].kind == "categorical"


def test_kpi():
    spec = recommend(["sales"], [[123456.7]], "上个月的总销售额是多少？")
    assert spec.chart_type == "kpi" and spec.title == "上个月的总销售额是多少"
    opt = build_echarts_option(spec, ["sales"], [[123456.7]])
    assert opt["kind"] == "kpi" and opt["items"] == [{"label": "sales", "value": 123456.7}]


def test_line_single_series():
    rows = [[m, i * 10] for i, m in enumerate(MONTHS)]
    spec = recommend(["month", "sales"], rows, "近 3 个月销售额趋势")
    assert spec.chart_type == "line" and spec.x_field == "month"
    opt = build_echarts_option(spec, ["month", "sales"], rows)
    assert opt["xAxis"]["data"] == MONTHS and opt["series"][0]["data"] == [0, 10, 20]


def test_line_multi_series_fills_missing_with_none():
    cols = ["month", "category_name", "sales"]
    rows = [["2026-05", "A", 1], ["2026-05", "B", 2], ["2026-06", "A", 3]]
    spec = recommend(cols, rows, "各品类趋势")
    assert spec.chart_type == "line" and spec.series_field == "category_name"
    opt = build_echarts_option(spec, cols, rows)
    assert {s["name"]: s["data"] for s in opt["series"]} == {"A": [1, 3], "B": [2, None]}
    assert opt["legend"]["type"] == "scroll"


def test_bar_sorted_desc():
    cols, rows = ["region_name", "sales"], [["华北", 5], ["华东", 9], ["华南", 7]]
    spec = recommend(cols, rows, "各大区销售额")
    assert spec.chart_type == "bar" and spec.sort == "desc"
    opt = build_echarts_option(spec, cols, rows)
    assert opt["xAxis"]["data"] == ["华东", "华南", "华北"]


def test_pie_only_when_question_asks_share():
    cols, rows = ["member_level", "n"], [["普通", 60], ["银卡", 25], ["金卡", 11], ["钻石", 4]]
    assert recommend(cols, rows, "各会员等级的客户占比").chart_type == "pie"
    assert recommend(cols, rows, "各会员等级的客户数").chart_type == "bar"
    opt = build_echarts_option(recommend(cols, rows, "占比"), cols, rows)
    assert opt["series"][0]["type"] == "pie" and len(opt["series"][0]["data"]) == 4
    # 数量 + 比例两个数值列：仍是饼图，取第一个数值列
    spec = recommend(cols + ["ratio"], [r + [0.1] for r in rows], "各会员等级的客户占比")
    assert spec.chart_type == "pie" and spec.y_fields == ["n"]


def test_pie_falls_back_to_bar_when_too_many_slices():
    rows = [[f"省{i}", i] for i in range(10)]
    assert recommend(["province", "n"], rows, "各省份占比").chart_type == "bar"


def test_stacked_bar():
    cols = ["region_name", "category_name", "sales"]
    rows = [[r, c, 1] for r in ["华东", "华南"] for c in ["A", "B", "C"]]
    spec = recommend(cols, rows, "各大区不同品类的销售额")
    assert spec.chart_type == "stacked_bar"
    opt = build_echarts_option(spec, cols, rows)
    assert all(s["stack"] == "total" for s in opt["series"])


def test_scatter():
    spec = recommend(["age", "sales"], [[20, 100], [30, 300]], "")
    assert spec.chart_type == "scatter"
    assert build_echarts_option(spec, ["age", "sales"], [[20, 100]])["series"][0]["data"] == [[20, 100]]


@pytest.mark.parametrize("cols, rows", [
    (["name", "city"], [["张三", "上海"]]),   # 无数值列
    (["sales"], []),                          # 空结果
])
def test_table_fallback(cols, rows):
    spec = recommend(cols, rows, "x")
    assert spec.chart_type == "table"
    assert build_echarts_option(spec, cols, rows)["kind"] == "table"


def test_multi_dimension_detail_is_table():
    cols = ["name", "member_level", "city", "sales", "order_count"]
    assert recommend(cols, [["张三", "金卡", "上海", 100, 3]] * 2, "前 10 位客户").chart_type == "table"


def test_too_many_categories_returns_none():
    rows = [[f"商品{i}", i] for i in range(50)]
    assert recommend(["product_name", "n"], rows, "各商品销量") is None


def test_datazoom_for_long_axis():
    rows = [[f"2026-{i:02d}-01", i] for i in range(1, 13)] + [[f"2025-{i:02d}-01", i] for i in range(1, 13)]
    rows.sort()
    opt = build_echarts_option(recommend(["day", "n"], rows, ""), ["day", "n"], rows)
    assert "dataZoom" in opt


def test_yoy_two_temporal_columns():
    cols = ["month", "year", "sales"]
    rows = [[f"{m:02d}", y, 1] for m in range(1, 13) for y in ["2025", "2026"]]
    spec = recommend(cols, rows, "今年和去年每月对比")
    assert spec.chart_type == "line" and spec.x_field == "month" and spec.series_field == "year"


def test_switch_line_to_bar_and_pie():
    cols, rows = ["month", "category_name", "sales"], [["2026-05", "A", 1], ["2026-05", "B", 2]]
    base = recommend(cols, rows, "趋势")
    bar = switch_type(base, "bar", cols, rows)
    assert bar.chart_type == "bar" and bar.series_field == "category_name"
    build_echarts_option(bar, cols, rows)
    pie = switch_type(base, "pie", cols, rows)
    assert build_echarts_option(pie, cols, rows)["series"][0]["data"] == [{"name": "2026-05", "value": 3}]


def test_switch_to_unsupported_raises():
    cols, rows = ["region_name", "sales"], [["华东", 1], ["华南", 2]]
    base = recommend(cols, rows, "")
    with pytest.raises(ChartError):
        switch_type(base, "kpi", cols, rows)
    with pytest.raises(ChartError):
        switch_type(base, "scatter", cols, rows)


def test_spec_field_not_in_result_raises():
    spec = ChartSpec(chart_type="bar", title="t", x_field="nope", y_fields=["sales"])
    with pytest.raises(ChartError):
        build_echarts_option(spec, ["region_name", "sales"], [["华东", 1]])


def test_examples_expected_chart_types(business_db):
    """示例集在真实数据上跑一遍，规则推荐结果与标注的期望图表一致。"""
    from app.db.business import run_readonly_query
    from app.db.schema import load_examples

    mismatched = []
    for e in load_examples():
        r = run_readonly_query(e["sql"], path=business_db)
        if not r.rows:
            continue  # 小样本库里某些时间窗可能为空
        spec = recommend(r.columns, r.rows, e["question"])
        got = spec.chart_type if spec else None
        if got != e["chart"]:
            mismatched.append((e["id"], e["chart"], got))
        if spec:
            build_echarts_option(spec, r.columns, r.rows)
    assert not mismatched, mismatched
