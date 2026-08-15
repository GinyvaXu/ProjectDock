"""技术栈文档：TECHSTACK.md 的模板与解析。

格式约定（供 ProjectDock UI 与 AI agent 共用）：
- `## 概览`：一个表格（维度 | 内容），列语言/运行时、主要框架、数据存储、前端、构建与打包、测试等；
- `## 核心功能实现`：每个关键功能一个 `### 小节`，内含 `- **实现逻辑**：...` 与 `- **技术手段**：...` 两条要点。
要求：详细但简明清晰，先讲功能做什么，再讲用什么技术、为什么。
"""
from __future__ import annotations

from pathlib import Path

TECHSTACK_FILENAME = "TECHSTACK.md"

TEMPLATE = """# 技术栈 — {title}

## 概览
| 维度 | 内容 |
|------|------|
| 语言/运行时 | （如 Python 3.12） |
| 主要框架 | （如 FastAPI / pywebview） |
| 数据存储 | （如 SQLite） |
| 前端 | （如 原生 HTML/CSS/JS） |
| 构建与打包 | （如 PyInstaller + Inno Setup） |
| 测试 | （如 pytest + coverage） |

## 核心功能实现
### （功能名称）
- **实现逻辑**：（该功能做什么、怎么做的流程）
- **技术手段**：（用什么技术/库/数据结构实现，为什么这么选）
"""


def parse_techstack(content: str) -> dict:
    """把 TECHSTACK.md 解析成结构化视图：{overview, features}。

    解析失败/内容缺失时返回空结构，由 UI 展示原文或引导撰写。
    """
    overview: list[dict] = []
    features: list[dict] = []
    raw = content or ""
    lines = raw.splitlines()
    in_overview = False
    in_features = False
    current: dict | None = None
    seen_header = {"概览": False, "功能": False}

    def close_feature() -> None:
        nonlocal current
        if current and (current["logic"] or current["means"]):
            features.append(current)
        current = None

    for line in lines:
        s = line.strip()
        if s.startswith("## "):
            close_feature()
            heading = s[3:].strip()
            in_overview = heading == "概览"
            in_features = heading == "核心功能实现"
            if heading == "概览":
                seen_header["概览"] = True
            if heading == "核心功能实现":
                seen_header["功能"] = True
            continue
        if in_overview and s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if len(cells) >= 2 and not all(set(c) <= set("-: ") for c in cells):
                if cells[0] and cells[0] != "维度" and not cells[0].startswith("---"):
                    overview.append({"label": cells[0], "value": cells[1]})
            continue
        if in_features:
            if s.startswith("### "):
                close_feature()
                current = {"title": s[4:].strip(), "logic": [], "means": []}
                continue
            if current is None:
                continue
            if s.startswith("- **实现逻辑**"):
                current["logic"].append(s[len("- **实现逻辑**"):].lstrip("：: ").strip())
            elif s.startswith("- **技术手段**"):
                current["means"].append(s[len("- **技术手段**"):].lstrip("：: ").strip())
            elif s.startswith("- ") and not current["means"]:
                current["logic"].append(s[2:].strip())
            elif s.startswith("- ") and current["means"]:
                current["means"].append(s[2:].strip())
    close_feature()
    return {
        "has_overview": seen_header["概览"] or bool(overview),
        "overview": overview,
        "features": features,
        "raw": raw,
    }


def techstack_path(project_path: Path) -> Path:
    return project_path / TECHSTACK_FILENAME


def read_techstack(project_path: Path) -> dict:
    path = techstack_path(project_path)
    content = ""
    if path.is_file():
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            content = ""
    parsed = parse_techstack(content)
    parsed["exists"] = bool(content.strip())
    parsed["path"] = str(path)
    parsed["content"] = content
    return parsed


def write_techstack(project_path: Path, content: str) -> dict:
    path = techstack_path(project_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    parsed = parse_techstack(content)
    parsed["exists"] = True
    parsed["path"] = str(path)
    parsed["content"] = content
    return parsed


def ensure_template(project_path: Path, title: str) -> dict:
    """缺失时用模板创建 TECHSTACK.md（不覆盖已有内容）。"""
    path = techstack_path(project_path)
    if path.is_file():
        return read_techstack(project_path)
    return write_techstack(project_path, TEMPLATE.format(title=title))
