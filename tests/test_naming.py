"""命名规范风格（naming styles）测试：解析 / 识别 / 创建 / 优先级 / API。"""
from __future__ import annotations

from pathlib import Path

from projectdock import naming
from projectdock.config import Settings
from projectdock.naming import make_folder_name, next_index, parse_name, resolve_style, sanitize_title
from projectdock.scanner import find_next_index, list_unmanaged, parse_project_dir, parse_project_entry, scan_root


# ---------- 解析 ----------

def test_parse_classic_style():
    p = naming.STYLES["classic"].parse("项目12-软件-AgentFloat")
    assert p is not None
    assert (p.style, p.index, p.index_raw, p.ptype, p.title) == ("classic", 12, "12", "软件", "AgentFloat")
    p2 = naming.STYLES["classic"].parse("项目2-游戏")
    assert (p2.index, p2.ptype, p2.title) == (2, "游戏", "游戏")
    assert naming.STYLES["classic"].parse("普通文件夹") is None
    assert naming.STYLES["classic"].parse("项目1-") is None


def test_parse_local_style():
    p = naming.STYLES["local"].parse("Project0-ComfyUI")
    assert (p.style, p.index, p.index_raw, p.ptype, p.title) == ("local", 0, "0", "", "ComfyUI")
    p2 = naming.STYLES["local"].parse("Project2.1-洛琪希美图分类")
    assert (p2.index, p2.index_raw, p2.title) == (2, "2.1", "洛琪希美图分类")
    p3 = naming.STYLES["local"].parse("project3-个案")
    assert p3 is not None and p3.index == 3  # 大小写不敏感
    assert naming.STYLES["local"].parse("ProjectDock - 本地项目管理器部署") is None
    assert naming.STYLES["local"].parse("Project-x") is None
    assert naming.STYLES["local"].parse("Project1-") is None


def test_parse_name_returns_style():
    assert parse_name("项目3-软件-X").style == "classic"
    assert parse_name("Project3-AgentFloat克隆仓库").style == "local"
    assert parse_name("普通文件夹") is None


def test_parse_project_dir_backcompat():
    assert parse_project_dir("项目12-软件-AgentFloat") == (12, "软件", "AgentFloat")
    assert parse_project_dir("Project2.1-洛琪希美图分类") == (2, "", "洛琪希美图分类")
    assert parse_project_dir("普通文件夹") is None
    entry = parse_project_entry("Project2.1-洛琪希美图分类")
    assert entry is not None and entry.style == "local" and entry.index_raw == "2.1"


# ---------- 识别 / 编号 / 创建 ----------

def test_detect_style(tmp_path):
    assert naming.detect_style(tmp_path) == "classic"  # 空目录 → 默认
    (tmp_path / "项目1-软件-A").mkdir()
    (tmp_path / "Project2-图库").mkdir()
    (tmp_path / "Project3-工具").mkdir()
    assert naming.detect_style(tmp_path) == "local"  # 多数命中


def test_next_index_local_counts_sub_index(tmp_path):
    for name in ("Project0-ComfyUI", "Project1-大学", "Project2.0-图库", "Project2.1-洛琪希", "Project3-AgentFloat"):
        (tmp_path / name).mkdir()
    assert next_index(tmp_path, "local") == 4
    assert next_index(tmp_path, "classic") == 1


def test_make_folder_name_styles(tmp_path):
    # auto：本机风格资料库 → ProjectN-名称（名称不含类型）
    (tmp_path / "Project1-大学").mkdir()
    assert make_folder_name(tmp_path, "软件", "新项目") == "Project2-新项目"
    # 显式风格覆盖自动识别
    assert make_folder_name(tmp_path, "软件", "新项目", style_id="classic") == "项目1-软件-新项目"
    # classic 资料库 → 保持经典三段式
    other = tmp_path / "other"
    other.mkdir()
    (other / "项目5-软件-A").mkdir()
    assert make_folder_name(other, "软件", "新项目") == "项目6-软件-新项目"


def test_find_next_index_and_make_folder_backcompat(tmp_path):
    (tmp_path / "项目1-软件-A").mkdir()
    (tmp_path / "项目3-网站-B").mkdir()
    assert find_next_index(tmp_path) == 4
    assert make_folder_name(tmp_path, "软件", "新项目") == "项目4-软件-新项目"  # 经 scanner 兼容入口
    assert sanitize_title("   ") == "未命名项目"


def test_scan_root_mixed_styles_and_db_type(tmp_path):
    (tmp_path / "项目1-软件-A").mkdir()
    (tmp_path / "Project2-图库管理").mkdir()
    (tmp_path / "Project3-文档").mkdir()
    db_rows = {"Project2-图库管理": {"type": "其他", "description": "d"}, "Project3-文档": {"type": "文稿"}}
    projects = scan_root(tmp_path, db_rows)
    by_name = {p["name"]: p for p in projects}
    assert len(projects) == 3
    assert by_name["项目1-软件-A"]["type"] == "软件"
    assert by_name["项目1-软件-A"]["style"] == "classic"
    assert by_name["Project3-文档"]["type"] == "文稿"  # 无类型风格：类型以注册表为准
    assert by_name["Project3-文档"]["style"] == "local"


# ---------- 设置 ----------

def test_settings_naming_style(tmp_path):
    settings = Settings(tmp_path / "data")
    assert settings.naming_style == "auto"  # 默认自动识别
    settings.update(naming_style="local")
    assert settings.naming_style == "local"
    assert settings.as_dict()["naming_style"] == "local"
    settings.update(naming_style="不存在的风格")
    assert settings.naming_style == "local"  # 非法值被忽略
    assert Settings(tmp_path / "data").naming_style == "local"  # 持久化


