from __future__ import annotations

from pydantic import BaseModel, Field

PROJECT_TYPES = ["软件", "网站", "游戏", "PPT", "文稿", "脚本", "其他"]
AGENT_NAMES = ["claude", "pi"]
THEMES = ["system", "light", "dark"]


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    type: str = "其他"
    description: str = ""
    preset: bool = True
    github: bool | None = None


class ProjectImport(BaseModel):
    path: str = Field(min_length=1)
    type: str = "其他"
    description: str = ""


class ProjectInit(BaseModel):
    type: str | None = None
    name: str | None = None
    description: str | None = None
    git: bool = True


class AgentRun(BaseModel):
    project_id: str
    prompt: str = Field(min_length=1)
    agent: str | None = None  # None 时回落全局设置（默认 pi）


class BuildRun(BaseModel):
    script: str


class CustomTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    label: str | None = None
    description: str = ""
    dirs: list[str] = []
    files: dict[str, str] = {}
    git: bool = True


class OpenPath(BaseModel):
    path: str = Field(min_length=1)


class ComplianceFix(BaseModel):
    actions: list[str] = []
    confirm: bool = False


class ReleaseRun(BaseModel):
    version: str = Field(min_length=1)
    changelog: str = ""
    build_script: str | None = None
    push: bool = False


class SettingsUpdate(BaseModel):
    root: str | None = None
    agent: str | None = None
    theme: str | None = None
    github_auto: bool | None = None
    github_visibility: str | None = None
    backup: bool | None = None
