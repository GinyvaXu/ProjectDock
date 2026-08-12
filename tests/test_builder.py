from __future__ import annotations

import sys

from projectdock.builder import command_for, find_build_scripts


def test_find_build_scripts_priority(tmp_path):
    (tmp_path / "build_debug.py").write_text("", encoding="utf-8")
    (tmp_path / "build_exe.py").write_text("", encoding="utf-8")
    (tmp_path / "打包.bat").write_text("", encoding="utf-8")
    (tmp_path / "build.png").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("", encoding="utf-8")
    scripts = find_build_scripts(tmp_path)
    assert [s["name"] for s in scripts] == ["build_debug.py", "build_exe.py", "打包.bat"]
    assert scripts[0]["kind"] == "python"
    assert scripts[2]["kind"] == "batch"


def test_find_build_scripts_missing_dir(tmp_path):
    assert find_build_scripts(tmp_path / "不存在") == []


def test_command_for():
    py = {"name": "build_debug.py", "path": "C:/x/build_debug.py", "kind": "python"}
    assert command_for(py) == [sys.executable, "C:/x/build_debug.py"]
    bat = {"name": "打包.bat", "path": "C:/x/打包.bat", "kind": "batch"}
    assert command_for(bat) == ["cmd", "/c", "C:/x/打包.bat"]
