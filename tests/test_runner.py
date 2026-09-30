from __future__ import annotations

import sys

from projectdock.runner import JobRegistry


def test_registry_run_echo(tmp_path):
    registry = JobRegistry()
    job = registry.start([sys.executable, "-c", "print('hello runner')"], str(tmp_path), "测试")
    lines = _drain(job)
    assert any(l.get("text") == "hello runner" for l in lines)
    assert job.status == "done"
    assert job.exit_code == 0


def test_registry_status_missing():
    assert JobRegistry().status("nope") is None


def test_registry_error_path(tmp_path):
    registry = JobRegistry()
    job = registry.start([sys.executable, "-c", "import sys; sys.exit(3)"], str(tmp_path), "失败")
    _drain(job)
    assert job.status == "error"
    assert job.exit_code == 3
    assert "退出码" in (job.error or "")


def _drain(job, timeout: float = 15.0) -> list[dict]:
    lines = []
    while True:
        item = job.queue.get(timeout=timeout)
        lines.append(item)
        if item.get("type") == "end":
            return lines
