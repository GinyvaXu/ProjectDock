"""pytest fixtures：隔离的临时状态 + 内存/临时数据库。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from projectdock.api import create_app
from projectdock.config import Settings
from projectdock.db import connect
from projectdock.runner import JobRegistry
from projectdock.state import AppState


@pytest.fixture()
def state(tmp_path):
    data_dir = tmp_path / "data"
    root = tmp_path / "library"
    root.mkdir()
    settings = Settings(data_dir)
    settings.root = str(root)
    settings.update(github_auto=False, backup=True)
    conn = connect(data_dir / "data.db")
    st = AppState(settings, conn, JobRegistry())
    return st


@pytest.fixture()
def client(state):
    return TestClient(create_app(state))
