"""TECHSTACK.md 技术栈文档：解析、读写、API 与模板。"""
from __future__ import annotations

from pathlib import Path

from projectdock import presets, techstack

SAMPLE = """# 技术栈 — 演示项目

## 概览
| 维度 | 内容 |
|------|------|
| 语言/运行时 | Python 3.12 |
| 主要框架 | FastAPI + pywebview |
| 数据存储 | SQLite |

## 核心功能实现
### 项目扫描
- **实现逻辑**：遍历根目录，解析 `项目NN-类型-名称` 命名并合并注册表元数据。
- **技术手段**：pathlib + 正则；用注册表做增量覆盖，保证重命名/移动后路径唯一。
### 纯逻辑功能
- **实现逻辑**：仅演示只有实现逻辑的小节。
"""


def test_parse_full():
    d = techstack.parse_techstack(SAMPLE)
    assert d["has_overview"] is True
    labels = [o["label"] for o in d["overview"]]
    assert "语言/运行时" in labels and "数据存储" in labels
    assert len(d["features"]) == 2
    scan = d["features"][0]
    assert scan["title"] == "项目扫描"
    assert scan["logic"] and "遍历根目录" in scan["logic"][0]
    assert scan["means"] and "pathlib" in scan["means"][0]
    assert d["features"][1]["logic"] and not d["features"][1]["means"]


def test_parse_empty_and_garbage():
    assert techstack.parse_techstack("")["features"] == []
    d = techstack.parse_techstack("随便写点什么\n没有结构")
    assert d["has_overview"] is False and d["features"] == []


def test_template_roundtrip():
    content = techstack.TEMPLATE.format(title="某项目")
    d = techstack.parse_techstack(content)
    assert d["has_overview"] is True
    assert len(d["overview"]) == 6
    assert len(d["features"]) == 1
    assert d["features"][0]["title"] == "（功能名称）"


def test_read_write_roundtrip(tmp_path):
    proj = tmp_path / "项目1-软件-演示"
    proj.mkdir()
    d = techstack.write_techstack(proj, SAMPLE)
    assert d["exists"] is True
    assert d["path"] == str(proj / "TECHSTACK.md")
    got = techstack.read_techstack(proj)
    assert got["exists"] is True
    assert got["features"][0]["title"] == "项目扫描"
    assert Path(got["path"]).read_text(encoding="utf-8") == SAMPLE


def test_read_missing(tmp_path):
    proj = tmp_path / "项目1-软件-演示"
    proj.mkdir()
    d = techstack.read_techstack(proj)
    assert d["exists"] is False and d["features"] == []


def test_ensure_template_no_overwrite(tmp_path):
    proj = tmp_path / "项目1-软件-演示"
    proj.mkdir()
    d = techstack.ensure_template(proj, "演示")
    assert "# 技术栈 — 演示" in d["content"]
    again = techstack.ensure_template(proj, "演示")
    assert again["content"] == d["content"]
    assert "（功能名称）" in again["content"]


def test_software_preset_includes_techstack():
    files = presets.PRESETS["软件"]["files"]
    assert "TECHSTACK.md" in files
    assert "techstack" in presets.DEFAULT_TABS["软件"]
    assert "techstack" in presets.NEW_TABS


def test_api_techstack_flow(client):
    resp = client.post("/api/projects", json={"name": "演示项目", "type": "软件", "description": "测试"})
    assert resp.status_code == 201
    pid = resp.json()["name"]
    got = client.get(f"/api/projects/{pid}/techstack").json()
    assert got["exists"] is True
    assert got["features"][0]["title"] == "（功能名称）"
    Path(got["path"]).unlink()
    tpl = client.post(f"/api/projects/{pid}/techstack/template").json()
    assert tpl["exists"] is True
    assert "## 概览" in tpl["content"]
    saved = client.put(f"/api/projects/{pid}/techstack", json={"content": SAMPLE}).json()
    assert saved["features"][0]["title"] == "项目扫描"
    got = client.get(f"/api/projects/{pid}/techstack").json()
    assert got["exists"] is True
    assert got["overview"][0]["label"] == "语言/运行时"


def test_api_techstack_unknown_project(client):
    resp = client.get("/api/projects/项目999-软件-不存在/techstack")
    assert resp.status_code == 404
