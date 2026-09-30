"""管理协议（Protocols）：类型 → 骨架 / 合规基线 / 菜单 / 版本方案 / 归档规则的单一数据源。

一个「管理协议」定义一类文件夹怎么被管理：
- 骨架（dirs/files/git）：新建项目时生成什么；
- 合规基线（required/suggested）：哪些是硬要求、哪些是建议；
- 菜单（tabs）：项目抽屉显示哪些页签；
- 版本方案（version_scheme）：semver（VERSION/CHANGELOG/versions/vX.Y.Z）/
  archive（日期+序号归档：archive/v<N>_<YYYYMMDD>/、versions/、dist 交付物）/
  upstream（上游仓库只读版本）/ none（不追踪版本）；
- 归档规则（build_archive）：根目录 dist/installer/build 是否按「未归档构建」处理。

新增类型 = 在此登记一个 Protocol；presets / compliance / 菜单 / 版本页自动生效。
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .techstack import TEMPLATE as TECHSTACK_TEMPLATE

VERSION_SCHEMES = ("semver", "archive", "upstream", "none")

# ---------------------------------------------------------------- 模板

GITIGNORE_SOFTWARE = """# Python 缓存
__pycache__/
*.pyc
build/
dist/
versions/
installer/
.venv/
venv/
.env
logs/
.idea/
.vscode/
"""

GITIGNORE_BASIC = """# 缓存与临时文件
__pycache__/
*.pyc
.DS_Store
.idea/
.vscode/
"""

README_SOFTWARE = """# {title}

{description}

## 技术栈
- Python 3.12

## 快速开始
```bash
python -m pip install -r requirements.txt
python run.py
```

## 测试
```bash
python -m pytest
```

## 版本与构建
- 版本号唯一来源：VERSION 文件；更新内容记录在 CHANGELOG.md
- 构建产物归档到 versions/vX.Y.Z/dist/（仅本地保留，不上传）
"""

README_BASIC = """# {title}

{description}

## 说明
本目录由 ProjectDock 项目坞初始化创建。
"""

README_WEBSITE = """# {title}

{description}

## 结构
- index.html  — 首页
- assets/     — 静态资源（css/js/img）
"""

README_BATCH = """# {title}

{description}

## 说明
文档加工项目：按任务批次组织。批次目录建议 `YYYY.M.D-<主题>`（历史风格）或 `YYYYMMDD-<主题>`。

## 约定
- 每批任务一个目录，内含原始材料、加工产物与说明
- 工具脚本放 `_tools/`；临时文件用后即删
- 交付物命名：`<主题>_<YYYYMMDD>.<扩展名>`
"""

README_DATA = """# {title}

{description}

## 说明
资料/数据系统：编号数据根（如 00~04）+ 归档 + 交付物。

## 归档约定
- 交付批次归档到 `archive/v<序号>_<YYYYMMDD>/`（只增不删、不覆盖）
- `dist/` 存放对外交付物（资料包等），不按构建产物处理
"""

README_APP = """# {title}

{description}

## 说明
本地应用/工具：启动脚本 + 数据目录 + 使用说明。

## 运行
- 启动脚本：`启动.bat`（如有）
- 数据目录：`data/`、`models/`（如有）

## 版本与归档
- 更新批次归档到 `archive/v<序号>_<YYYYMMDD>/`（覆盖前先归档，只增不删）
"""

USAGE_APP = """# {title} 使用说明

## 启动
- 双击 `启动.bat`（如有），或按 README 说明运行

## 数据
- 数据/模型/配置放在项目内对应目录，勿放系统盘临时目录

## 注意
- 覆盖旧数据/产物前先归档到 `archive/v<序号>_<YYYYMMDD>/`
"""

INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; margin: 40px; color: #1d1d1f; }}
    h1 {{ font-size: 2rem; letter-spacing: -0.02em; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p>{description}</p>
</body>
</html>
"""

MAIN_PY = """import sys
import io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def main() -> int:
    print("{title} 脚本运行中……")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""

CHANGELOG_TEMPLATE = """# 更新日志

## [0.1.0] - 2026-08-12
### Added
- 项目初始化（由 ProjectDock 预设生成）
"""

AGENTS_SOFTWARE = """# AGENTS.md

{description}

## 运行与测试
- 测试：python -m pytest
- 构建：python build_debug.py / build_exe.py（产物进 versions/vX.Y.Z/dist/）

## 版本规范
- 版本号唯一来源：VERSION 文件
- 提交前缀：feat: / fix: / release: / build: / chore: / docs:
- 单 main 分支直接开发与发布；不主动 push
"""

GODOT_README = """# {title}

