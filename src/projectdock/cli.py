"""projectdock-cli：供 AI agent 对接 ProjectDock 的命令行接口。

用法（在 ProjectDock 项目目录内运行，或任意位置加 --root）：
  python -m projectdock.cli contract <项目> [--force]   生成/重写 AGENTS.md 契约
  python -m projectdock.cli context <项目>               输出契约 + 项目当前状态
  python -m projectdock.cli status <项目>                项目状态（版本/git/AI日志数）
  python -m projectdock.cli log <项目> --agent x --action "..." --result done --summary "..." [--details "..."]
  python -m projectdock.cli logs <项目> [--limit N]      列出 AI 操作日志
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import ailog, contract
from .config import default_root
from .versioning import read_version

CLI_HINT = "用 python -m projectdock.cli <子命令> --help 查看用法"


def _resolve_project(root: Path, name: str) -> Path:
    exact = root / name
    if exact.is_dir():
        return exact
    matches = [p for p in root.iterdir() if p.is_dir() and name in p.name]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        sys.exit(f"匹配到多个项目，请使用完整文件夹名：{', '.join(p.name for p in matches)}")
    sys.exit(f"项目不存在：{name}（根目录：{root}）")


def _project_type(project: Path) -> str:
    from .scanner import parse_project_dir
    parsed = parse_project_dir(project.name)
    return parsed[1] if parsed else "其他"


def cmd_contract(args) -> None:
    project = _resolve_project(args.root, args.name)
    ptype = _project_type(project)
    path = contract.write_contract(project, ptype, project.name, force=args.force)
    print(f"契约已{'重写' if args.force else '就绪'}：{path}")


def cmd_context(args) -> None:
    project = _resolve_project(args.root, args.name)
    ptype = _project_type(project)
    spec = None
    from . import presets
    spec = presets.PRESETS.get(ptype, presets.PRESETS["其他"])
    print(contract.contract_for(ptype, spec, project.name))
    print()
    print(contract.dynamic_context(project))


def cmd_status(args) -> None:
    project = _resolve_project(args.root, args.name)
    ptype = _project_type(project)
    from .compliance import quick_compliance
    logs = ailog.list_logs(project, limit=args.limit)
    info = {
        "name": project.name,
        "type": ptype,
        "version": read_version(project),
        "git": (project / ".git").is_dir(),
        "compliant": quick_compliance(project, ptype),
        "ai_logs": len(logs),
    }
    print(json.dumps(info, ensure_ascii=False, indent=2))


def cmd_log(args) -> None:
    project = _resolve_project(args.root, args.name)
    path = ailog.write_log(project, agent=args.agent, action=args.action, result=args.result,
                           summary=args.summary, details=args.details or "", source="external")
    print(f"日志已写入：{path}")


def cmd_logs(args) -> None:
    project = _resolve_project(args.root, args.name)
    entries = ailog.list_logs(project, limit=args.limit)
    if not entries:
        print("（暂无 AI 操作日志）")
        return
    for e in entries:
        print(f"[{e.get('ts', '')[:19]}] {e.get('agent', '')} | {e.get('result', '')} | {e.get('action', '')}")
        if e.get("summary"):
            print(f"    {e['summary']}")
        if e.get("git"):
            print(f"    git: {e['git']}")


def main(argv: list[str] | None = None) -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass
    parser = argparse.ArgumentParser(prog="projectdock.cli", description="ProjectDock 命令行接口（供 AI agent 对接）")
    parser.add_argument("--root", default=str(default_root()), help="管理根目录（默认自动检测）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_contract = sub.add_parser("contract", help="生成/重写 AGENTS.md 契约")
    p_contract.add_argument("name")
    p_contract.add_argument("--force", action="store_true")
    p_contract.set_defaults(func=cmd_contract)

    p_context = sub.add_parser("context", help="输出契约 + 项目当前状态")
    p_context.add_argument("name")
    p_context.set_defaults(func=cmd_context)

    p_status = sub.add_parser("status", help="项目状态 JSON")
    p_status.add_argument("name")
    p_status.add_argument("--limit", type=int, default=10)
    p_status.set_defaults(func=cmd_status)

    p_log = sub.add_parser("log", help="写一条 AI 操作日志")
    p_log.add_argument("name")
    p_log.add_argument("--agent", required=True)
    p_log.add_argument("--action", required=True)
    p_log.add_argument("--result", default="done", choices=("running", "done", "failed"))
    p_log.add_argument("--summary", default="")
    p_log.add_argument("--details", default="")
    p_log.set_defaults(func=cmd_log)

    p_logs = sub.add_parser("logs", help="列出 AI 操作日志")
    p_logs.add_argument("name")
    p_logs.add_argument("--limit", type=int, default=20)
    p_logs.set_defaults(func=cmd_logs)

    args = parser.parse_args(argv)
    try:
        args.root = Path(args.root).expanduser().resolve()
        if not args.root.is_dir():
            sys.exit(f"根目录不存在：{args.root}")
        args.func(args)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"错误：{exc}（{CLI_HINT}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())