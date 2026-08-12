from __future__ import annotations

AGENTS = {
    "claude": {
        "label": "Claude Code",
        "command": ["claude", "-p", "{prompt}"],
        "hint": "claude -p \"...\"（非交互打印模式，在当前项目目录执行）",
    },
    "pi": {
        "label": "Pi",
        "command": ["pi", "{prompt}"],
        "hint": "pi \"...\"（把消息作为参数传入，在当前项目目录执行）",
    },
}


def build_command(agent: str, prompt: str) -> list[str]:
    """把用户提示词填入 agent 命令模板。"""
    spec = AGENTS.get(agent) or AGENTS["claude"]
    return [part.format(prompt=prompt) if "{prompt}" in part else part for part in spec["command"]]


def system_prompt(project_name: str, project_path: str) -> str:
    """给 agent 的项目上下文前缀。"""
    return (
        f"你是 ProjectDock 项目坞内置的项目管理助手。"
        f"当前正在管理的项目：{project_name}（目录：{project_path}）。"
        "请在该项目目录内，按用户要求执行文件操作、代码修改、版本管理等任务；"
        "不要离开当前项目目录做无关操作。"
    )
