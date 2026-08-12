"""项目合规检查与合规化。

对照 ProjectDock 管理标准检查项目结构，并提供修复动作：
- 修复 = 创建缺失的标准文件/目录、初始化 git、把根目录 dist 的构建产物归档到版本目录；
- 本模块不删除任何文件；涉及移动文件（归档）的动作标记为 destructive，必须显式确认。
"""
from __future__ import annotations

import fnmatch
import os
import re
from datetime import datetime
from pathlib import Path

from . import presets
from .versioning import read_version

BUILD_EXT = {".exe", ".msi", ".msix", ".appx", ".appimage", ".deb", ".rpm", ".dmg", ".pkg", ".nupkg", ".whl"}
BUILD_NAME_RE = re.compile(r"(debug|release|portable|setup|installer|uninstall|v?\d+\.\d+)", re.IGNORECASE)
SKIP_NAMES = {".build_version", "error_log.txt", "crash.log"}

# ---- 各类型的必需项与建议项 ----
_REQUIRED = {
    "软件": [
        {"key": "readme", "label": "README.md 项目说明", "kind": "file", "name": "README.md"},
        {"key": "version", "label": "VERSION 文件（版本号唯一来源）", "kind": "file", "name": "VERSION"},
        {"key": "changelog", "label": "CHANGELOG.md 更新日志", "kind": "file", "name": "CHANGELOG.md"},
        {"key": "gitignore", "label": ".gitignore 忽略规则", "kind": "file", "name": ".gitignore"},
        {"key": "git", "label": "Git 仓库", "kind": "git"},
    ],
}
_GIT_TYPES = {"网站", "游戏", "脚本", "其他"}
_SUGGESTED = {
    "软件": [
        {"key": "contract", "label": "AGENTS.md 项目契约", "kind": "file", "name": "AGENTS.md"},
        {"key": "versions", "label": "versions/ 版本归档目录", "kind": "dir", "name": "versions"},
        {"key": "build_script", "label": "构建脚本（build*.py / 打包.bat）", "kind": "pattern", "patterns": ("build*.py", "打包.bat")},
        {"key": "src", "label": "src/ 源码目录", "kind": "dir", "name": "src"},
        {"key": "tests", "label": "tests/ 测试目录", "kind": "dir", "name": "tests"},
    ],
}


def required_items(ptype: str) -> list[dict]:
    if ptype == "软件":
        return list(_REQUIRED["软件"])
    if ptype in _GIT_TYPES:
        return [
            {"key": "readme", "label": "README.md 项目说明", "kind": "file", "name": "README.md"},
            {"key": "gitignore", "label": ".gitignore 忽略规则", "kind": "file", "name": ".gitignore"},
            {"key": "git", "label": "Git 仓库", "kind": "git"},
        ]
    return [{"key": "readme", "label": "README.md 项目说明", "kind": "file", "name": "README.md"}]


def suggested_items(ptype: str) -> list[dict]:
    return list(_SUGGESTED.get(ptype, []))


def check_item(project_path: Path, item: dict) -> tuple[bool, str]:
    kind = item["kind"]
    if kind == "file":
        p = project_path / item["name"]
        if not p.is_file():
            return False, f"缺少 {item['name']}"
        if item["name"] == "VERSION" and not read_version(project_path):
            return False, "VERSION 内容不是合法语义化版本"
        return True, "存在"
    if kind == "dir":
        return (project_path / item["name"]).is_dir(), "存在" if (project_path / item["name"]).is_dir() else f"缺少 {item['name']}/"
    if kind == "git":
        return (project_path / ".git").is_dir(), "已初始化" if (project_path / ".git").is_dir() else "未初始化 Git"
    if kind == "pattern":
        try:
            names = [p.name for p in project_path.iterdir() if p.is_file()]
        except OSError:
            names = []
        matched = [pat for pat in item["patterns"] if any(fnmatch.fnmatch(n, pat) for n in names)]
        return bool(matched), ("发现 " + "、".join(matched)) if matched else "未发现构建脚本"
    return False, "未知检查项"


