# ProjectDock 项目状态

- 版本：0.4.0（自动更新 + Setup 安装包）
- 状态：✅ v0.1 核心功能 + v0.2 阶段 1/2/3 + 自动更新
- GitHub：https://github.com/GinyvaXu/ProjectDock（私有，main 分支）

## v0.1.0 完成项
1. 项目创建与管理（内置 7 类型 + 自定义类型，自动命名 项目NN-类型-名称，SQLite 索引 + 扫描）
2. 预设一键初始化（骨架文件 + git init + 首次提交 + 可选自动创建 GitHub 仓库）
3. 版本与构建展示（读取本地约定文件 VERSION / CHANGELOG / versions/ / dist/，一键构建入口）
4. 发布向导（版本号 → 更新日志 → 构建脚本 → git tag → 提交，构建失败自动中止并报告）
5. AI 项目助手（App 内嵌聊天，claude / pi 可切换，默认 pi；全自动执行 + 任务前备份 + 任务后操作/Git 报告）
6. iOS 风格 UI（毛玻璃 / 弹簧动画 / 深色浅色跟随系统，面板切换淡入动画）；修复 hidden 与 display:flex 冲突导致的界面被遮罩锁定（空状态层/模态遮罩不再拦截交互）
7. 概览页 Git 状态面板（最新提交 / 工作区变更 / 一键刷新）、搜索空状态区分、发布向导版本快速递增
7.1 项目 Logo 展示（真实图片优先 + 类型渐变 emoji 兜底，卡片/抽屉双处显示）
7.2 版本产物次级菜单（版本目录「打开文件夹/位置」，产物「打开/位置/复制」）
7.3 概览页「项目文档」面板（README + 计划书/企划书/方案/设计/需求/说明书，支持打开/定位）
7.4 最新构建视图（跨版本目录 + 根 dist 按修改时间合并，未归档构建标记 + 一键去合规归档）
7.5 项目合规化 Tab（类型标准展示 / 逐项检查 / 一键修复：创建缺失标准文件、git init、归档根 dist；移动类动作需显式确认，不删除任何文件；项目卡片与概览显示合规状态）
7.6 修复：VERSION 文件带 UTF-8 BOM 时版本号读取异常
7.7 AI 开发闭环地基（v0.2 阶段 1）：项目契约 AGENTS.md（按类型渲染）+ 动态上下文；AI 操作日志 logs/ai/（CLI/API 双入口）；projectdock-cli（contract/context/status/log/logs）；合规新增契约动作；设计文档 02_AI开发闭环设计.md；ProjectDock 自身 AGENTS.md 已契约化（dogfood）
8. 测试与质量门禁：89 个用例通过，覆盖率 84.48%（门槛 80%）
9. 构建脚本：build_debug.py / build_exe.py（PyInstaller → versions/vX.Y.Z/dist/），debug/release 均已构建验证，windowed 版崩溃已修复（devnull + crash.log）
10. GitHub：私有仓库已推送（main 分支），新项目可一键自动建仓

## 逻辑链路审查与修复（R3）
1. 数据层：upsert 冲突处理（重命名/移动/换根目录）、移除管理不再复活
2. 安全：项目名消毒（Windows 非法字符、路径穿越）
3. GitHub：无预设勾选建仓时自动 git init + 提交
4. 任务链路：agent 启动失败也出报告、任务队列自动清理
5. 性能：备份 os.walk 剪枝、未注册项目类型推断
6. 默认值对齐：AI 后端统一回落 pi

## v0.2.0 完成项（阶段 2）
1. 主页总控台：跨项目 AI 操作时间线 / 运行中任务 / 项目合规与版本状态 / 失败计数
2. 批量下指令：多项目勾选统一向 AI agent 下达，逐项目任务 + 自动 AI 日志
3. 项目「AI 日志」菜单：操作时间线只读展示（agent/时间/动作/结果/详情/备份/Git），与「AI 管理」对话分离
4. 类型菜单模板：设置面板逐类型勾选菜单（可持久化覆盖）；文稿类默认「文稿版本」分组（Word/PDF/PPT/表格/Markdown/文本，按时间倒序）
5. 新端点：/api/console、/api/jobs、/api/agent/batch、documents?scope=all、/api/types tabs
6. 测试：99 个用例通过，覆盖率 85.00%（门槛 80%）

## v0.3.0 完成项（阶段 3）
1. projectdock-cli 工具级扩展：init / build / release / archive（含自动 AI 日志）
2. 确认策略：设置面板勾选需确认操作（push/删除/建仓/Release/归档），CLI 未带 --confirm 拒绝执行
3. 契约与 agent 提示词注入确认策略；Settings/API 持久化 confirm_policy
4. 测试：111 个用例通过，覆盖率 85.36%（门槛 80%）

## v0.4.0 完成项（自动更新）
1. 自动更新链路：GitHub Releases 检查（gh/API）→ Setup 下载 → 静默安装（Inno Setup）
2. 设置面板「软件更新」UI + 启动自动检查提示；更新仓库可配置
3. build_setup.py 构建 Setup 安装包（%LOCALAPPDATA%/Programs/ProjectDock，无需管理员）
4. 测试：126 个用例通过，覆盖率 85.30%（门槛 80%）

## 待办（后续）
- GitHub Releases 拉取（下载/展示历史版本）、模板导入/导出、多根目录、托盘、全局快捷键
- 自动更新（检查 GitHub 新版本 → 下载 → 安装）
- 多根目录、托盘、全局快捷键
