---
name: projectdock-dev
description: ProjectDock 项目坞的开发规范。当用户要求对 ProjectDock（本地项目文件管理器，FastAPI + pywebview + iOS 风格 Web UI）进行功能迭代、Bug 修复、UI 改进、构建 exe、发布新版本时使用。不要用于 Godot、PPT 或其他非 ProjectDock 任务。
---

# ProjectDock 开发规范

## 架构
- 后端：FastAPI（src/projectdock/api.py），无状态、通过 AppState 注入依赖
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

## 常见坑
- Windows 中文路径：一律用 Python pathlib / PowerShell -LiteralPath
- 子进程（agent/构建）用 creationflags=CREATE_NO_WINDOW，输出按行流式回传
- 不主动 push GitHub；推送前先 git status + git diff --stat 复核