def detect_build_artifacts(dist_dir: Path) -> list[Path]:
    """识别根目录 dist/ 中看起来像构建产物的条目（避免把用户数据当产物移动）。"""
    if not dist_dir.is_dir():
        return []
    out: list[Path] = []
    try:
        children = sorted(dist_dir.iterdir())
    except OSError:
        return out
    for child in children:
        if child.name in SKIP_NAMES or child.name.startswith("."):
            continue
        try:
            if child.is_file():
                if child.suffix.lower() in BUILD_EXT or BUILD_NAME_RE.search(child.name):
                    out.append(child)
            elif child.is_dir() and BUILD_NAME_RE.search(child.name):
                out.append(child)
        except OSError:
            continue
    return out


def standard_info(ptype: str) -> dict:
    """返回某类型的标准结构说明（用于 UI 展示与文档）。"""
    spec = presets.PRESETS.get(ptype)
    return {
        "type": ptype,
        "description": spec["description"] if spec else "",
        "dirs": list(spec.get("dirs", [])) if spec else [],
        "files": list(spec.get("files", {})) if spec else [],
        "git": bool(spec.get("git", True)) if spec else False,
        "required": [i["label"] for i in required_items(ptype)],
        "suggested": [i["label"] for i in suggested_items(ptype)],
    }


def check_compliance(project_path: Path, ptype: str) -> dict:
    required = required_items(ptype)
    checks: list[dict] = []
    actions: list[dict] = []
    for item in required:
        ok, detail = check_item(project_path, item)
        checks.append({**item, "ok": ok, "detail": detail, "required": True})
        if not ok:
            action = _fix_action_for(item)
            if action:
                actions.append(action)
    for item in suggested_items(ptype):
        ok, detail = check_item(project_path, item)
        checks.append({**item, "ok": ok, "detail": detail, "required": False})
        if not ok and item["key"] in ("src", "tests", "versions"):
            actions.append({
                "key": f"mkdir_{item['key']}",
                "label": f"创建 {item['name']}/ 目录",
                "detail": f"在项目根目录创建 {item['name']}/",
                "destructive": False,
            })
        if not ok and item["key"] == "contract":
            actions.append({
                "key": "create_contract",
                "label": "生成 AGENTS.md 项目契约",
                "detail": "按该类型规范生成 AGENTS.md（AI agent 对接契约，含版本/git/日志要求）",
                "destructive": False,
            })
    dist_dir = project_path / "dist"
    candidates = detect_build_artifacts(dist_dir)
    if candidates:
        rels = [str(c.relative_to(dist_dir)) for c in candidates]
        actions.append({
            "key": "archive_dist",
            "label": "归档根目录 dist/ 构建产物到 versions/ 版本目录",
            "detail": "将移动 " + str(len(rels)) + " 个构建产物（移动而非删除，目标已存在时跳过不覆盖）：" + "、".join(rels[:12]) + ("…" if len(rels) > 12 else ""),
            "destructive": True,
            "items": rels,
        })
    required_checks = [c for c in checks if c["required"]]
    passed = sum(1 for c in required_checks if c["ok"])
    return {
        "type": ptype,
        "compliant": bool(required_checks) and passed == len(required_checks),
        "summary": {
            "passed": passed,
            "total": len(required_checks),
            "suggestions": sum(1 for c in checks if not c["required"] and not c["ok"]),
        },
        "checks": checks,
        "actions": actions,
        "standard": standard_info(ptype),
    }


def quick_compliance(project_path: Path, ptype: str) -> bool:
    """轻量合规判断（仅文件存在性，供扫描列表使用）。"""
    for item in required_items(ptype):
        ok, _ = check_item(project_path, item)
        if not ok:
            return False
    return True


def _fix_action_for(item: dict) -> dict | None:
    mapping = {
        "readme": ("create_readme", "创建 README.md", "按该类型的标准模板生成 README.md"),
        "version": ("create_version", "创建 VERSION", "写入版本号 0.1.0（可后续修改）"),
        "changelog": ("create_changelog", "创建 CHANGELOG.md", "生成标准更新日志模板"),
        "gitignore": ("create_gitignore", "创建 .gitignore", "生成标准忽略规则"),
        "versions": ("create_versions", "创建 versions/ 目录", "建立版本归档目录"),
        "git": ("git_init", "初始化 Git 仓库", "git init + 首次提交"),
    }
    fix = mapping.get(item["key"])
    if not fix:
        return None
    return {"key": fix[0], "label": fix[1], "detail": fix[2], "destructive": False}


