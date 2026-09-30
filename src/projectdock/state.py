from __future__ import annotations

from .config import Settings
from .db import connect
from .runner import JobRegistry


class AppState:
    """应用全局状态：设置、数据库连接、管理根目录、流式任务注册表。"""

    def __init__(self, settings: Settings, conn, jobs: JobRegistry):
        self.settings = settings
        self.conn = conn
        self.jobs = jobs

    @classmethod
    def default(cls) -> AppState:
        settings = Settings()
        conn = connect(settings.data_dir / "data.db")
        return cls(settings, conn, JobRegistry())
