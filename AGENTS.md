# AGENTS.md — ProjectDock 项目坞

本地项目文件管理器：iOS 风格 UI、Python 后端、丝滑弹簧动画。

## 运行与测试
- 安装依赖：python -m pip install -r requirements-dev.txt
- 运行应用：python -m projectdock（默认打开 pywebview 窗口）
- 仅启动后端：python -m projectdock --no-webview --debug
- 测试：python -m pytest（覆盖率门槛 80%，--cov-fail-under=80）

## 代码结构
- src/projectdock/ — Python 后端（FastAPI）
  - api.py 路由；state.py 全局状态；db.py SQLite 注册表；scanner.py 文件扫描
  - presets.py 一键初始化模板与自定义类型；versioning.py 版本解析；runner.py 子进程流式任务；builder.py 构建脚本
  - agent.py AI 命令模板（claude/pi）；backup.py 任务前备份；github.py 自动建仓；release.py 发布向导
- web/ — iOS 风格前端（原生 HTML/CSS/JS，无构建步骤）
  - js/spring.js 弹簧动画库；js/app.js 应用逻辑
- tests/ — pytest 单元测试，必须离线、可重复

## 版本与提交规范
- 版本号唯一来源：根目录 VERSION 文件；发布前更新 CHANGELOG.md
- 提交前缀：feat: / fix: / release: / build: / chore: / docs: / refactor: / test:
- 构建产物进 versions/vX.Y.Z/dist/，仅本地保留；dist/、versions/ 不入库
- 单 main 分支直接开发与发布；不主动 push，推送需用户明确要求

## UI 规范
- 参考 apple-design：反馈即时（按下即响应）、动画可打断、弹簧不硬切
- 主题变量在 web/css/style.css 的 CSS 变量中，支持 light / dark / system
- 尊重 prefers-reduced-motion，减少动画时退化为淡入淡出
