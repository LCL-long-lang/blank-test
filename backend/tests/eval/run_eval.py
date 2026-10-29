"""执行准确率（EX）评测：用真实模型为示例集生成 SQL，比较执行结果与标准 SQL 的执行结果（会消耗 Token）。

用法：
    python tests/eval/run_eval.py              # 全部示例
    python tests/eval/run_eval.py --limit 5    # 只跑前 5 条
    python tests/eval/run_eval.py --no-few-shot  # 去掉 Few-shot，避免“背答案”

判定（列子集匹配）：行数相同，且标准结果的每一列都能在生成结果中找到取值完全相同的一列。
不要求列名、列顺序一致，允许多出列（如额外返回 product_id），数值保留 2 位小数比较。
"""
import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")

from app.agent import AgentInput, Pipeline, default_llms  # noqa: E402
from app.db.business import run_readonly_query  # noqa: E402
from app.db.schema import get_catalog  # noqa: E402

TARGET_EX = 0.8


def _norm_value(v):
    if isinstance(v, float):
        return round(v, 2)
    return v


def _columns(rows: list[list]) -> list[tuple]:
    """按列取值并排序（忽略行顺序），每列得到一个可比较的元组。"""
    if not rows:
        return []
    return [tuple(sorted((_norm_value(r[i]) for r in rows), key=repr)) for i in range(len(rows[0]))]


def result_match(pred: list[list], gold: list[list]) -> bool:
    if len(pred) != len(gold):
        return False
    remaining = _columns(pred)
    for col in _columns(gold):
        if col not in remaining:
            return False
        remaining.remove(col)
    return True


async def generate_sql(pipe: Pipeline, question: str) -> tuple[str | None, str | None]:
    async for ev in pipe.run(AgentInput(question=question)):
        if ev.event == "final":
            out = ev.data
            return out.sql, out.error_message
    return None, "no outcome"


async def main(limit: int | None, few_shot: bool) -> int:
    catalog = get_catalog()
    examples = catalog.examples[:limit] if limit else catalog.examples
    if not few_shot:
        catalog.examples = []
    llms = default_llms()
    pipe = Pipeline(llms=llms, catalog=catalog)

    passed, rows = 0, []
    started = time.perf_counter()
    for e in examples:
        gold = run_readonly_query(e["sql"])
        sql, err = await generate_sql(pipe, e["question"])
        ok = False
        if sql:
            try:
                pred = run_readonly_query(sql)
                ok = result_match(pred.rows, gold.rows)
            except Exception as exc:  # noqa: BLE001
                err = str(exc)
        passed += ok
        rows.append((e["id"], ok, err))
        print(f"{'✓' if ok else '✗'} {e['id']:<28} {e['question']}" + (f"\n    {err}" if err and not ok else ""))
        if not ok and sql:
            print(f"    生成：{' '.join(sql.split())}")

    ex = passed / len(examples) if examples else 0
    print(f"\nEX = {passed}/{len(examples)} = {ex:.1%}（目标 ≥ {TARGET_EX:.0%}），"
          f"耗时 {time.perf_counter() - started:.0f}s，Few-shot={'开' if few_shot else '关'}")
    return 0 if ex >= TARGET_EX else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--no-few-shot", action="store_true")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.limit, not args.no_few_shot)))
