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
    agent: str = "claude"


class BuildRun(BaseModel):
    script: str


class SettingsUpdate(BaseModel):
    root: str | None = None
    agent: str | None = None
    theme: str | None = None
