"""图表回看与类型切换。"""
from app.chart import build_echarts_option, switch_type
from app.common.errors import NotFoundError
from app.common.schemas import ChartOut, ChartSpec, ChartType
from app.repository import ChartRepo


class ChartService:
    def __init__(self, charts: ChartRepo | None = None):
        self.charts = charts or ChartRepo()

    def get(self, message_id: str) -> ChartOut:
        row = self.charts.get_by_message(message_id)
        if row is None:
            raise NotFoundError("该消息没有图表")
        return ChartOut(message_id=message_id, spec=ChartSpec.model_validate(row.chart_spec),
                        option=row.echarts_option, columns=row.columns, rows=row.rows)

    def render(self, message_id: str, chart_type: ChartType) -> ChartOut:
        """按新类型重新组装 option 并保存，下次回看保持用户的选择。数据不适合时抛 ChartError（400）。"""
        current = self.get(message_id)
        spec = switch_type(current.spec, chart_type, current.columns, current.rows)
        option = build_echarts_option(spec, current.columns, current.rows)
        self.charts.update_render(message_id, spec.model_dump(), option)
        return current.model_copy(update={"spec": spec, "option": option})
