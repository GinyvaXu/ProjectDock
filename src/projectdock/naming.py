"""命名规范风格（naming styles）：项目文件夹命名规则的可插拔注册表。

设计目标（为「命名规范风格快速切换」新版本功能做准备）：
- 把「项目文件夹怎么命名」收敛为可注册的 NamedStyle：新增风格只需在此注册一个类；
- 扫描 / 导入：始终兼容全部已注册风格 —— 切换风格不会丢项目；
- 新建 / 重命名：按当前风格设置（settings.naming_style；auto = 按资料库现有项目自动识别）。

内置风格：
- classic：``项目NN-类型-名称``（ProjectDock 默认，如 ``项目14-软件-ProjectDock``）
- local  ：``ProjectN-名称`` / ``ProjectN.M-名称``（AIAgentBase 本机资料库，
           名称不含类型；类型只存储在 ProjectDock 注册表中）

规范文档见 ``docs/命名规范.md``。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

STYLE_AUTO = "auto"
DEFAULT_STYLE = "classic"

INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_title(title: str) -> str:
    """清理项目名：替换 Windows 非法字符、防路径穿越（..）、去首尾空白/点。"""
    title = INVALID_CHARS.sub("-", title or "")
    title = re.sub(r"\.\.+", "-", title)
    title = re.sub(r"\s+", " ", title).strip(" .-")
    return title or "未命名项目"


@dataclass(frozen=True)
class ParsedProject:
    """一次成功的文件夹名解析结果。"""

    style: str      # 命中的风格 id
    index: int      # 主序号（供「下一个编号」计算）
    index_raw: str  # 原始序号文本（local 可能是 "2.1"；重命名时原样保留）
    ptype: str      # 类型；无类型风格为空串（类型以注册表为准）
    title: str      # 展示标题


class NamingStyle:
    """一种项目文件夹命名风格。子类实现 parse / make。"""

    id: str = ""
    label: str = ""
    description: str = ""
    example: str = ""

    def parse(self, name: str) -> ParsedProject | None:  # pragma: no cover - 接口
        raise NotImplementedError

    def make(self, index_raw: str, ptype: str, title: str) -> str:  # pragma: no cover - 接口
        raise NotImplementedError

    def as_dict(self) -> dict:
        return {"id": self.id, "label": self.label,
                "description": self.description, "example": self.example}


class ClassicStyle(NamingStyle):
    """ProjectDock 默认：``项目NN-类型-名称``。"""

    id = "classic"
    label = "经典三段式"
    description = "项目 + 序号 + 类型 + 名称；类型直接体现在文件夹名上"
    example = "项目14-软件-ProjectDock"

    _re = re.compile(r"^项目(\d+)-(.*)$")

    def parse(self, name: str) -> ParsedProject | None:
        m = self._re.match(name)
        if not m:
            return None
        index_raw, rest = m.group(1), m.group(2)
        if not rest:
            return None
        if "-" not in rest:
            return ParsedProject(self.id, int(index_raw), index_raw, rest, rest)
        ptype, _, title = rest.partition("-")
        return ParsedProject(self.id, int(index_raw), index_raw, ptype, title or rest)

    def make(self, index_raw: str, ptype: str, title: str) -> str:
        return f"项目{index_raw}-{ptype}-{title}"


class LocalStyle(NamingStyle):
    """AIAgentBase 本机资料库：``ProjectN-名称``，子项目 ``ProjectN.M-名称``。"""

    id = "local"
    label = "本机两段式"
    description = "Project + 序号 + 名称；子项目用小数点编号（Project2.1-xxx）；类型存注册表"
    example = "Project2.1-洛琪希美图分类"

    _re = re.compile(r"^project(\d+(?:\.\d+)?)-(.*)$", re.IGNORECASE)

    def parse(self, name: str) -> ParsedProject | None:
        m = self._re.match(name)
        if not m:
            return None
        index_raw = m.group(1)
        title = m.group(2).strip()
        if not title:
            return None
        return ParsedProject(self.id, int(index_raw.split(".")[0]), index_raw, "", title)

    def make(self, index_raw: str, ptype: str, title: str) -> str:
        return f"Project{index_raw}-{title}"


# 注册表：新增命名规范风格 = 在此注册一个 NamingStyle 子类实例。
STYLES: dict[str, NamingStyle] = {s.id: s for s in (ClassicStyle(), LocalStyle())}


def style_ids() -> list[str]:
    return list(STYLES)


def get_style(style_id: str | None) -> NamingStyle | None:
    return STYLES.get((style_id or "").strip().lower())


def parse_name(name: str) -> ParsedProject | None:
    """按注册顺序尝试全部风格（扫描/导入始终兼容所有风格）。"""
    for style in STYLES.values():
        parsed = style.parse(name)
        if parsed:
            return parsed
    return None


def detect_style(root: Path) -> str:
    """按资料库现有项目文件夹识别风格；命中数最多者胜，无命中时用默认风格。"""
    counts = {sid: 0 for sid in STYLES}
    root = Path(root)
    try:
        children = list(root.iterdir())
    except OSError:
        return DEFAULT_STYLE
    for child in children:
        if not child.is_dir():
            continue
        for sid, style in STYLES.items():
            if style.parse(child.name):
                counts[sid] += 1
                break
    best = max(counts, key=lambda k: counts[k])
    return best if counts[best] > 0 else DEFAULT_STYLE


def resolve_style(root: Path, style_id: str | None = None) -> str:
    """解析风格设置：auto / 空 / 未知 → 按资料库自动识别。返回已注册的风格 id。"""
    sid = (style_id or "").strip().lower()
    if sid in STYLES:
        return sid
    return detect_style(root)


def next_index(root: Path, style_id: str | None = None) -> int:
    """下一个可用主序号：同风格现有项目的最大主序号 + 1。"""
    sid = resolve_style(root, style_id)
    best = 0
    root = Path(root)
    try:
        children = list(root.iterdir())
    except OSError:
        return 1
    for child in children:
        if not child.is_dir():
            continue
        parsed = STYLES[sid].parse(child.name)
        if parsed:
            best = max(best, parsed.index)
    return best + 1


def make_name(style_id: str, index_raw: str | int, ptype: str, title: str) -> str:
    """按指定风格组装文件夹名（不含路径，title 需已消毒）。"""
    style = STYLES.get(style_id) or STYLES[DEFAULT_STYLE]
    return style.make(str(index_raw), ptype, title)


def make_folder_name(root: Path, ptype: str, title: str, style_id: str | None = None) -> str:
    """按当前风格生成「下一个编号」的项目文件夹名。"""
    sid = resolve_style(root, style_id)
    return make_name(sid, next_index(root, sid), ptype, sanitize_title(title))
