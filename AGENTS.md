# AGENTS.md — 项目契约（由 ProjectDock 生成）

ProjectDock 项目坞：本地项目文件管理器：iOS 风格 UI、Python 后端、丝滑弹簧动画，内置 AI 开发闭环（契约/日志/版本迭代）。本项目由 ProjectDock 管理，以下是必须遵守的规范。

## 项目结构
- 类型：软件（Python 软件项目）
- 目录结构约定：src、tests
- 骨架文件约定：README.md、VERSION、CHANGELOG.md、requirements.txt、.gitignore、AGENTS.md

## 版本管理（强制）
- 版本号唯一来源：根目录 `VERSION` 文件（纯数字 semver，如 0.1.0）；禁止在源码/spec/安装器里手写第二份版本号
- 每次变更同步更新 `CHANGELOG.md` 更新日志（## [版本] - 日期 + ### Added/Fixed/Changed 分组）
- 构建产物归档到 `versions/vX.Y.Z/dist/`（仅本地、不上传、只增不删、不覆盖旧产物）
- 语义化版本：Bug 修复=PATCH、新功能/UI=MINOR、不兼容大改=MAJOR

## Git 规范
- 单 main 分支直接开发与发布，不建 develop/feature 分支
- 提交前缀：feat: / fix: / release: / build: / chore: / docs: / refactor: / test:
- 提交前用 git status + git diff --stat 复核改动范围，不提交无关文件
- **不主动 push**；推送 GitHub 由用户明确要求后进行，推送前复核内容
- versions/ 与 dist/ 只增不删、仅本地保留、不上传

## 任务流程（强制）
1. 大功能先调研 → 与用户 grill 确认方案 → update_plan 拆解 → 逐步实现 → 交付报告
2. 重要修改先与用户商讨，不一键直达
3. 任务执行前先做安全备份（快照进 versions/backups/）
4. 每轮迭代结束交付报告：改动清单 / 构建产物路径 / 测试建议

## AI 操作日志（强制）
- 每个任务完成后必须主动写 AI 操作日志到 `logs/ai/`（JSON），位置与格式见下；**不写日志视为未完成任务**
- 要素：ts / agent / action / result / summary / details / git / backup
- 快捷方式：`python -m projectdock.cli log <项目名> --agent <你的名字> --action "..." --result done --summary "..."`

## 与 ProjectDock 对接
- 查看契约与当前状态：`python -m projectdock.cli context <项目名>`
- 查看 AI 操作日志：`python -m projectdock.cli logs <项目名>`
- 若上述命令不可用：按本契约手动维护文件，并把日志 JSON 写到 logs/ai/ 即可

## 禁止事项
- 不删除 versions/、dist/ 内容；不覆盖旧构建产物（同版本重建先带时间戳归档旧 exe）
- 不把私有配置（config.json / *.env / API Key）提交入库
- 不离开当前项目目录做无关操作

## 项目特有信息（ProjectDock 自维护）
## 项目结构
- 类型：软件（Python 软件项目）
- 目录结构约定：src、tests
- 骨架文件约定：README.md、VERSION、CHANGELOG.md、requirements.txt、.gitignore、AGENTS.md

## 版本管理（强制）
- 版本号唯一来源：根目录 `VERSION` 文件（纯数字 semver，如 0.1.0）；禁止在源码/spec/安装器里手写第二份版本号
- 每次变更同步更新 `CHANGELOG.md` 更新日志（## [版本] - 日期 + ### Added/Fixed/Changed 分组）
- 构建产物归档到 `versions/vX.Y.Z/dist/`（仅本地、不上传、只增不删、不覆盖旧产物）
- 语义化版本：Bug 修复=PATCH、新功能/UI=MINOR、不兼容大改=MAJOR

## Git 规范
- 单 main 分支直接开发与发布，不建 develop/feature 分支
- 提交前缀：feat: / fix: / release: / build: / chore: / docs: / refactor: / test:
- 提交前用 git status + git diff --stat 复核改动范围，不提交无关文件
- **不主动 push**；推送 GitHub 由用户明确要求后进行，推送前复核内容
- versions/ 与 dist/ 只增不删、仅本地保留、不上传

## 任务流程（强制）
1. 大功能先调研 → 与用户 grill 确认方案 → update_plan 拆解 → 逐步实现 → 交付报告
2. 重要修改先与用户商讨，不一键直达
3. 任务执行前先做安全备份（快照进 versions/backups/）
4. 每轮迭代结束交付报告：改动清单 / 构建产物路径 / 测试建议

## AI 操作日志（强制）
- 每个任务完成后必须主动写 AI 操作日志到 `logs/ai/`（JSON），位置与格式见下；**不写日志视为未完成任务**
- 要素：ts / agent / action / result / summary / details / git / backup
- 快捷方式：`python -m projectdock.cli log <项目名> --agent <你的名字> --action "..." --result done --summary "..."`

## 与 ProjectDock 对接
- 查看契约与当前状态：`python -m projectdock.cli context <项目名>`
- 查看 AI 操作日志：`python -m projectdock.cli logs <项目名>`
- 若上述命令不可用：按本契约手动维护文件，并把日志 JSON 写到 logs/ai/ 即可

## 禁止事项
- 不删除 versions/、dist/ 内容；不覆盖旧构建产物（同版本重建先带时间戳归档旧 exe）
- 不把私有配置（config.json / *.env / API Key）提交入库
- 不离开当前项目目录做无关操作

## 项目特有信息（ProjectDock 自维护）
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

## UI 规范
- 参考 apple-design：反馈即时（按下即响应）、动画可打断、弹簧不硬切
- 主题变量在 web/css/style.css 的 CSS 变量中，支持 light / dark / system
- 尊重 prefers-reduced-motion，减少动画时退化为淡入淡出
