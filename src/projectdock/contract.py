"""项目契约：AGENTS.md 生成 + 动态上下文（供外部/内置 AI agent 对接 ProjectDock）。

契约把 ProjectDock 的管理规范（版本 / git / 归档 / 日志 / 流程）固化成 agent 可直接遵守的规则。
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from . import presets
from .ailog import recent_summary
from .versioning import parse_changelog, read_version

CONTRACT_SUBPATH = "AGENTS.md"


def contract_for(ptype: str, spec: dict, title: str, description: str = "") -> str:
    """按类型渲染 AGENTS.md 契约内容。spec 来自 presets 或自定义类型。"""
    dirs = "、".join(spec.get("dirs", [])) or "（无固定目录）"
    files = "、".join(spec.get("files", {}).keys()) or "（无固定文件）"
    git = bool(spec.get("git", True))
    if ptype == "软件":
        return _software(title, description, dirs, files, git)
    if git:
        return _generic(title, description, dirs, files)
    return _lite(title, description, dirs, files)


def _software(title: str, description: str, dirs: str, files: str, git: bool) -> str:
    git_rules = (
        "- 单 main 分支直接开发与发布，不建 develop/feature 分支\n"
        "- 提交前缀：feat: / fix: / release: / build: / chore: / docs: / refactor: / test:\n"
        "- 提交前用 git status + git diff --stat 复核改动范围，不提交无关文件\n"
        "- **不主动 push**；推送 GitHub 由用户明确要求后进行，推送前复核内容\n"
        "- versions/ 与 dist/ 只增不删、仅本地保留、不上传"
    ) if git else "- 该项目不使用 git 管理，请直接操作文件"
    return f"""# AGENTS.md — 项目契约（由 ProjectDock 生成）

{title}：{description or "（暂无描述）"}。本项目由 ProjectDock 管理，以下是必须遵守的规范。

## 项目结构
- 类型：软件（Python 软件项目）
- 目录结构约定：{dirs}
- 骨架文件约定：{files}

## 版本管理（强制）
- 版本号唯一来源：根目录 `VERSION` 文件（纯数字 semver，如 0.1.0）；禁止在源码/spec/安装器里手写第二份版本号
- 每次变更同步更新 `CHANGELOG.md` 更新日志（## [版本] - 日期 + ### Added/Fixed/Changed 分组）
- 构建产物归档到 `versions/vX.Y.Z/dist/`（仅本地、不上传、只增不删、不覆盖旧产物）
- 语义化版本：Bug 修复=PATCH、新功能/UI=MINOR、不兼容大改=MAJOR

## Git 规范
{git_rules}

## 任务流程（强制）
1. 大功能先调研 → 与用户 grill 确认方案 → update_plan 拆解 → 逐步实现 → 交付报告
2. 重要修改先与用户商讨，不一键直达
3. 任务执行前先做安全备份（快照进 versions/backups/）
4. 每轮迭代结束交付报告：改动清单 / 构建产物路径 / 测试建议

## 归档优先（先听懂再动手）
- 用户说「整理版本归档 / 归档构建产物 / 把产物归到版本里」= 把根目录 `dist/`、`installer/`、`build/` 的构建产物移动归档到 `versions/vX.Y.Z/dist/`（文件名带版本号的按各自版本归档，否则用 VERSION 的当前版本）。
- 用户只提「归档 / 整理版本」时：**不要擅自修改 CHANGELOG.md、VERSION 或发版本号**；先归档，再报告并询问是否需要补更新日志。
- 只有用户明确说「发布 / 发版 / release」才走 VERSION -> CHANGELOG -> git tag -> Release 完整流程。
- 归档用 `python -m projectdock.cli archive <项目名> [--version X.Y.Z] [--confirm]`；归档是移动不是删除，绝不覆盖旧产物。

## 确认策略（强制）
- 以下操作必须先获得**用户明确同意**才能执行：推送 GitHub（push）/ 删除文件（delete）/ 创建 GitHub 仓库（github_create）/ 发布 Release（release）/ 归档移动构建产物（archive）
- 执行上述操作时：`projectdock-cli` 对应命令要求加 `--confirm` 参数；外部 agent 不得擅自 push / 删除 / 建仓
- 用户可在 ProjectDock 设置中逐项关闭确认（关闭后该操作可自动执行），但删除文件类操作始终建议先备份

## AI 操作日志（强制）
- 每个任务完成后必须主动写 AI 操作日志到 `logs/ai/`（JSON），位置与格式见下；**不写日志视为未完成任务**
- 要素：ts / agent / action / result / summary / details / git / backup
- 快捷方式：`python -m projectdock.cli log <项目名> --agent <你的名字> --action "..." --result done --summary "..."`

