---
name: projectdock-dev
description: ProjectDock 项目坞的开发规范。当用户要求对 ProjectDock（本地项目文件管理器，FastAPI + pywebview + iOS 风格 Web UI）进行功能迭代、Bug 修复、UI 改进、构建 exe、发布新版本时使用。不要用于 Godot、PPT 或其他非 ProjectDock 任务。
---

# ProjectDock 开发规范

## 架构
- 后端：FastAPI（src/projectdock/api.py），无状态、通过 AppState 注入依赖
- 管理协议：protocols.py 注册表（12 个内置类型：骨架/合规/菜单/版本方案/归档规则一处定义）；新增类型在此登记；见 docs/管理协议.md
- 命名规范风格：naming.py 注册表（classic / local / free / auto），scanner 兼容严格风格；新建/重命名按设置 naming_style；规范见 docs/命名规范.md
- 版本方案：versioning.py 支持 semver / archive / upstream / none（按类型默认，项目可覆盖，DB projects.version_scheme）
- AI 与发布：agent.py（claude/pi 全自动 + 备份 + 任务报告）、github.py（自动建仓）、release.py（发布向导）
- 前端：原生 HTML/CSS/JS（web/），弹簧动画在 web/js/spring.js，禁止引入构建步骤
- 数据：SQLite（%APPDATA%/ProjectDock/data.db）+ 文件系统扫描；根目录可配置

## 新增功能流程
1. 后端先加 API + 单元测试（pytest，覆盖率门槛 80%）
2. 前端接入：先想动画（参考 apple-design：即时反馈、可打断、弹簧）
3. 冒烟：python -m projectdock --no-webview --debug 后 curl 验证
4. 更新 CHANGELOG.md 与 VERSION

## 构建与发布
- build_debug.py：PyInstaller console 版，产物进 versions/vX.Y.Z/dist/
- build_exe.py：PyInstaller windowed 版
- 发布前：全量测试 → 覆盖率 → 构建 → 冒烟 → 归档 → 两次提交（release:/build:）
- VERSION 是版本号唯一来源，禁止在代码里硬编码版本号
- 本地迭代（用户已授权自动执行）：构建后运行 `reinstall_local.ps1`（卸载旧版 → 安装最新 Setup → 健康检查），无需再次确认

## 常见坑
- Windows 中文路径：一律用 Python pathlib / PowerShell -LiteralPath
- 子进程（agent/构建）用 creationflags=CREATE_NO_WINDOW，输出按行流式回传
- Windows 下 npm 包装命令（pi.cmd / pi.ps1）不能直接被 create_subprocess_exec 执行，需经 agent.resolve_command 包装为 cmd /c
- 不主动 push GitHub；推送前先 git status + git diff --stat 复核
