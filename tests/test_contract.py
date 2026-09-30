from __future__ import annotations

from projectdock import ailog, contract
from projectdock.presets import PRESETS, apply_preset


def _software(tmp_path, name="契约项目"):
    proj = tmp_path / f"项目1-软件-{name}"
    proj.mkdir()
    (proj / "VERSION").write_text("1.2.3\n", encoding="utf-8")
    (proj / "CHANGELOG.md").write_text("# 更新日志\n\n## [1.2.3] - 2026-08-12\n### Added\n- x\n", encoding="utf-8")
    return proj


def test_software_contract_contains_required_sections(tmp_path):
    proj = _software(tmp_path)
    text = contract.contract_for("软件", PRESETS["软件"], proj.name)
    for kw in ("版本号唯一来源", "不主动 push", "versions/vX.Y.Z/dist", "AI 操作日志", "logs/ai/", "grill", "更新日志"):
        assert kw in text, kw


def test_generic_and_lite_contracts():
    website = contract.contract_for("网站", PRESETS["网站"], "站点")
    assert "AI 操作日志" in website and "不主动 push" in website
    doc = contract.contract_for("文稿", PRESETS["文稿"], "文档")
    assert "AI 操作日志" in doc and "不强制 git" in doc


def test_write_contract_and_dynamic_context(tmp_path):
    proj = _software(tmp_path)
    path = contract.write_contract(proj, "软件", proj.name)
    assert path.name == "AGENTS.md"
    assert (proj / "AGENTS.md").is_file()
    # 不覆盖已存在
    original = (proj / "AGENTS.md").read_text(encoding="utf-8")
    contract.write_contract(proj, "软件", proj.name, force=False)
    assert (proj / "AGENTS.md").read_text(encoding="utf-8") == original
    # force 覆盖
    contract.write_contract(proj, "软件", proj.name, force=True)
    assert (proj / "AGENTS.md").is_file()
    ctx = contract.dynamic_context(proj)
    assert "1.2.3" in ctx
    assert "项目当前状态" in ctx


def test_preset_generates_full_contract(tmp_path):
    proj = tmp_path / "项目2-软件-契约预设"
    apply_preset(proj, "软件", "契约预设", "desc", git=False)
    agen = (proj / "AGENTS.md").read_text(encoding="utf-8")
    assert "版本号唯一来源" in agen
    assert "AI 操作日志" in agen


def test_ailog_write_and_list(tmp_path):
    proj = _software(tmp_path)
    assert ailog.list_logs(proj) == []
    p1 = ailog.write_log(proj, agent="codex", action="写日志模块", result="done", summary="完成")
    ailog.write_log(proj, agent="claude", action="修 bug", result="failed", summary="失败", source="inapp")
    assert p1.parent == proj / "logs" / "ai"
    logs = ailog.list_logs(proj)
    assert len(logs) == 2
    actions = {e["action"] for e in logs}
    assert actions == {"写日志模块", "修 bug"}
    inapp = next(e for e in logs if e["source"] == "inapp")
    assert inapp["action"] == "修 bug"
    assert all("file" in e for e in logs)
    recent = ailog.recent_summary(proj, limit=1)
    assert len(recent) == 1 and "claude" in recent[0]
