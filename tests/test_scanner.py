from __future__ import annotations

from projectdock.scanner import find_next_index, make_folder_name, parse_project_dir, scan_root


def test_parse_project_dir():
    assert parse_project_dir("项目12-软件-AgentFloat") == (12, "软件", "AgentFloat")
    assert parse_project_dir("项目1-PPT-情景模拟PPT") == (1, "PPT", "情景模拟PPT")
    assert parse_project_dir("项目2-游戏") == (2, "游戏", "游戏")
    assert parse_project_dir("普通文件夹") is None


def test_find_next_index(tmp_path):
    (tmp_path / "项目1-软件-A").mkdir()
    (tmp_path / "项目3-网站-B").mkdir()
    (tmp_path / "资料").mkdir()
    assert find_next_index(tmp_path) == 4


def test_make_folder_name(tmp_path):
    (tmp_path / "项目2-软件-A").mkdir()
    name = make_folder_name(tmp_path, "软件", "新项目")
    assert name == "项目3-软件-新项目"


def test_scan_root(tmp_path):
    (tmp_path / "项目1-软件-A").mkdir()
    (tmp_path / "项目2-文稿-B").mkdir()
    (tmp_path / "普通").mkdir()
    (tmp_path / "项目1-软件-A" / "VERSION").write_text("1.2.3\n", encoding="utf-8")
    projects = scan_root(tmp_path)
    assert len(projects) == 2
    by_name = {p["name"]: p for p in projects}
    assert by_name["项目1-软件-A"]["type"] == "软件"
    assert by_name["项目1-软件-A"]["version"] == "1.2.3"
    assert by_name["项目2-文稿-B"]["has_git"] is False
