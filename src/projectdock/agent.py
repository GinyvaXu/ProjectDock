from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import backup
from .runner import run_simple, stream_command

AGENTS = {
    "claude": {
        "label": "Claude Code",
        "command": ["claude", "-p", "{prompt}", "--dangerously-skip-permissions"],
        "hint": "claude -p \"...\" 全自动模式（跳过权限确认，依赖 git 与备份兜底）",
    },
    "pi": {
        "label": "Pi",
        "command": ["pi", "-p", "{prompt}"],
        "hint": "pi -p \"...\" 非交互模式（在当前项目目录执行）",
    },
}


def build_command(agent: str, prompt: str) -> list[str]:
    """把用户提示词填入 agent 命令模板。"""
    spec = AGENTS.get(agent) or AGENTS["pi"]
    return [part.format(prompt=prompt) if "{prompt}" in part else part for part in spec["command"]]


def resolve_command(cmd: list[str]) -> list[str]:
    """Windows 下解析 npm 包装命令（如 pi.cmd），保证可被 create_subprocess_exec 直接执行。"""
    if os.name != "nt" or not cmd:
        return cmd
    exe = shutil.which(cmd[0])
    if not exe:
        return cmd
    lower = exe.lower()
    if lower.endswith((".cmd", ".bat")):
        return ["cmd", "/c", *cmd]
    if lower.endswith(".ps1"):
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", exe, *cmd[1:]]
    return [exe, *cmd[1:]]


def system_prompt(project_name: str, project_path: str, type_info: dict | None = None) -> str:
    """给 agent 的项目上下文前缀；含类型结构约定（与管理端约定一致）。"""
    lines = [
        "你是 ProjectDock 项目坞内置的项目管理助手。",
        f"当前正在管理的项目：{project_name}（目录：{project_path}）。",
        "请在该项目目录内，按用户要求执行文件操作、代码修改、版本管理等任务；不要离开当前项目目录做无关操作。",
    ]
    if type_info:
        structure = []
        if type_info.get("dirs"):
            structure.append("目录结构约定：" + "、".join(str(d) for d in type_info["dirs"]))
        if type_info.get("files"):
            structure.append("骨架文件约定：" + "、".join(str(k) for k in type_info["files"]))
        if type_info.get("git"):
            structure.append("该项目使用 git 管理，重要改动请及时提交")
        lines.append(f"项目类型：{type_info.get('label') or type_info.get('name')}。")
        if structure:
            lines.append("；".join(structure) + "。请遵循这些结构约定进行管理。")
    return "\n".join(lines)


async def run_agent_task(state, project_path: Path, agent: str, prompt: str, emit) -> None:
    """全自动执行 agent 任务：任务前备份 -> 流式执行 -> 输出任务报告（操作/变更/git）。"""
    backup_path = None
    if state.settings.backup:
        try:
            backup_path = backup.make_backup(project_path)
            emit(f"[备份] 已创建任务前快照：versions/backups/{backup_path.name}")
        except Exception as exc:  # noqa: BLE001
            emit(f"[备份] 跳过（{exc}）")

    cmd = resolve_command(build_command(agent, prompt))
    try:
        code = await stream_command(emit, cmd, str(project_path))
    except Exception as exc:  # noqa: BLE001
        emit("")
        emit("———— 任务报告 ————")
        emit(f"状态：失败（无法启动命令：{exc}）")
        hint = AGENTS.get(agent, {}).get("hint")
        if hint:
            emit(f"提示：{hint}")
        raise

    emit("")
    emit("———— 任务报告 ————")
    emit(f"状态：{'完成' if code == 0 else '失败'}（退出码 {code}）")
    if backup_path:
        emit(f"备份快照：{backup_path}")
    if (project_path / ".git").is_dir():
        _, head = await run_simple(["git", "log", "--oneline", "-1"], str(project_path))
        _, status = await run_simple(["git", "-c", "core.quotepath=false", "status", "--porcelain"], str(project_path))
        files = [ln for ln in status.splitlines() if ln.strip()]
        emit(f"Git：{'工作区干净' if not files else f'{len(files)} 项变更'}；最新提交：{head.strip() or '无'}")
        for ln in files[:10]:
            emit("  " + ln.strip()[:110])
        if len(files) > 10:
            emit(f"  … 共 {len(files)} 项变更")