{description}

## 引擎
- Godot 4.x（由 ProjectDock 游戏类型预设创建，请在 Godot 中打开本目录作为项目）

## 建议结构
- scenes/  场景
- scripts/ GDScript
- assets/  素材（精灵/音频/字体）
"""


# ---------------------------------------------------------------- 合规项小工具

def _file(key: str, label: str, name: str) -> dict:
    return {"key": key, "label": label, "kind": "file", "name": name}


def _dir(key: str, label: str, name: str) -> dict:
    return {"key": key, "label": label, "kind": "dir", "name": name}


def _git(label: str = "Git 仓库") -> dict:
    return {"key": "git", "label": label, "kind": "git"}


def _pattern(key: str, label: str, patterns: tuple[str, ...]) -> dict:
    return {"key": key, "label": label, "kind": "pattern", "patterns": patterns}


# ---------------------------------------------------------------- 协议定义

@dataclass(frozen=True)
class Protocol:
    name: str
    label: str
    description: str
    git: bool
    dirs: tuple[str, ...] = ()
    files: Mapping[str, str] = field(default_factory=dict)
    tabs: tuple[str, ...] = ()
    required: tuple[dict, ...] = ()
    suggested: tuple[dict, ...] = ()
    version_scheme: str = "semver"
    build_archive: bool = True

    def as_preset(self) -> dict:
        """转成 presets.PRESETS 兼容结构（label/description/git/dirs/files）。"""
        return {"label": self.label, "description": self.description, "git": self.git,
                "dirs": list(self.dirs), "files": dict(self.files)}


_README = _file("readme", "README.md 项目说明", "README.md")
_GITIGNORE = _file("gitignore", ".gitignore 忽略规则", ".gitignore")
_VERSION = _file("version", "VERSION 文件（版本号唯一来源）", "VERSION")
_CHANGELOG = _file("changelog", "CHANGELOG.md 更新日志", "CHANGELOG.md")
_TECHSTACK = _file("techstack", "TECHSTACK.md 技术栈文档", "TECHSTACK.md")
_CONTRACT = _file("contract", "AGENTS.md 项目契约", "AGENTS.md")

PROTOCOLS: dict[str, Protocol] = {
    # ---------------- 既有 7 类（行为保持） ----------------
    "软件": Protocol(
        name="软件", label="软件",
        description="Python 软件项目骨架：README/VERSION/CHANGELOG/测试/构建规范",
        git=True, dirs=("src", "tests"),
        files={
            "README.md": README_SOFTWARE,
            "VERSION": "0.1.0\n",
            "CHANGELOG.md": CHANGELOG_TEMPLATE,
            "TECHSTACK.md": TECHSTACK_TEMPLATE,
            "requirements.txt": "# 依赖\n",
            ".gitignore": GITIGNORE_SOFTWARE,
            "AGENTS.md": AGENTS_SOFTWARE,
        },
        tabs=("overview", "ai", "versions", "techstack", "github"),
        required=(_README, _VERSION, _CHANGELOG, _TECHSTACK, _GITIGNORE, _git()),
        suggested=(
            _CONTRACT,
            _dir("versions", "versions/ 版本归档目录", "versions"),
            _pattern("build_script", "构建脚本（build*.py / 打包.bat）", ("build*.py", "打包.bat")),
            _dir("src", "src/ 源码目录", "src"),
            _dir("tests", "tests/ 测试目录", "tests"),
        ),
    ),
    "网站": Protocol(
        name="网站", label="网站",
        description="静态网站骨架：index.html + assets/",
        git=True, dirs=("assets/css", "assets/js", "assets/img"),
        files={"README.md": README_WEBSITE, "index.html": INDEX_HTML, ".gitignore": GITIGNORE_BASIC},
        tabs=("overview", "ai", "versions", "github"),
        required=(_README, _GITIGNORE, _git()),
    ),
    "游戏": Protocol(
        name="游戏", label="游戏",
        description="Godot 4 游戏骨架：推荐目录结构",
        git=True, dirs=("scenes", "scripts", "assets/sprites", "assets/audio", "assets/fonts"),
        files={"README.md": GODOT_README, ".gitignore": GITIGNORE_BASIC},
        tabs=("overview", "ai", "versions", "github"),
        required=(_README, _GITIGNORE, _git()),
    ),
    "PPT": Protocol(
        name="PPT", label="PPT",
        description="演示文稿目录：素材/输出 分离",
        git=False, dirs=("素材", "输出", "参考"),
        files={"README.md": README_BASIC},
        tabs=("overview", "ai", "docs"),
        required=(_README,),
    ),
    "文稿": Protocol(
        name="文稿", label="文稿",
        description="文稿/文档目录：docs 结构",
        git=False, dirs=("docs",),
        files={"README.md": README_BASIC},
        tabs=("overview", "ai", "docs"),
        required=(_README,),
    ),
    "脚本": Protocol(
        name="脚本", label="脚本",
        description="Python 脚本工具骨架：main.py",
        git=True, dirs=("scripts",),
        files={"README.md": README_BASIC, "main.py": MAIN_PY, ".gitignore": GITIGNORE_BASIC},
        tabs=("overview", "ai", "versions", "github"),
        required=(_README, _GITIGNORE, _git()),
    ),
    "其他": Protocol(
        name="其他", label="其他",
        description="通用目录：README + git",
        git=True, dirs=(),
        files={"README.md": README_BASIC, ".gitignore": GITIGNORE_BASIC},
        tabs=("overview", "ai", "versions", "github"),
        required=(_README, _GITIGNORE, _git()),
    ),

    # ---------------- 新增 5 类（本机资料库本土化） ----------------
    "文档加工": Protocol(
        name="文档加工", label="文档加工",
        description="文档加工/任务批次：按日期批次组织任务与交付物；不强制 git 与版本号",
        git=False, dirs=(),
        files={"README.md": README_BATCH},
        tabs=("overview", "ai", "docs"),
        required=(),
        suggested=(_README, _dir("_tools", "_tools/ 工具链目录", "_tools")),
        version_scheme="none", build_archive=False,
    ),
    "资料系统": Protocol(
        name="资料系统", label="资料系统",
        description="资料/数据系统：编号数据根 + 归档（archive/vN_日期）+ dist 交付物",
        git=False, dirs=(),
        files={"README.md": README_DATA},
        tabs=("overview", "ai", "versions", "docs"),
        required=(_README,),
        suggested=(_dir("archive", "archive/ 归档目录", "archive"),
                   _dir("dist", "dist/ 交付物目录", "dist")),
        version_scheme="archive", build_archive=False,
    ),
    "本地应用": Protocol(
        name="本地应用", label="本地应用",
        description="本地应用/工具：启动脚本 + 数据目录 + 使用说明；更新按日期批次归档",
        git=True, dirs=(),
        files={"README.md": README_APP, "使用说明.md": USAGE_APP},
        tabs=("overview", "ai", "versions", "docs"),
        required=(_README,),
        suggested=(_git(), _GITIGNORE,
                   _file("usage", "使用说明.md", "使用说明.md"),
                   _pattern("launcher", "启动脚本（启动.bat / start.bat / run.py）",
                            ("启动.bat", "start.bat", "启动.sh", "run.py"))),
        version_scheme="archive", build_archive=False,
    ),
    "克隆仓库": Protocol(
        name="克隆仓库", label="克隆仓库",
        description="外部克隆仓库：遵循上游规范，上游版本只读展示；不要求本地骨架与合规",
        git=False, dirs=(), files={},
        tabs=("overview", "ai", "versions", "github"),
        required=(),
        suggested=(_README,),
        version_scheme="upstream", build_archive=False,
    ),
    "工具脚本": Protocol(
        name="工具脚本", label="工具脚本",
        description="松散脚本/工具集：无强制规范，随用随放",
        git=False, dirs=(), files={},
        tabs=("overview", "ai", "docs"),
        required=(),
        suggested=(_README,),
        version_scheme="none", build_archive=False,
    ),
}


def protocol_for(ptype: str) -> Protocol | None:
    return PROTOCOLS.get(ptype)


def version_scheme_for(ptype: str, override: str = "") -> str:
    """生效版本方案：项目覆盖 > 类型协议默认 > semver（自定义/未知类型沿用旧行为）。"""
    if override in VERSION_SCHEMES:
        return override
    proto = PROTOCOLS.get(ptype)
    return proto.version_scheme if proto else "semver"


def build_archive_for(ptype: str) -> bool:
    """根目录 dist/installer/build 是否按「未归档构建」处理。"""
    proto = PROTOCOLS.get(ptype)
    return proto.build_archive if proto else True


def required_items(ptype: str) -> list[dict]:
    """合规必需项：内置协议直读；自定义类型沿用宽松回退（README + git 类）。"""
    proto = PROTOCOLS.get(ptype)
    if proto is not None:
        return list(proto.required)
    return [_README]


def suggested_items(ptype: str) -> list[dict]:
    proto = PROTOCOLS.get(ptype)
    if proto is not None:
        return list(proto.suggested)
    return []