## 与 ProjectDock 对接（projectdock-cli）
- 查看契约与当前状态：`python -m projectdock.cli context <项目名>`；查看 AI 日志：`python -m projectdock.cli logs <项目名>`
- 新建项目：`python -m projectdock.cli init <名称> --type <类型> [--no-git]`
- 构建并归档：`python -m projectdock.cli build <项目名> [--script 脚本] [--archive]`
- 发布版本：`python -m projectdock.cli release <项目名> --version X.Y.Z [--changelog "..."] [--build 脚本] [--push] [--confirm]`
- 归档根目录产物：`python -m projectdock.cli archive <项目名> [--version X.Y.Z] [--confirm]`
- 若上述命令不可用：按本契约手动维护文件，并把日志 JSON 写到 logs/ai/ 即可

## 禁止事项
- 不删除 versions/、dist/ 内容；不覆盖旧构建产物（同版本重建先带时间戳归档旧 exe）
- 不把私有配置（config.json / *.env / API Key）提交入库
- 不离开当前项目目录做无关操作
"""


def _generic(title: str, description: str, dirs: str, files: str) -> str:
    return f"""# AGENTS.md — 项目契约（由 ProjectDock 生成）

{title}：{description or "（暂无描述）"}。本项目由 ProjectDock 管理，以下是必须遵守的规范。

## 项目结构
- 目录结构约定：{dirs}
- 骨架文件约定：{files}

## 版本管理
- 若存在 VERSION 文件：它是版本号唯一来源；更新版本时同步维护 CHANGELOG.md
- 构建/发布产物按需归档到 `versions/vX.Y.Z/`（仅本地、不上传）

## Git 规范
- 单 main 分支直接开发；提交前缀：feat: / fix: / docs: / chore:
- **不主动 push**；推送由用户明确要求后进行
- versions/、dist/、logs/ 仅本地保留、不上传

## 确认策略（强制）
- 推送 GitHub / 删除文件 / 创建 GitHub 仓库 / 发布 Release / 归档移动产物前必须先获得用户明确同意（CLI 加 `--confirm`）

## AI 操作日志（强制）
- 每个任务完成后必须主动写 AI 操作日志到 `logs/ai/`（JSON：ts / agent / action / result / summary / details / git / backup）
- 快捷方式：`python -m projectdock.cli log <项目名> --agent <你的名字> --action "..." --result done --summary "..."`

## 任务流程
- 重要修改先与用户商讨（grill）；执行前先备份；每轮结束交付报告
"""


def _lite(title: str, description: str, dirs: str, files: str) -> str:
    return f"""# AGENTS.md — 项目契约（由 ProjectDock 生成）

{title}：{description or "（暂无描述）"}。本项目由 ProjectDock 管理（文档/演示类，不强制 git 与版本归档）。

## 项目结构
- 目录结构约定：{dirs}
- 骨架文件约定：{files}

## 管理要求
- 文档按文件类型归类，版本以文件名/目录时间顺序区分；不删除历史版本
- 重要修改先与用户商讨

## AI 操作日志（强制）
- 每个任务完成后必须主动写 AI 操作日志到 `logs/ai/`（JSON：ts / agent / action / result / summary / details）
- 快捷方式：`python -m projectdock.cli log <项目名> --agent <你的名字> --action "..." --result done --summary "..."`
"""


def write_contract(project_path: Path, ptype: str, title: str, description: str = "",
                   force: bool = False) -> Path:
    """生成/重写 AGENTS.md 契约，返回路径。force=False 且已存在时不覆盖。"""
    spec = presets.PRESETS.get(ptype, presets.PRESETS["其他"])
    target = project_path / CONTRACT_SUBPATH
    if target.is_file() and not force:
        return target
    target.write_text(contract_for(ptype, spec, title, description), encoding="utf-8")
    return target


def dynamic_context(project_path: Path) -> str:
    """项目当前状态摘要（供 agent 动态上下文 / cli context 使用）。"""
    p = Path(project_path)
    version = read_version(p)
    lines = [f"## 项目当前状态（{p.name}）"]
    lines.append(f"- 版本：{('v' + version) if version else '（无 VERSION 文件）'}")
    git_ok = (p / ".git").is_dir()
    head = ""
    dirty = 0
    if git_ok:
        try:
            head = subprocess.run(["git", "log", "--oneline", "-1"], cwd=str(p), capture_output=True,
                                  text=True, encoding="utf-8", errors="replace", timeout=10,
                                  creationflags=0x08000000 if os.name == "nt" else 0).stdout.strip()
            status = subprocess.run(["git", "-c", "core.quotepath=false", "status", "--porcelain"], cwd=str(p),
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
                                    creationflags=0x08000000 if os.name == "nt" else 0).stdout
            dirty = len([ln for ln in status.splitlines() if ln.strip()])
        except (OSError, subprocess.TimeoutExpired):
            pass
        lines.append(f"- Git：{'已初始化' if git_ok else '未初始化'}；最新提交：{head or '无'}")
        lines.append(f"- 工作区：{'干净' if not dirty else f'{dirty} 项变更'}")
    changelog = parse_changelog(p, limit=1)
    if changelog:
        top = changelog[0]
        lines.append(f"- 最新更新：v{top.get('version', '')} {top.get('date', '')}")
    recent = recent_summary(p, limit=3)
    if recent:
        lines.append("- 最近 AI 操作：")
        lines.extend("  " + r for r in recent)
    return "\n".join(lines)