import json
from dataclasses import dataclass
from typing import Any

from app.repository.base import BaseRepo, new_id, now


@dataclass
class ChartRow:
    id: str
    message_id: str
    chart_spec: dict[str, Any]
    echarts_option: dict[str, Any]
    columns: list[str]
    rows: list[list[Any]]
    created_at: str


def _dumps(v: Any) -> str:
    # default=str：兜底处理 Decimal、bytes 等 JSON 不支持的类型
    return json.dumps(v, ensure_ascii=False, default=str)


def _row(r) -> ChartRow:
    return ChartRow(id=r["id"], message_id=r["message_id"], chart_spec=json.loads(r["chart_spec"]),
                    echarts_option=json.loads(r["echarts_option"]), columns=json.loads(r["columns"]),
                    rows=json.loads(r["rows"]), created_at=r["created_at"])


class ChartRepo(BaseRepo):
    def save(self, message_id: str, chart_spec: dict, echarts_option: dict,
             columns: list[str], rows: list[list[Any]]) -> str:
        """一条消息只有一张图：已存在则覆盖。"""
        cid = new_id()
        with self.conn() as c:
            c.execute(
                """INSERT INTO charts (id, message_id, chart_spec, echarts_option, columns, rows, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(message_id) DO UPDATE SET
                       chart_spec = excluded.chart_spec, echarts_option = excluded.echarts_option,
                       columns = excluded.columns, rows = excluded.rows""",
                (cid, message_id, _dumps(chart_spec), _dumps(echarts_option), _dumps(columns),
                 _dumps(rows), now()),
            )
        return cid

    def get_by_message(self, message_id: str) -> ChartRow | None:
        with self.conn() as c:
            r = c.execute("SELECT * FROM charts WHERE message_id = ?", (message_id,)).fetchone()
        return _row(r) if r else None

    def update_render(self, message_id: str, chart_spec: dict, echarts_option: dict) -> bool:
        """切换图表类型后保存新的 spec 和 option，下次回看保持用户的选择。"""
        with self.conn() as c:
            cur = c.execute("UPDATE charts SET chart_spec = ?, echarts_option = ? WHERE message_id = ?",
                            (_dumps(chart_spec), _dumps(echarts_option), message_id))
        return cur.rowcount > 0
