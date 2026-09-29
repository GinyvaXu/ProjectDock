"""管理协议（protocols）与版本方案（version schemes）测试。"""
from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path

import pytest

from projectdock import compliance, contract, presets, protocols, versioning
from projectdock.protocols import PROTOCOLS, VERSION_SCHEMES


# ---------- 协议注册表 ----------

def test_protocols_registry_integrity():
    assert set(PROTOCOLS) == set(presets.PRESETS)
    assert len(PROTOCOLS) == 12
    for name, proto in PROTOCOLS.items():
        assert proto.name == name
        assert proto.label and proto.description
        assert proto.version_scheme in VERSION_SCHEMES
        for tab in proto.tabs:
            assert tab in presets.TAB_LABELS, tab
        assert "overview" in proto.tabs and "ai" in proto.tabs
        for item in (*proto.required, *proto.suggested):
            assert item["key"] and item["label"] and item["kind"] in ("file", "dir", "git", "pattern")


def test_new_protocols_mapping():
    assert protocols.version_scheme_for("文档加工") == "none"
    assert protocols.version_scheme_for("工具脚本") == "none"
    assert protocols.version_scheme_for("资料系统") == "archive"
    assert protocols.version_scheme_for("本地应用") == "archive"
    assert protocols.version_scheme_for("克隆仓库") == "upstream"
    assert protocols.build_archive_for("资料系统") is False
    assert protocols.build_archive_for("软件") is True
    assert protocols.version_scheme_for("未知类型") == "semver"  # 自定义/未知回退


def test_version_scheme_override_priority():
    assert protocols.version_scheme_for("资料系统", "semver") == "semver"
    assert protocols.version_scheme_for("软件", "none") == "none"
    assert protocols.version_scheme_for("软件", "bogus") == "semver"


def test_tabs_for_new_types():
    assert presets.tabs_for_type("文档加工") == ["overview", "ai", "docs"]
    assert "versions" in presets.tabs_for_type("本地应用")
    assert "github" in presets.tabs_for_type("克隆仓库")
    assert "compliance" not in presets.tabs_for_type("工具脚本")
    assert "ailog" not in presets.tabs_for_type("软件")  # 日志并入 AI 栏目


def test_required_items_from_protocols():
    assert [i["key"] for i in compliance.required_items("文档加工")] == []
    assert [i["key"] for i in compliance.required_items("资料系统")] == ["readme"]
    assert "version" in [i["key"] for i in compliance.required_items("软件")]
    assert compliance.required_items("自定义类型") == [i for i in compliance.required_items("自定义类型")]  # 回退不炸


# ---------- 合规（协议驱动） ----------

def test_compliance_empty_required_is_compliant(tmp_path):
    (tmp_path / "任意").mkdir(exist_ok=True)
    report = compliance.check_compliance(tmp_path, "文档加工")
    assert report["compliant"] is True
    assert report["summary"]["total"] == 0
    assert [a["key"] for a in report["actions"]] == []


def test_compliance_archive_type_skips_build_actions(tmp_path):
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "资料包_v1.0.zip").write_text("x", encoding="utf-8")
    report = compliance.check_compliance(tmp_path, "资料系统")
    assert report["compliant"] is True
    assert "archive_dist" not in [a["key"] for a in report["actions"]]
    # 软件类型仍会提示归档
    report2 = compliance.check_compliance(tmp_path, "软件")
    assert "archive_dist" in [a["key"] for a in report2["actions"]]


def test_standard_info_has_version_scheme():
    info = compliance.standard_info("资料系统")
    assert info["version_scheme"] == "archive"
    assert info["required"] == ["README.md 项目说明"]


# ---------- 版本方案 ----------

def _mk(path: Path, rel: str, content: str = "x", mtime: float | None = None) -> Path:
    f = path / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    if mtime is not None:
        os.utime(f, (mtime, mtime))
    return f


def test_archive_summary(tmp_path):
    _mk(tmp_path, "archive/v1_20260911/资料包_v1_20260911.zip", mtime=1000)
    _mk(tmp_path, "archive/v1.1_20260911/资料包_v1.1_20260911.zip", mtime=2000)
    _mk(tmp_path, "versions/v2_20260911/交付物.zip", mtime=3000)
    _mk(tmp_path, "dist/对外资料包.zip", mtime=4000)
    summary = versioning.project_version_summary(tmp_path, scheme="archive", build_archive=False)
    assert summary["scheme"] == "archive"
    assert summary["version"] is None
    names = [e["name"] for e in summary["artifacts"]["versions"]]
    assert names == ["v2_20260911", "v1.1_20260911", "v1_20260911"]
    assert [f["name"] for f in summary["artifacts"]["dist"]] == ["对外资料包.zip"]
    assert summary["artifacts"]["latest"][0]["name"] == "对外资料包.zip"
    assert summary["root_dist_newer"] is False


