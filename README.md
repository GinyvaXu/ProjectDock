# ProjectDock 项目坞

本地项目文件管理器：把所有项目文件夹收进一个清爽的 iOS 风格界面，统一创建、初始化、管理，并内置 AI 项目助手。

## 功能总览

1. **自由创建项目文件夹**：支持 软件 / 网站 / 游戏 / PPT / 文稿 / 脚本 / 其他 类型，自动按 项目NN-类型-名称 命名。
2. **统一管理**：SQLite 索引 + 文件系统扫描双轨，搜索、类型筛选、导入已有文件夹、打开目录。
3. **预设一键初始化**：按类型生成项目骨架（README / VERSION / CHANGELOG / .gitignore / AGENTS.md 等）+ git init + 首次提交。
4. **AI 项目助手**：内置聊天面板，claude / pi 可切换，自然语言下指令，流式输出回显到界面。
5. **版本与构建展示**：软件类项目直接呈现版本迭代（VERSION / CHANGELOG）、构建产物（versions/ / dist/）、更新内容，支持一键调用项目构建脚本。

## 技术栈

- Python 3.12 + FastAPI + Uvicorn（后端 API）
- pywebview（原生窗口容器，Windows 使用 Edge WebView2）
- 原生 HTML/CSS/JS 前端（零构建步骤），弹簧动画引擎 web/js/spring.js
- SQLite（%APPDATA%/ProjectDock/data.db）存项目注册表与设置

## 目录结构

```text
项目14-软件-ProjectDock/
├── src/projectdock/        # Python 后端
│   ├── api.py              # FastAPI 路由
│   ├── state.py            # 全局状态（设置/数据库/根目录/任务注册表）
│   ├── db.py               # SQLite 注册表
│   ├── scanner.py          # 文件系统扫描与命名
│   ├── presets.py          # 一键初始化预设
│   ├── versioning.py       # 版本/更新日志/构建产物解析
│   ├── runner.py           # 子进程流式任务（agent 与构建共用）
│   ├── builder.py          # 构建脚本发现与执行
│   └── main.py             # 启动入口（uvicorn + pywebview）
├── web/                    # iOS 风格前端
│   ├── index.html
│   ├── css/style.css
│   └── js/{spring.js, api.js, app.js}
├── tests/                  # pytest 单元测试（覆盖率门槛 80%）
├── build_debug.py          # PyInstaller debug/console 构建
├── build_exe.py            # PyInstaller release/windowed 构建
├── build_utils.py          # 版本读取与旧版归档
├── .agents/skills/projectdock/  # 项目级开发规范
├── VERSION                 # 版本号唯一来源
└── CHANGELOG.md            # 更新日志
```

## 快速开始

```bash
python -m pip install -r requirements-dev.txt
python -m projectdock            # 打开 App 窗口（pywebview）
python -m projectdock --no-webview --debug   # 仅启动后端，浏览器访问 http://127.0.0.1:8765
```

管理根目录可在设置中修改；首次运行默认指向检测到的“资料库”目录。

## 构建方式

- `python build_debug.py`：PyInstaller console（debug）版，产物进 versions/vX.Y.Z/dist/
- `python build_exe.py`：PyInstaller windowed（release）版
- 发布前门禁：全量测试 + 覆盖率 >= 80% + 构建 + 冒烟

## 路线图

- v0.2：模板编辑器（自定义预设）、GitHub Releases 拉取与发布向导
- v0.3：项目依赖图、批量操作、全局快捷键与托盘

## 致谢

设计灵感与工程规范来自：apple-design、python-project-release、project-git-mgmt、software-project-init、emil-design-eng 等 skills。
