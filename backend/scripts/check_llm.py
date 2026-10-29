"""连通性检查：调用一次百炼 Qwen3，确认 API Key、接口地址、模型名可用。

用法：python scripts/check_llm.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import settings  # noqa: E402
from app.llm.client import get_fast_llm, get_sql_llm, is_configured  # noqa: E402


def main() -> int:
    if not is_configured():
        print("未配置 DASHSCOPE_API_KEY：请复制 .env.example 为 .env 并填写百炼 API Key")
        return 1

    print(f"接口地址：{settings.dashscope_base_url}")
    ok = True
    for label, llm in [("SQL 模型", get_sql_llm()), ("快模型", get_fast_llm())]:
        t0 = time.perf_counter()
        try:
            reply = llm.invoke("用一句话介绍你自己，不超过 20 个字。")
            cost = (time.perf_counter() - t0) * 1000
            print(f"[OK]   {label} {llm.model_name}（{cost:.0f} ms）：{reply.content.strip()}")
        except Exception as exc:  # 打印原始错误便于排查 Key / 模型名 / 网络问题
            ok = False
            print(f"[FAIL] {label} {llm.model_name}：{type(exc).__name__}: {exc}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
