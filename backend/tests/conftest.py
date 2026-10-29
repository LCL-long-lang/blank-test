"""测试夹具：每个测试使用临时目录下的 app.db，不污染 data/；业务库用小规模生成数据。"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from scripts.seed_business_db import build


@pytest.fixture(scope="session")
def business_db(tmp_path_factory):
    """会话级小业务库（2000 单 / 12 个月），只读测试共享。"""
    path = tmp_path_factory.mktemp("biz") / "business.db"
    build(path, n_orders=2000, n_months=12, end=date(2026, 10, 3))
    return path


@pytest.fixture
def tmp_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "app_db_path", tmp_path / "app.db")
    monkeypatch.setattr(settings, "business_db_path", tmp_path / "business.db")
    return settings


@pytest.fixture
def client(tmp_settings):
    from app.main import app

    with TestClient(app) as c:  # with 语句会触发 lifespan（建表）
        yield c
