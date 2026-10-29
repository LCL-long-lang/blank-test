"""图表模块对外接口：结果画像 → 规则推荐 → 组装 ECharts option，全部是纯函数。"""
from app.chart.echarts import build_echarts_option
from app.chart.profile import ResultProfile, profile
from app.chart.recommend import make_title, recommend, recommend_by_rules, switch_type

__all__ = [
    "ResultProfile", "build_echarts_option", "make_title",
    "profile", "recommend", "recommend_by_rules", "switch_type",
]
