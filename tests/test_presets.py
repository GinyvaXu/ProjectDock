from __future__ import annotations

import subprocess

from projectdock.presets import PRESETS, apply_preset

IDENTITY = {"name": "Tester", "email": "tester@example.com"}


def test_presets_cover_all_types():
    assert set(PRESETS) == {"软件", "网站", "游戏", "PPT", "文稿", "脚本", "其他"}


def test_apply_preset_software_creates_files_and_git(tmp_path):
    project = tmp_path / "项目1-软件-Demo"
    result = apply_preset(project, "软件", "Demo", "一个演示项目", git=True, git_identity=IDENTITY)
    assert (project / "README.md").is_file()
    assert (project / "VERSION").read_text(encoding="utf-8").strip() == "0.1.0"
    assert (project / ".gitignore").is_file()
    assert (project / "CHANGELOG.md").is_file()
    assert (project / "src").is_dir()
    assert (project / "tests").is_dir()
    assert result["git"] is True
    head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=str(project), capture_output=True, text=True
    )
    assert head.returncode == 0 and head.stdout.strip()


def test_apply_preset_ppt_no_git(tmp_path):
    project = tmp_path / "项目1-PPT-演示"
    result = apply_preset(project, "PPT", "演示", git=True, git_identity=IDENTITY)
    assert (project / "素材").is_dir()
    assert (project / "输出").is_dir()
    assert result["git"] is False
    assert not (project / ".git").exists()


def test_apply_preset_website(tmp_path):
    project = tmp_path / "项目1-网站-Site"
    apply_preset(project, "网站", "Site", git=True, git_identity=IDENTITY)
    assert (project / "index.html").is_file()
    assert (project / "assets" / "css").is_dir()
