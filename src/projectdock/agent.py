from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from . import ailog, backup, contract
from .runner import run_simple, stream_command

AGENTS = {
    "claude": {
        "label": "Claude Code",
        "command": ["claude", "-p", "{prompt}", "--dangerously-skip-permissions"],
        "system_args": ["--append-system-prompt", "{file}"],
        "hint": "claude -p \"...\" 全自动模式（跳过权限确认，依赖 git 与备份兜底）",
    },
    "pi": {
        "label": "Pi",
        "command": ["pi", "-p", "{prompt}"],
        "system_args": ["--append-system-prompt", "{file}"],
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


POLICY_LABELS = {
    "push": "推送 GitHub",
    "delete": "删除文件",
    "github_create": "创建 GitHub 仓库",
    "release": "发布 Release",
    "archive": "归档移动构建产物",
}


def render_history(history: list[dict] | None, max_turns: int = 12, max_chars: int = 1500) -> str:
    """把会话历史渲染成给 agent 的「前情提要」文本（防上下文爆炸）。"""
    if not history:
        return ""
    turns = [h for h in history if isinstance(h, dict) and h.get("text")]
    lines = ["## 对话历史（前情提要，最近的交互，按顺序发生）"]
    for h in turns[-max_turns:]:
        role = "用户" if h.get("role") == "user" else "助手"
        text = str(h.get("text") or "")[:max_chars]
        lines.append(f"- [{role}] {text}")
    lines.append("（以上是此前对话；用户可能参考其中的问题与答复，继续完成当前任务。）")
    return "\n".join(lines)


def system_prompt(project_name: str, project_path: str, type_info: dict | None = None,
                  confirm_policy: dict | None = None, history: list[dict] | None = None) -> str:
    """给 agent 的项目上下文前缀；含类型结构约定与确认策略（与管理端约定一致）。"""
    lines = [
        "你是 ProjectDock 项目坞内置的项目管理助手。",
        f"当前正在管理的项目：{project_name}（目录：{project_path}）。",
        "请在该项目目录内，按用户要求执行文件操作、代码修改、版本管理等任务；不要离开当前项目目录做无关操作。",
    ]
    if confirm_policy:
        need = [POLICY_LABELS.get(k, k) for k, v in (confirm_policy or {}).items() if v]
        if need:
            lines.append("确认策略：以下操作必须先向用户确认并获得明确同意才能执行——" + "、".join(need) + "。")
        else:
            lines.append("确认策略：所有高危操作均允许自动执行（用户已在设置中关闭确认）。")
    lines.append("")
    lines.append("## 需要用户决策时（grill 交互）")
    lines.append("当任务需要用户拍板（多方案选择 / 高风险操作确认 / 关键信息缺失）时，"
                 "停止执行并把选择交给用户：在回复末尾输出一个选择卡片（JSON，选项 2-5 个、每个选项一句话），"
                 "然后停下来等待用户选择，不要自行决定继续执行。选择卡片格式：")
    lines.append('```pdchoice')
    lines.append('{"question": "需要用户决定的问题", "options": ["选项一", "选项二", "选项三"]}')
    lines.append('```')
    lines.append("")
    lines.append("## 技术栈文档（TECHSTACK.md）")
    lines.append("用户要求「写/补/更新技术栈」时：先通读源码、README、依赖清单与 CHANGELOG，"
                 "在项目根目录维护 TECHSTACK.md。格式：`## 概览` 表格（语言/运行时、主要框架、数据存储、"
                 "前端、构建与打包、测试等维度）+ `## 核心功能实现`（每个关键功能一个 `### 小节`，"
                 "含 `- **实现逻辑**：` 与 `- **技术手段**：` 两条要点）。要求详细但简明清晰，"
                 "先讲功能做什么、再讲用什么技术为什么；只写真实存在的内容。")
    lines.append("")
    lines.append("## 常见任务解读（先想清楚用户要什么，再动手）")
    lines.append("- 「整理版本归档 / 归档构建产物 / 把产物归到版本里」= 把根目录 dist/、installer/、build/ 里的构建产物移动归档到 versions/vX.Y.Z/dist/（VERSION 文件里的当前版本号对应的目录；没有就先建），并报告移动了哪些文件。")
    lines.append("- 「整理版本」但没提 CHANGELOG：不要主动改 CHANGELOG.md，先做上面的归档，最后报告并询问是否需要补更新日志。")
    lines.append("- 「发布 / 发版 / release」才走完整流程：VERSION -> CHANGELOG -> git 提交打 tag -> （用户确认后）推送/Release。")
    lines.append("- 用户只让整理文件/归档时，绝不擅自修改 CHANGELOG.md、VERSION 或发版本号。")
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
    hist = render_history(history)
    if hist:
        lines.append("")
        lines.append(hist)
    try:
        ctx = contract.dynamic_context(project_path)
        if ctx:
            lines.append("")
            lines.append(ctx)
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(lines)


async def run_agent_task(state, project_path: Path, agent: str, prompt: str, emit, context: str | None = None) -> None:
    """全自动执行 agent 任务：任务前备份 -> 流式执行 -> 输出任务报告（操作/变更/git）。

    结构化事件：emit({"type": "status", "text": ...}) 供前端展示 agent 当前活动
    （正在思考 / 正在调用哪个程序），普通文本仍按输出行处理。
    """
    def status(text: str) -> None:
        emit({"type": "status", "text": text})

    label = AGENTS.get(agent, {}).get("label", agent)
    backup_path = None
    status(f"正在准备 · {label}（任务前检查备份）…")
    if state.settings.backup:
        try:
            backup_path = backup.make_backup(project_path)
            emit(f"[备份] 已创建任务前快照：versions/backups/{backup_path.name}")
        except Exception as exc:  # noqa: BLE001
            emit(f"[备份] 跳过（{exc}）")

    base_cmd = build_command(agent, prompt)
    tmp_ctx = None
    if context:
        try:
            tmp_ctx = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
            tmp_ctx.write(context)
            tmp_ctx.close()
            extra = [x.format(file=tmp_ctx.name) if "{file}" in x else x for x in (AGENTS.get(agent) or AGENTS["pi"]).get("system_args", [])]
            base_cmd = [base_cmd[0], *extra, *base_cmd[1:]]
        except OSError:
            tmp_ctx = None
    cmd = resolve_command(base_cmd)
    status(f"正在调用 {label}：{' '.join(cmd[:4])}{' …' if len(cmd) > 4 else ''}")
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
    finally:
        if tmp_ctx:
            try:
                os.unlink(tmp_ctx.name)
            except OSError:
                pass

    status("任务已结束，正在汇总报告…")
    emit("")
    emit("———— 任务报告 ————")
    emit(f"状态：{'完成' if code == 0 else '失败'}（退出码 {code}）")
    if backup_path:
        emit(f"备份快照：{backup_path}")
    git_info: dict = {}
    try:
        if (project_path / ".git").is_dir():
            _, head = await run_simple(["git", "log", "--oneline", "-1"], str(project_path))
            _, status = await run_simple(["git", "-c", "core.quotepath=false", "status", "--porcelain"], str(project_path))
            git_info = {"head": head.strip() or "", "changed": len([ln for ln in status.splitlines() if ln.strip()])}
        ailog.write_log(
            project_path, agent=agent, action=prompt.splitlines()[0][:60] if prompt else "AI 任务",
            result="done" if code == 0 else "failed", source="inapp",
            summary=f"{AGENTS.get(agent, {}).get('label', agent)} 任务{'完成' if code == 0 else '失败'}（退出码 {code}）",
            details=prompt[:500], git=git_info,
            backup=f"versions/backups/{backup_path.name}" if backup_path else "",
        )
    except Exception:  # noqa: BLE001
        pass
    if (project_path / ".git").is_dir():
        _, head = await run_simple(["git", "log", "--oneline", "-1"], str(project_path))
        _, status = await run_simple(["git", "-c", "core.quotepath=false", "status", "--porcelain"], str(project_path))
        files = [ln for ln in status.splitlines() if ln.strip()]
        emit(f"Git：{'工作区干净' if not files else f'{len(files)} 项变更'}；最新提交：{head.strip() or '无'}")
        for ln in files[:10]:
            emit("  " + ln.strip()[:110])
        if len(files) > 10:
            emit(f"  … 共 {len(files)} 项变更")
