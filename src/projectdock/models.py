from __future__ import annotations

from pydantic import BaseModel, Field

PROJECT_TYPES = ["软件", "网站", "游戏", "PPT", "文稿", "脚本", "其他"]
AGENT_NAMES = ["claude", "pi", "api", "opencode"]
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
    history: list[dict] = []  # 会话历史 [{role: user|assistant, text}]，供 agent 延续上下文


class AgentBatch(BaseModel):
    project_ids: list[str] = Field(min_length=1)
    prompt: str = Field(min_length=1)
    agent: str | None = None


class BuildRun(BaseModel):
    script: str


class CustomTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    label: str | None = None
    description: str = ""
    dirs: list[str] = []
    files: dict[str, str] = {}
    git: bool = True


class TechstackPayload(BaseModel):
    content: str = Field(max_length=200000)


class OpenPath(BaseModel):
    path: str = Field(min_length=1)


class AILogCreate(BaseModel):
    agent: str = Field(min_length=1, max_length=60)
    action: str = Field(min_length=1, max_length=200)
    result: str = "done"
    summary: str = ""
    details: str = ""
    source: str = "external"


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
    type_tabs: dict[str, list[str]] | None = None
    confirm_policy: dict[str, bool] | None = None
    update_repo: str | None = None
    naming_style: str | None = None  # auto / classic / local（见 naming.STYLES）
    api_base_url: str | None = None  # API 直连（OpenAI 兼容）
    api_model: str | None = None
    api_key: str | None = None
    oc_model: str | None = None  # opencode 会话模型（provider/model）


class OcPtyCreate(BaseModel):
    """创建内嵌终端：kind=opencode（跑 opencode TUI）/ shell（cmd）。"""
    kind: str = "opencode"
    new: bool = False
    cols: int = 100
    rows: int = 30


class OcPtyResize(BaseModel):
    cols: int = 100
    rows: int = 30


class AiTestPayload(BaseModel):
    """测试 API 接入：可传未保存的临时值覆盖设置。"""
    base_url: str | None = None
    api_key: str | None = None


class UpdateInstall(BaseModel):
    path: str = Field(min_length=1)


class BackupRestore(BaseModel):
    name: str = Field(min_length=1)
    confirm: bool = False


class IconPayload(BaseModel):
    """项目图标：mode=auto 按类型/符号生成，mode=upload 上传图片（data 为 base64）。"""
    mode: str = "auto"
    symbol: int | None = None
    data: str = ""


class ProjectUpdate(BaseModel):
    """编辑项目信息：name 会重命名文件夹标题，type 会更新类型（重命名前缀），description 存库。"""
    name: str | None = Field(default=None, max_length=60)
    type: str | None = None
    description: str | None = None
    version_scheme: str | None = None  # ''=跟随类型默认 / semver / archive / upstream / none


class GithubAuthPayload(BaseModel):
    token: str = Field(min_length=1, max_length=200)


class GithubCreatePayload(BaseModel):
    visibility: str = "private"


class GithubSetRemotePayload(BaseModel):
    url: str = Field(min_length=1, max_length=300)


class OpenUrl(BaseModel):
    url: str = Field(min_length=1, max_length=500)