def apply_fix(project_path: Path, ptype: str, title: str, description: str,
              keys: list[str], confirm: bool = False) -> dict:
    results = []
    for key in keys:
        try:
            results.append({"key": key, **(_execute_fix(project_path, ptype, title, description, key, confirm))})
        except Exception as exc:  # noqa: BLE001
            results.append({"key": key, "ok": False, "message": str(exc)})
    return {"results": results}


def _execute_fix(project_path: Path, ptype: str, title: str, description: str,
                 key: str, confirm: bool) -> dict:
    if key in ("archive_dist",) and not confirm:
        return {"ok": False, "message": "该操作会移动文件，需要显式确认后再执行"}

    if key == "create_readme":
        spec = presets.PRESETS.get(ptype, presets.PRESETS["其他"])
        template = spec.get("files", {}).get("README.md", presets.README_BASIC)
        _write(project_path / "README.md", template.format(title=title or project_path.name, description=description or ""))
        return {"ok": True, "message": "已创建 README.md"}
    if key == "create_version":
        _write(project_path / "VERSION", "0.1.0\n")
        return {"ok": True, "message": "已创建 VERSION（0.1.0）"}
    if key == "create_changelog":
        _write(project_path / "CHANGELOG.md", presets.CHANGELOG_TEMPLATE)
        return {"ok": True, "message": "已创建 CHANGELOG.md"}
    if key == "create_contract":
        from .contract import write_contract
        write_contract(project_path, ptype, title or project_path.name, description or "", force=False)
        return {"ok": True, "message": "已生成 AGENTS.md 项目契约"}
    if key == "create_gitignore":
        content = presets.GITIGNORE_SOFTWARE if ptype == "软件" else presets.GITIGNORE_BASIC
        _write(project_path / ".gitignore", content)
        return {"ok": True, "message": "已创建 .gitignore"}
    if key == "create_versions":
        (project_path / "versions").mkdir(parents=True, exist_ok=True)
        return {"ok": True, "message": "已创建 versions/"}
    if key == "mkdir_versions":
        (project_path / "versions").mkdir(parents=True, exist_ok=True)
        return {"ok": True, "message": "已创建 versions/"}
    if key == "mkdir_src":
        (project_path / "src").mkdir(parents=True, exist_ok=True)
        return {"ok": True, "message": "已创建 src/"}
    if key == "mkdir_tests":
        (project_path / "tests").mkdir(parents=True, exist_ok=True)
        return {"ok": True, "message": "已创建 tests/"}
    if key == "git_init":
        ok = presets._git_init_commit(project_path, None)
        return {"ok": ok, "message": "Git 初始化并完成首次提交" if ok else "Git 初始化失败（请检查 git 是否可用）"}
    if key == "archive_dist":
        return archive_root_dist(project_path)
    return {"ok": False, "message": f"未知动作：{key}"}


def archive_root_dist(project_path: Path, version: str | None = None) -> dict:
    """把根目录 dist/ 的构建产物移动到 versions/vX.Y.Z/dist/（version 缺省读 VERSION）。"""
    dist_dir = project_path / "dist"
    candidates = detect_build_artifacts(dist_dir)
    if not candidates:
        return {"ok": True, "message": "根目录 dist/ 没有需要归档的构建产物"}
    version = version or read_version(project_path) or "0.1.0"
    target = project_path / "versions" / f"v{version}" / "dist"
    target.mkdir(parents=True, exist_ok=True)
    moved, skipped, failed = [], [], []
    for src in candidates:
        dst = target / src.name
        if dst.exists():
            skipped.append(src.name + "（目标已存在，跳过）")
            continue
        try:
            os.replace(str(src), str(dst))
            moved.append(src.name)
        except OSError as exc:
            failed.append(src.name + "（" + str(exc) + "）")
    msg = "已归档到 " + str(target.relative_to(project_path))
    if moved:
        msg += "：" + "、".join(moved[:12]) + ("…" if len(moved) > 12 else "")
    if skipped:
        msg += "；跳过：" + "、".join(skipped[:6])
    if failed:
        msg += "；失败：" + "、".join(failed[:6])
    return {"ok": not failed, "message": msg}


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