def test_resolve_style_auto_and_unknown(tmp_path):
    (tmp_path / "Project1-XX").mkdir()
    assert resolve_style(tmp_path, "auto") == "local"
    assert resolve_style(tmp_path, "classic") == "classic"
    assert resolve_style(tmp_path, "whatever") == "local"  # 未知 → 自动识别


def test_default_root_detects_all_styles(tmp_path):
    from projectdock.config import _detect_library_root

    lib = tmp_path / "lib"
    sub = lib / "sub"
    sub.mkdir(parents=True)
    (sub / "file.py").write_text("x", encoding="utf-8")
    assert _detect_library_root(sub / "file.py") is None
    (lib / "Project1-大学").mkdir()  # 本机风格
    assert _detect_library_root(sub / "file.py") == lib
    (lib / "Project1-大学").rename(lib / "项目1-软件-大学")  # 经典风格
    assert _detect_library_root(sub / "file.py") == lib


# ---------- free 自由命名风格 ----------

def test_free_style_parse_and_detect(tmp_path):
    (tmp_path / "ProjectDock - 本地项目管理器部署").mkdir()
    (tmp_path / "Project1-XX").mkdir()
    (tmp_path / ".hidden").mkdir()
    free = naming.STYLES["free"]
    assert free.parse("ProjectDock - 本地项目管理器部署").title == "ProjectDock - 本地项目管理器部署"
    assert free.parse(".hidden") is None
    assert parse_name("ProjectDock - 本地项目管理器部署") is None  # 默认不含 free
    got = parse_name("ProjectDock - 本地项目管理器部署", include_free=True)
    assert got is not None and got.style == "free"
    assert naming.detect_style(tmp_path) == "local"  # free 不参与自动识别
    assert resolve_style(tmp_path, "free") == "free"
    assert make_folder_name(tmp_path, "其他", "新文件夹", style_id="free") == "新文件夹"


def test_scan_root_free_and_unmanaged(tmp_path):
    (tmp_path / "Project1-XX").mkdir()
    (tmp_path / "任意文件夹").mkdir()
    (tmp_path / ".hidden").mkdir()
    assert [p["name"] for p in scan_root(tmp_path)] == ["Project1-XX"]
    assert [u["name"] for u in list_unmanaged(tmp_path)] == ["任意文件夹"]
    free = scan_root(tmp_path, style_id="free")
    assert {p["name"] for p in free} == {"Project1-XX", "任意文件夹"}
    assert list_unmanaged(tmp_path, style_id="free") == []


# ---------- API ----------

def test_api_naming_styles(client, state):
    resp = client.get("/api/naming/styles")
    assert resp.status_code == 200
    body = resp.json()
    assert body["current"] == "auto"
    assert body["detected"] == "classic"  # 空资料库 → 默认经典
    ids = [s["id"] for s in body["styles"]]
    assert "classic" in ids and "local" in ids
    assert body["auto"]["id"] == "auto"


def test_api_settings_naming_style(client):
    resp = client.put("/api/settings", json={"naming_style": "local"})
    assert resp.status_code == 200
    assert resp.json()["naming_style"] == "local"
    assert client.get("/api/settings").json()["naming_style"] == "local"
    bad = client.put("/api/settings", json={"naming_style": "xxx"})
    assert bad.status_code == 400


def test_api_create_project_local_style(client, state):
    state.settings.update(naming_style="local")
    resp = client.post("/api/projects", json={"name": "演示项目", "type": "软件", "preset": False})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Project1-演示项目"
    assert body["type"] == "软件"
    assert body["title"] == "演示项目"
    second = client.post("/api/projects", json={"name": "二号", "type": "其他", "preset": False})
    assert second.json()["name"] == "Project2-二号"
    listing = client.get("/api/projects").json()
    by_name = {p["name"]: p for p in listing}
    assert by_name["Project1-演示项目"]["type"] == "软件"  # 类型来自注册表
    assert by_name["Project1-演示项目"]["style"] == "local"


def test_api_rename_preserves_local_style_and_subindex(client, state):
    state.settings.update(naming_style="local")
    root = state.settings.root
    (root / "Project2.1-洛琪希美图分类").mkdir()
    resp = client.put("/api/projects/Project2.1-洛琪希美图分类",
                      json={"name": "洛琪希美图分类", "type": "其他"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Project2.1-洛琪希美图分类"  # 无变化：名称相同
    renamed = client.put("/api/projects/Project2.1-洛琪希美图分类", json={"name": "美图分类"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Project2.1-美图分类"
    assert (root / "Project2.1-美图分类").is_dir()
    assert renamed.json()["title"] == "美图分类"


def test_api_import_local_folder_keeps_type(client, state):
    root = state.settings.root
    target = root / "Project9-导入项目"
    target.mkdir()
    resp = client.post("/api/projects/import", json={"path": str(target), "type": "文稿", "description": "d"})
    assert resp.status_code == 201
    assert resp.json()["type"] == "文稿"  # 无类型风格：保留导入时选择的类型
    assert resp.json()["title"] == "导入项目"


def test_cli_init_local_style(tmp_path, monkeypatch):
    import projectdock.cli as cli
    from projectdock.db import connect

    data_dir = tmp_path / "data"
    root = tmp_path / "lib"
    root.mkdir()
    monkeypatch.setattr(cli, "_app_settings", lambda: Settings(data_dir))
    monkeypatch.setattr(cli, "_db", lambda: connect(data_dir / "data.db"))
    settings = Settings(data_dir)
    settings.update(naming_style="local")
    monkeypatch.setattr(cli, "_app_settings", lambda: settings)
    assert cli.main(["--root", str(root), "init", "脚本项目", "--type", "脚本", "--no-git"]) == 0
    assert (root / "Project1-脚本项目").is_dir()
