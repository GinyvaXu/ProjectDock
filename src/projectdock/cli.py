"""projectdock-cli：供 AI agent 对接 ProjectDock 的命令行接口。

用法（在 ProjectDock 项目目录内运行，或任意位置加 --root）：
  python -m projectdock.cli contract <项目> [--force]       生成/重写 AGENTS.md 契约
  python -m projectdock.cli context <项目>                   输出契约 + 项目当前状态
  python -m projectdock.cli status <项目>                    项目状态（版本/git/AI日志数）
  python -m projectdock.cli log <项目> --agent x --action "..." --result done --summary "..."
  python -m projectdock.cli logs <项目> [--limit N]          列出 AI 操作日志
  python -m projectdock.cli init <名称> --type <类型> [--description "..."] [--no-git] [--style auto|classic|local]
  python -m projectdock.cli build <项目> [--script 脚本] [--archive] [--agent x]
  python -m projectdock.cli release <项目> --version X.Y.Z [--changelog "..."] [--build 脚本] [--push] [--confirm] [--agent x]
  python -m projectdock.cli archive <项目> [--version X.Y.Z] [--confirm] [--agent x]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from . import ailog, builder, compliance, contract, naming, presets, release, scanner, techstack
from .config import Settings, default_root
from .runner import stream_command
from .versioning import VERSION_RE, read_version

CLI_HINT = "用 python -m projectdock.cli <子命令> --help 查看用法"

POLICY_ACTIONS = {
    "push": "推送 GitHub",
    "delete": "删除文件",
    "github_create": "创建 GitHub 仓库",
    "release": "发布 Release",
    "archive": "归档移动构建产物",
}


def _app_settings() -> Settings:
    """读取与桌面端一致的全局设置（%APPDATA%/ProjectDock/settings.json）。"""
    return Settings()


def _db():
    from .db import connect
    return connect(_app_settings().data_dir / "data.db")


def _confirm(args, *policy_keys) -> None:
    """确认策略校验：策略要求确认的操作必须显式带 --confirm。"""
    keys = [k for k in policy_keys if k]
    settings = _app_settings()
    need = [k for k in keys if settings.confirm_required(k)]
    if need and not getattr(args, "confirm", False):
        names = "、".join(POLICY_ACTIONS.get(k, k) for k in need)
        sys.exit(f"按确认策略，该操作需要用户确认：{names}。请先获得用户明确同意后加 --confirm 重试。")


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
    """项目类型：优先文件夹名（经典三段式）；无类型风格（如 ProjectN-名称）查注册表。"""
    from .scanner import parse_project_entry
    entry = parse_project_entry(project.name)
    if entry and entry.ptype:
        return entry.ptype
    try:
        from .db import list_projects
        for row in list_projects(_db()):
            if row["id"] == project.name or Path(row["path"]) == project:
                return row["type"] or "其他"
    except Exception:
        pass
    return "其他"


def cmd_contract(args) -> None:
    project = _resolve_project(args.root, args.name)
    ptype = _project_type(project)
    path = contract.write_contract(project, ptype, project.name, force=args.force)
    print(f"契约已{'重写' if args.force else '就绪'}：{path}")


def cmd_context(args) -> None:
    project = _resolve_project(args.root, args.name)
    ptype = _project_type(project)
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


def cmd_init(args) -> None:
    """新建项目：按类型预设初始化骨架 + git + 契约，并注册到 ProjectDock。"""
    root = args.root
    root.mkdir(parents=True, exist_ok=True)
    ptype = args.type or "其他"
    title = args.name.strip()
    if not title:
        sys.exit("项目名称不能为空")
    from .db import get_custom_type, upsert_project
    conn = _db()
    custom = get_custom_type(conn, ptype)
    if ptype not in presets.PRESETS and not custom:
        types = "、".join(list(presets.PRESETS) + ["（自定义类型由 ProjectDock 管理）"])
        sys.exit(f"未知类型：{ptype}（可用：{types}）")
    folder_name = scanner.make_folder_name(root, ptype, title, style_id=args.style or _app_settings().naming_style)
    project_path = root / folder_name
    if project_path.exists():
        sys.exit(f"同名项目已存在：{folder_name}")
    git = not args.no_git
    if custom:
        spec = {
            "name": custom["name"], "label": custom["label"], "description": custom["description"],
            "dirs": json.loads(custom["dirs"]), "files": json.loads(custom["files"]),
            "git": bool(custom["git"]), "custom": True,
        }
        result = presets.apply_custom_preset(project_path, spec, title, args.description, git=git)
    else:
        result = presets.apply_preset(project_path, ptype, title, args.description, git=git)
    upsert_project(conn, folder_name, folder_name, ptype, str(project_path), args.description, imported=False)
    print(json.dumps({
        "ok": True, "folder": folder_name, "path": str(project_path), "type": ptype,
        "files": result.get("files", []), "git": result.get("git", False), "message": result.get("message", ""),
    }, ensure_ascii=False, indent=2))


def cmd_build(args) -> None:
    """运行项目构建脚本，可选把产物归档到 versions/vX.Y.Z/dist/。"""
    project = _resolve_project(args.root, args.name)
    scripts = builder.find_build_scripts(project)
    if not scripts:
        sys.exit("没有发现构建脚本（build*.py / 打包.bat）")
    if args.script:
        script = next((s for s in scripts if s["name"] == args.script), None)
        if not script:
            sys.exit(f"构建脚本不存在：{args.script}（可用：{'、'.join(s['name'] for s in scripts)}）")
    else:
        script = scripts[0]
    if args.archive:
        _confirm(args, "archive")

    async def _run():
        return await stream_command(lambda t: print(t), builder.command_for(script), str(project))

    print(f"[build] 运行 {script['name']} …")
    code = asyncio.run(_run())
    if code != 0:
        ailog.write_log(project, agent=args.agent, action=f"构建 {script['name']}", result="failed",
                        summary=f"构建失败（exit={code}）", source="external")
        sys.exit(f"构建失败（exit={code}）")
    print(f"[build] 构建成功：{script['name']}")
    message = ""
    if args.archive:
        result = compliance.archive_root_dist(project)
        message = result["message"]
        print(f"[build] 归档：{message}")
        if not result["ok"]:
            sys.exit(1)
    ailog.write_log(project, agent=args.agent, action=f"构建 {script['name']}",
                    result="done", summary="构建成功" + (f"；{message}" if message else ""), source="external")


def cmd_release(args) -> None:
    """发布版本：备份 -> 版本/日志 -> 测试门禁 -> 构建 -> git tag -> （确认后）推送 + GitHub Release。"""
    project = _resolve_project(args.root, args.name)
    _confirm(args, "release", "push" if args.push else None)
    version = args.version.strip().lstrip("v")
    if not VERSION_RE.match("v" + version):
        sys.exit("版本号格式不正确（应为语义化版本，如 1.2.3）")
    settings = _app_settings()
    state = SimpleNamespace(settings=settings)
    cfg = {"version": version, "changelog": args.changelog or "",
           "build_script": args.build or None, "push": bool(args.push)}
    async def _run():
        await release.run_release(state, project, cfg, lambda t: print(t))
    asyncio.run(_run())
    ailog.write_log(project, agent=args.agent, action=f"发布 v{version}", result="done",
                    summary="projectdock-cli release 发布完成",
                    details=json.dumps(cfg, ensure_ascii=False), source="external")
    print(f"[release] 发布完成：v{version}")


def cmd_archive(args) -> None:
    """把根目录 dist/ 的构建产物归档到 versions/vX.Y.Z/dist/（移动文件，需确认）。"""
    project = _resolve_project(args.root, args.name)
    _confirm(args, "archive")
    version = args.version.strip().lstrip("v") or None
    result = compliance.archive_root_artifacts(project, version=version)
    print(result["message"])
    ailog.write_log(project, agent=args.agent, action="归档根目录构建产物(dist/installer/build)", result="done" if result["ok"] else "failed",
                    summary=result["message"], source="external")
    if not result["ok"]:
        sys.exit(1)


def cmd_techstack(args) -> None:
    """查看或初始化 TECHSTACK.md（技术栈文档）。"""
    project = _resolve_project(args.root, args.name)
    ptype = _project_type(project)
    if ptype != "软件" and not args.force:
        sys.exit("该命令主要面向软件项目；如需强制操作请加 --force")
    title = project.name
    parsed = scanner.parse_project_dir(project.name)
    if parsed:
        title = parsed[2]
    if args.init:
        data = techstack.ensure_template(project, title)
        sys.stdout.write(f"[techstack] 已就绪：{data['path']}\n")
        sys.stdout.write(data["content"])
        return
    data = techstack.read_techstack(project)
    if not data["exists"]:
        sys.stdout.write("[techstack] 项目尚无 TECHSTACK.md，用 --init 创建模板。\n")
        return
    sys.stdout.write(data["content"])


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

    p_init = sub.add_parser("init", help="按类型预设新建项目（含 git + 契约）")
    p_init.add_argument("name")
    p_init.add_argument("--type", default="其他")
    p_init.add_argument("--description", default="")
    p_init.add_argument("--no-git", action="store_true")
    p_init.add_argument("--style", default="", choices=("", naming.STYLE_AUTO, *naming.style_ids()),
                        help="命名规范风格（缺省读取设置，auto=按资料库自动识别）")
    p_init.set_defaults(func=cmd_init)

    p_build = sub.add_parser("build", help="运行项目构建脚本并可选归档产物")
    p_build.add_argument("name")
    p_build.add_argument("--script", default="")
    p_build.add_argument("--archive", action="store_true", help="构建成功后把根目录 dist/ 产物归档到 versions/")
    p_build.add_argument("--agent", default="cli")
    p_build.add_argument("--confirm", action="store_true", help="确认归档移动产物（确认策略要求时必填）")
    p_build.set_defaults(func=cmd_build)

    p_release = sub.add_parser("release", help="发布版本（备份/版本/日志/测试/构建/tag/推送）")
    p_release.add_argument("name")
    p_release.add_argument("--version", required=True, help="新版本号（semver，如 1.2.3）")
    p_release.add_argument("--changelog", default="")
    p_release.add_argument("--build", default="", help="构建脚本名（可选）")
    p_release.add_argument("--push", action="store_true", help="推送 GitHub 并创建 Release")
    p_release.add_argument("--agent", default="cli")
    p_release.add_argument("--confirm", action="store_true", help="确认发布/推送（确认策略要求时必填）")
    p_release.set_defaults(func=cmd_release)

    p_archive = sub.add_parser("archive", help="归档根目录构建产物到版本目录")
    p_archive.add_argument("name")
    p_archive.add_argument("--version", default="", help="目标版本（缺省读 VERSION）")
    p_archive.add_argument("--agent", default="cli")
    p_archive.add_argument("--confirm", action="store_true", help="确认移动产物（确认策略要求时必填）")
    p_archive.set_defaults(func=cmd_archive)

    p_techstack = sub.add_parser("techstack", help="查看/初始化 TECHSTACK.md 技术栈文档")
    p_techstack.add_argument("name")
    p_techstack.add_argument("--init", action="store_true", help="缺失时创建模板")
    p_techstack.add_argument("--force", action="store_true", help="允许非软件项目")
    p_techstack.set_defaults(func=cmd_techstack)

    args = parser.parse_args(argv)
    try:
        args.root = Path(args.root).expanduser().resolve()
        if not args.root.is_dir():
            sys.exit(f"根目录不存在：{args.root}")
        args.func(args)
    except SystemExit:
        raise
    except Exception as exc:
        sys.exit(f"错误：{exc}（{CLI_HINT}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
