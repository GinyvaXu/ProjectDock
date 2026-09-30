from __future__ import annotations

import datetime
import sys
from pathlib import Path

from . import backup, builder
from .github import gh_available
from .runner import run_simple, stream_command


async def run_release(state, project_path: Path, cfg: dict, emit) -> None:
    """发布向导：备份 -> 更新版本/日志 -> 测试门禁 -> 构建 -> git 提交打 tag -> 推送与 GitHub Release。"""
    project_path = Path(project_path)
    version = str(cfg["version"]).lstrip("v")
    changelog = cfg.get("changelog") or ""
    build_script = cfg.get("build_script")
    push = bool(cfg.get("push"))

    emit("[1/7] 备份项目（versions/backups/）")
    backup_path = None
    if state.settings.backup:
        try:
            backup_path = backup.make_backup(project_path)
            emit(f"      已生成快照：{backup_path.name}")
        except Exception as exc:
            emit(f"      备份跳过（{exc}）")

    emit(f"[2/7] 更新 VERSION -> {version}")
    (project_path / "VERSION").write_text(version + "\n", encoding="utf-8")

    emit("[3/7] 更新 CHANGELOG.md")
    _update_changelog(project_path, version, changelog)

    emit("[4/7] 测试门禁")
    pytest_ok, _ = await run_simple([sys.executable, "-c", "import pytest"], str(project_path))
    has_tests = any(project_path.rglob("test_*.py"))
    if pytest_ok != 0 or not has_tests:
        emit("      未发现 pytest 或测试文件，跳过（可后续手动补跑）")
    else:
        code = await stream_command(lambda t: emit("      " + t), [sys.executable, "-m", "pytest", "-q"], str(project_path))
        if code not in (0, 5):
            raise RuntimeError("测试未通过，发布中止（exit=%s）" % code)
        emit("      测试通过")

    if build_script:
        emit(f"[5/7] 构建：{build_script}")
        scripts = {s["name"]: s for s in builder.find_build_scripts(project_path)}
        script = scripts.get(build_script)
        if not script:
            raise RuntimeError(f"构建脚本不存在：{build_script}")
        code = await stream_command(lambda t: emit("      " + t), builder.command_for(script), str(project_path))
        if code != 0:
            raise RuntimeError("构建失败（exit=%s）" % code)
    else:
        emit("[5/7] 未选择构建脚本，跳过构建")

    if (project_path / ".git").is_dir():
        emit("[6/7] git 提交与打 tag")
        _, out = await run_simple(["git", "-c", "core.quotepath=false", "status", "--porcelain"], str(project_path))
        if out.strip():
            await run_simple(["git", "add", "-A"], str(project_path))
            code = await stream_command(lambda t: emit("      " + t), ["git", "commit", "-m", f"release: v{version}"], str(project_path))
            if code != 0:
                raise RuntimeError("git commit 失败（exit=%s）" % code)
        else:
            emit("      工作区干净，无需提交")
        code = await stream_command(lambda t: emit("      " + t), ["git", "tag", f"v{version}"], str(project_path))
        if code != 0:
            raise RuntimeError("git tag 失败（exit=%s）" % code)
    else:
        emit("[6/7] 项目未初始化 git，跳过提交/打 tag")

    release_url = None
    if push:
        emit("[7/7] 推送与 GitHub Release")
        code = await stream_command(lambda t: emit("      " + t), ["git", "push", "origin", "HEAD", "--tags"], str(project_path))
        if code != 0:
            raise RuntimeError("git push 失败（exit=%s）" % code)
        if gh_available():
            dist = project_path / "versions" / f"v{version}" / "dist"
            cmd = ["gh", "release", "create", f"v{version}", "--title", f"v{version}", "--notes", changelog or f"发布 v{version}"]
            if dist.is_dir():
                for artifact in sorted(dist.iterdir()):
                    if artifact.is_file():
                        cmd.append(str(artifact))
            out_lines: list[str] = []

            def _on_line(text: str) -> None:
                emit("      " + text)
                out_lines.append(text)

            code = await stream_command(_on_line, cmd, str(project_path))
            if code == 0:
                for line in out_lines:
                    if "http" in line:
                        release_url = line.strip()
            else:
                emit("      gh release create 失败（不影响本地发布）")
    else:
        emit("[7/7] 未勾选推送，跳过 push / GitHub Release")

    emit("")
    emit("———— 发布报告 ————")
    emit(f"版本：v{version}")
    emit("更新日志：CHANGELOG.md（已插入条目）")
    if build_script:
        emit(f"构建产物：versions/v{version}/dist/（若构建成功）")
    if backup_path:
        emit(f"备份快照：{backup_path}")
    if release_url:
        emit(f"GitHub Release：{release_url}")


def _update_changelog(project_path: Path, version: str, text: str) -> None:
    cf = project_path / "CHANGELOG.md"
    date = datetime.date.today().isoformat()
    items = text.strip() or "- 版本发布"
    block = f"## [{version}] - {date}\n### Added\n{items}\n"
    if cf.exists():
        content = cf.read_text(encoding="utf-8")
        idx = content.find("\n## ")
        if idx == -1:
            new = content.rstrip() + "\n\n" + block
        else:
            new = content[: idx + 1] + "\n" + block + content[idx + 1 :]
    else:
        new = f"# 更新日志\n\n{block}"
    cf.write_text(new, encoding="utf-8")
