from __future__ import annotations

import asyncio
import os
import queue
import threading
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


@dataclass
class Job:
    id: str
    label: str
    status: str = "running"  # running | done | error
    queue: "queue.Queue" = field(default_factory=queue.Queue)
    error: Optional[str] = None
    exit_code: Optional[int] = None


async def stream_command(on_line: Callable[[str], None], cmd: list[str], cwd: str | None) -> int:
    """流式执行命令，逐行回调，返回退出码。"""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        stdin=asyncio.subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
    )
    assert proc.stdout is not None
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="replace").rstrip("\r\n")
        if text:
            on_line(text)
    return await proc.wait()


async def run_simple(cmd: list[str], cwd: str | None) -> tuple[int, str]:
    """静默执行命令，返回 (退出码, 输出)。"""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        stdin=asyncio.subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
    )
    out, _ = await proc.communicate()
    return proc.returncode, out.decode("utf-8", errors="replace")


class JobRegistry:
    """子进程/协程流式任务注册表。

    任务在独立后台线程的专属事件循环中执行（避免被请求/测试循环取消），
    输出写入线程安全的 queue.Queue，SSE 端通过 asyncio.to_thread 读取。
    """

    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="projectdock-jobs", daemon=True)
        self._thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def start(self, cmd: list[str], cwd: str | None, label: str) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], label=label)
        self._jobs[job.id] = job
        asyncio.run_coroutine_threadsafe(self._run_command(job, cmd, cwd), self._loop)
        return job

    def start_task(self, label: str, coro_factory: Callable[[Callable[[str], None]], Awaitable[None]]) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], label=label)
        self._jobs[job.id] = job
        asyncio.run_coroutine_threadsafe(self._run_task(job, coro_factory), self._loop)
        return job

    async def _run_command(self, job: Job, cmd: list[str], cwd: str | None) -> None:
        try:
            code = await stream_command(lambda text: job.queue.put({"type": "line", "text": text}), cmd, cwd)
            job.exit_code = code
            job.status = "done" if code == 0 else "error"
            if code != 0:
                job.error = f"进程退出码 {code}"
        except Exception as exc:  # noqa: BLE001
            job.status = "error"
            job.error = str(exc)
        finally:
            job.queue.put({
                "type": "end",
                "status": job.status,
                "error": job.error,
                "exit_code": job.exit_code,
            })

    async def _run_task(self, job: Job, coro_factory) -> None:
        try:
            def emit(text: str) -> None:
                job.queue.put({"type": "line", "text": text})

            await coro_factory(emit)
            job.status = "done"
        except Exception as exc:  # noqa: BLE001
            job.status = "error"
            job.error = str(exc)
        finally:
            job.queue.put({
                "type": "end",
                "status": job.status,
                "error": job.error,
                "exit_code": 0 if job.status == "done" else 1,
            })

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def status(self, job_id: str) -> dict | None:
        job = self._jobs.get(job_id)
        if not job:
            return None
        return {
            "id": job.id,
            "label": job.label,
            "status": job.status,
            "error": job.error,
            "exit_code": job.exit_code,
        }
