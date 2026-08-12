from __future__ import annotations

import subprocess

import projectdock.presets as presets_module
from projectdock.presets import apply_preset

IDENTITY = {"name": "Tester", "email": "tester@example.com"}


def test_git_failure_reported(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "git")

    monkeypatch.setattr(presets_module.subprocess, "run", boom)
    project = tmp_path / "项目1-软件-X"
    result = apply_preset(project, "软件", "X", git=True, git_identity=IDENTITY)
    assert result["git"] is False
    assert "git 初始化失败" in result["message"]
