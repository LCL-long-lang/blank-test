"""仓储层公共部分：连接管理与 ID / 时间生成。仓储只做 SQL 读写，不含业务逻辑。"""
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from app.db.app_db import connect


def new_id() -> str:
    return uuid.uuid4().hex


def now() -> str:
    # 精确到微秒，保证同一秒内插入的消息顺序稳定
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")


class BaseRepo:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        """一次操作一个连接：成功提交，异常回滚。"""
        conn = connect(self.db_path)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