def test_upstream_summary_readonly(tmp_path):
    _mk(tmp_path, "VERSION", "3.0.2\n")
    _mk(tmp_path, "CHANGELOG.md", "# 更新日志\n\n## [3.0.2] - 2026-01-01\n### Added\n- x\n")
    _mk(tmp_path, "versions/v3.0.2/dist/app.exe", mtime=1000)
    _mk(tmp_path, "dist/app.exe", mtime=9999999999)  # 更新但不应标未归档
    summary = versioning.project_version_summary(tmp_path, scheme="upstream", build_archive=False)
    assert summary["scheme"] == "upstream"
    assert summary["version"] == "3.0.2"
    assert summary["changelog"][0]["version"] == "3.0.2"
    assert summary["artifacts"]["root_dist_newer"] is False


def test_semver_summary_unchanged(tmp_path):
    _mk(tmp_path, "VERSION", "1.0.0\n")
    _mk(tmp_path, "versions/v1.0.0/dist/app.exe", mtime=1000)
    _mk(tmp_path, "dist/app.exe", mtime=9999999999)
    summary = versioning.project_version_summary(tmp_path, scheme="semver", build_archive=True)
    assert summary["scheme"] == "semver"
    assert summary["version"] == "1.0.0"
    assert summary["artifacts"]["root_dist_newer"] is True


def test_none_summary_empty(tmp_path):
    _mk(tmp_path, "VERSION", "1.0.0\n")
    summary = versioning.project_version_summary(tmp_path, scheme="none")
    assert summary["scheme"] == "none"
    assert summary["version"] is None
    assert summary["artifacts"]["versions"] == []
    assert summary["artifacts"]["dist"] == []


# ---------- 契约（按方案渲染） ----------

def test_contracts_by_scheme():
    archive = contract.contract_for("资料系统", presets.PRESETS["资料系统"], "资料库")
    assert "日期归档" in archive and "archive/v<序号>_<YYYYMMDD>/" in archive
    upstream = contract.contract_for("克隆仓库", presets.PRESETS["克隆仓库"], "克隆")
    assert "上游" in upstream and "只读" in upstream
    lite = contract.contract_for("文档加工", presets.PRESETS["文档加工"], "加工")
    assert "不强制 git 与版本归档" in lite


# ---------- API ----------

def test_api_types_include_new_protocols(client):
    types = client.get("/api/types").json()
    by_name = {t["name"]: t for t in types}
    assert by_name["资料系统"]["version_scheme"] == "archive"
    assert by_name["克隆仓库"]["tabs"] == ["overview", "ai", "versions", "github"]


def test_api_unmanaged_and_import(client, state):
    root = state.settings.root
    (root / "Project1-软件-A").mkdir()
    (root / "任意文件夹").mkdir()
    (root / ".hidden").mkdir()
    un = client.get("/api/projects/unmanaged").json()
    assert [u["name"] for u in un] == ["任意文件夹"]
    resp = client.post("/api/projects/import", json={"path": str(root / "任意文件夹"), "type": "其他", "description": ""})
    assert resp.status_code == 201
    assert client.get("/api/projects/unmanaged").json() == []
    projects = client.get("/api/projects").json()
    assert "任意文件夹" in [p["name"] for p in projects]


def test_api_free_style_manages_everything(client, state):
    root = state.settings.root
    (root / "Project1-软件-A").mkdir()
    (root / "任意文件夹").mkdir()
    state.settings.update(naming_style="free")
    projects = client.get("/api/projects").json()
    assert {p["name"] for p in projects} == {"Project1-软件-A", "任意文件夹"}
    assert client.get("/api/projects/unmanaged").json() == []


def test_api_version_scheme_override(client, state):
    root = state.settings.root
    (root / "Project1-软件-A").mkdir()
    resp = client.put("/api/projects/Project1-软件-A", json={"version_scheme": "archive"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["version_scheme"] == "archive" and body["version_scheme_set"] == "archive"
    versions = client.get("/api/projects/Project1-软件-A/versions").json()
    assert versions["scheme"] == "archive"
    bad = client.put("/api/projects/Project1-软件-A", json={"version_scheme": "xxx"})
    assert bad.status_code == 400
    cleared = client.put("/api/projects/Project1-软件-A", json={"version_scheme": ""})
    assert cleared.json()["version_scheme_set"] == ""
    assert cleared.json()["version_scheme"] == "semver"  # 软件协议默认


def test_api_project_list_includes_scheme(client, state):
    root = state.settings.root
    (root / "Project1-软件-A").mkdir()
    projects = client.get("/api/projects").json()
    p = next(x for x in projects if x["name"] == "Project1-软件-A")
    assert p["version_scheme"] == "semver" and p["version_scheme_set"] == ""


# ---------- 别名目录（junction） ----------

@pytest.mark.skipif(sys.platform != "win32", reason="junction 仅 Windows")
def test_scan_skips_junction_alias(tmp_path):
    target = tmp_path / "Project1-Real"
    target.mkdir()
    link = tmp_path / "Project9-Alias"
    r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip("无法创建 junction：" + (r.stderr or r.stdout))
    from projectdock.scanner import scan_root
    assert [p["name"] for p in scan_root(tmp_path)] == ["Project1-Real"]
