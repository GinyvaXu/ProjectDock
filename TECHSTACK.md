# 技术栈 — ProjectDock

## 概览
| 维度 | 内容 |
|------|------|
| 语言/运行时 | Python 3.12（Windows） |
| 主要框架 | FastAPI + uvicorn（后端）+ pywebview（桌面壳） |
| 数据存储 | SQLite（注册表/设置，%APPDATA%/ProjectDock）+ 文件系统（项目文件） |
| 前端 | 原生 HTML/CSS/JS 单页（由 FastAPI 静态托管） |
| 构建与打包 | PyInstaller（便携/Debug）+ Inno Setup（安装包） |
| 测试 | pytest + coverage（≥80% 门槛） |

## 核心功能实现
### 项目扫描与统一管理
- **实现逻辑**：扫描管理根目录下 `项目NN-类型-名称` 命名文件夹，与 SQLite 注册表合并元数据（描述/置顶/排除），支持导入外部文件夹；首页支持图格/列表切换与置顶分组排序。
- **技术手段**：scanner 正则解析目录名 + db 增量 upsert（同路径冲突自动清理旧注册）；类型化模板（presets）按类型差异化生成目录结构与 Tab 菜单。
### 版本迭代与构建归档
- **实现逻辑**：版本号唯一来源 VERSION 文件；发版走 VERSION → CHANGELOG → git tag → GitHub Release 流程；构建产物（便携/Debug/安装包）归档到 versions/vX.Y.Z/dist/，绝不覆盖旧产物。
- **技术手段**：versioning/release/builder 模块 + `projectdock-cli archive`；git 分支模型（main/develop）+ GitHub CLI（gh）或 REST 注入令牌（不落盘）。
### 内置 AI Agent 协作
- **实现逻辑**：向 pi / Claude Code 下发自然语言指令，注入系统提示词（项目契约 + 确认策略 + 技术栈规范），以非交互模式在当前项目目录执行；操作日志独立归档（AILog），总控台可切换项目会话与全屏对话。
- **技术手段**：subprocess 调用 CLI（Windows 下解析 .cmd/.ps1 包装命令）+ `--append-system-prompt`；确认策略（push/delete/release/archive 等）要求用户手动确认；会话历史裁剪防上下文爆炸。
### GitHub 远程仓库管理
- **实现逻辑**：项目菜单内嵌 GitHub 面板——登录（PAT 或 gh CLI）、查看仓库/README/提交/Release、创建仓库与推送，内嵌浏览器浏览远程页面。
- **技术手段**：ghrepo 走 GitHub REST API（urllib + base64 解码 README，Markdown 渲染在 UI 完成）+ gh CLI 兜底；token 优先级 PAT > gh 登录态。
### 合规检查与自动修正
- **实现逻辑**：逐项检查项目必备文件（VERSION/CHANGELOG/TECHSTACK.md/.gitignore/git 仓库等），缺失项一键生成；扫描 dist/ 等未归档产物并提示归档。
- **技术手段**：compliance 清单驱动 + 幂等修复（已存在不覆盖）；与 versioning 联动自动按当前版本归档。
### 技术栈文档（TECHSTACK.md）
- **实现逻辑**：软件项目展示「技术栈」Tab：解析项目根目录 TECHSTACK.md 的概览表格与核心功能小节，卡片式渲染；支持在线编辑、模板生成与「AI 撰写」一键下发。
- **技术手段**：techstack 模块纯文本解析（无需第三方 Markdown 库）；新软件项目预设自动生成模板；AI 撰写通过内置 Agent 通道执行并回写。
### 自动更新
- **实现逻辑**：启动后检查 GitHub Releases，发现新版本下载安装包并引导安装；构建 release 成功后自动激活更新链路。
- **技术手段**：update 模块 + GitHub API/镜像源竞速；安装包由 Inno Setup 产出，支持覆盖安装。
### 备份与图标
- **实现逻辑**：归档前自动备份，删除类操作可恢复；每个项目自动生成 iOS 风格图标（圆角方块 + 类型渐变 + 几何符号），可一键重生成或选取自定义图标。
- **技术手段**：backup 模块（归档副本策略）；iconmaker 纯标准库绘制（无 PIL 依赖），2 倍分辨率绘制后降采样抗锯齿。
