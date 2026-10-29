"""全局配置：从环境变量 / .env 读取。"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 阿里云百炼（OpenAI 兼容接口）
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model_sql: str = "qwen3.8-max"     # SQL 生成用强模型
    model_fast: str = "qwen3.8-flash"  # 改写 / 意图 / 图表推荐 / 标题

    # 数据库
    business_db_path: Path = BACKEND_DIR / "data" / "business.db"
    app_db_path: Path = BACKEND_DIR / "data" / "app.db"

    # 查询限制
    sql_max_rows: int = 1000
    sql_timeout_s: float = 10.0

    # 记忆窗口（轮数）
    memory_window: int = 6

    # 前端开发地址
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
