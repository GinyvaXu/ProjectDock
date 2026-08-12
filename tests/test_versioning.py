from __future__ import annotations

from projectdock.versioning import (
    list_build_artifacts,
    parse_changelog,
    project_version_summary,
    read_version,
)


def _make_project(tmp_path):
    project = tmp_path / "项目1-软件-Demo"
    project.mkdir()
    return project


def test_read_version(tmp_path):
    project = _make_project(tmp_path)
    assert read_version(project) is None
    (project / "VERSION").write_text("1.4.0\n", encoding="utf-8")
    assert read_version(project) == "1.4.0"
    (project / "VERSION").write_text("v2.1.0-beta.1\n", encoding="utf-8")
    assert read_version(project) == "2.1.0-beta.1"


def test_parse_changelog(tmp_path):
    project = _make_project(tmp_path)
    (project / "CHANGELOG.md").write_text(
        "# 更新日志\n\n## [1.4.0] - 2026-08-01\n### Added\n- 新功能A\n- 新功能B\n### Fixed\n- 修复C\n\n## [1.3.0] - 2026-07-01\n### Changed\n- 改进D\n",
        encoding="utf-8",
    )
    entries = parse_changelog(project)
    assert len(entries) == 2
    first = entries[0]
    assert first["version"] == "1.4.0"
    assert first["date"] == "2026-08-01"
    assert first["groups"][0]["title"] == "Added"
    assert first["groups"][0]["items"] == ["新功能A", "新功能B"]
    assert first["groups"][1]["items"] == ["修复C"]


def test_list_build_artifacts(tmp_path):
    project = _make_project(tmp_path)
    dist = project / "versions" / "v1.4.0" / "dist"
    dist.mkdir(parents=True)
    (dist / "app_debug.exe").write_bytes(b"x" * 100)
    (project / "dist").mkdir()
    (project / "dist" / "app.exe").write_bytes(b"y" * 50)
    arts = list_build_artifacts(project)
    assert arts["versions"][0]["name"] == "v1.4.0"
    assert arts["versions"][0]["artifacts"][0]["name"] == "app_debug.exe"
    assert arts["versions"][0]["artifacts"][0]["size"] == 100
    assert arts["dist"][0]["name"] == "app.exe"


def test_project_version_summary(tmp_path):
    project = _make_project(tmp_path)
    (project / "VERSION").write_text("0.1.0\n", encoding="utf-8")
    summary = project_version_summary(project)
    assert summary["version"] == "0.1.0"
    assert summary["has_versions_dir"] is False
