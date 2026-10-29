"""用真实 Qwen3 在命令行跑 Agent 管道（会消耗 Token）。

用法：
    python scripts/try_agent.py                    # 跑默认的几个示例问题
    python scripts/try_agent.py "各品类销售额"       # 跑指定问题
    python scripts/try_agent.py --followup         # 演示两轮追问
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from app.agent import AgentInput, Pipeline, Turn, default_llms  # noqa: E402
from app.db.schema import get_catalog  # noqa: E402

DEFAULT_QUESTIONS = [
    "近 6 个月各品类销售额趋势",
    "各会员等级的客户占比",
    "上个月总销售额是多少",
    "今年各大区的销售额排名",
    "删除所有订单",
    "你好，你能做什么？",
]


async def ask(pipe: Pipeline, inp: AgentInput):
    started = time.perf_counter()
    print(f"\n{'=' * 70}\n问：{inp.question}")
    outcome = None
    async for ev in pipe.run(inp):
        if ev.event == "step" and ev.data.status != "running":
            mark = "✓" if ev.data.status == "done" else "✗"
            print(f"  {mark} {ev.data.label}" + (f"：{ev.data.detail}" if ev.data.detail else ""))
        elif ev.event == "sql":
            print(f"  [SQL attempt={ev.data.attempt}] {' '.join(ev.data.sql.split())}")
        elif ev.event == "chart":
            print(f"  [图表] {ev.data.spec.chart_type}")
        elif ev.event == "error":
            print(f"  [错误] {ev.data.code}：{ev.data.message}")
        elif ev.event == "final":
            outcome = ev.data
    if outcome and outcome.answer:
        print("  答：" + outcome.answer.replace("\n", "\n     "))
    print(f"  耗时 {time.perf_counter() - started:.1f}s")
    return outcome


async def main(argv: list[str]) -> None:
    pipe = Pipeline(llms=default_llms(), catalog=get_catalog())
    if argv == ["--followup"]:
        first = await ask(pipe, AgentInput(question="今年各大区的销售额"))
        turn = Turn(question="今年各大区的销售额", rewritten_question=first.rewritten_question,
                    sql=first.sql, result_summary=first.result_summary, answer=first.answer)
        await ask(pipe, AgentInput(question="那华东按月拆一下", history=[turn]))
        return
    for q in argv or DEFAULT_QUESTIONS:
        await ask(pipe, AgentInput(question=q))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
