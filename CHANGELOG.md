# 更新日志

本文件记录 ProjectDock 的版本迭代。格式：语义化版本 + 日期 + 变更分组。


## [1.4.0] - 2026-09-27
### Added（命名规范风格系统 + 本机资料库本土化）
- 新增命名规范风格注册表 `naming.py`：`classic`（项目NN-类型-名称）/ `local`（ProjectN-名称、ProjectN.M-名称，类型存注册表）/ `auto`（按资料库现有项目自动识别，默认）——为后续「命名规范风格一键切换」新版本功能打底
- 扫描/导入始终兼容全部已注册风格（切换风格不丢项目）；新建/重命名按当前风格执行，重命名保留原序号（含 `Project2.1-…` 子序号）
- 设置新增 `naming_style`（settings.json / API `PUT /api/settings` / CLI `init --style`）；新增只读接口 `GET /api/naming/styles`（风格清单 + 当前值 + 自动识别结果，供未来切换界面消费）
- CLI：`init` 支持 `--style auto|classic|local`；无类型风格项目的 `context/status/techstack` 类型读取注册表
- 文档：新增 `docs/命名规范.md`（AIAgentBase 本机命名规范总结 + 版本归档硬性要求 + 风格切换/扩展方法）；README/03_管理逻辑报告/AGENTS.md 同步
- 修复：`gh auth status` / `git remote` / `gh repo create` 输出未指定编码，GBK 环境下读取报错；统一按 UTF-8 解码
- 默认根目录探测改为兼容全部命名风格（含 `ProjectN-名称`）
- 测试：新增 tests/test_naming.py（18 用例：解析/识别/创建/优先级/API/CLI）；全量 178 个通过，覆盖率 83.65%（门槛 80%）

## [1.3.1] - 2026-08-15
### Added
- 技术栈文档（TECHSTACK.md）：软件项目新增「技术栈」Tab，解析项目根目录 TECHSTACK.md 的概览表格与核心功能小节（实现逻辑/技术手段）卡片展示，支持在线编辑、模板生成与「AI 撰写」一键下发
- 新软件项目预设自动生成 TECHSTACK.md 模板；合规检查新增必需项与 create_techstack 一键修复；CLI 新增 techstack 子命令（--init/--force）
- 内置 agent 教学：系统提示词与项目契约新增 TECHSTACK.md 撰写规范（通读源码→归纳概览+核心功能，只写真实内容）；软件类快捷指令新增「撰写/更新技术栈」
- 已为本地 7 个真实软件项目现场撰写 TECHSTACK.md（番茄钟/浮窗工具/座位表排列/webp转pdf/AgentFloat/GinyScreen/ProjectDock）
- 测试 160 个通过，覆盖率 83.32%（门槛 80%）
## [1.3.0] - 2026-08-13
### Fixed（修复安装包图标未生效）
- 根因：build_setup.py 重新构建 release exe 时未传 `--icon`，Setup 安装包内的 exe 一直使用 PyInstaller 默认图标；已补全 `--icon`，安装后程序/快捷方式图标为新「版本卡片」
### Added（总控台 AI 对话 + grill 选择 + 批量实时进度 + 全屏对话）
- 总控台新增「AI 助手对话」卡片：项目下拉切换任意项目的 agent 对话、agent 后端切换、清空记录；每项目独立会话历史，切换项目不串消息
- Agent grill 决策 UI：agent 需要用户拍板时在回复末尾输出 ```pdchoice``` JSON 卡片，前端渲染为可点击选项按钮，点击后自动把选择结果发回 agent 继续任务
- 会话历史上下文：`/api/agent/run` 支持 history，自动携带最近 12 轮对话作为前情提要，多轮追问/确认可延续
- 批量下指令实时进度：逐项目显示运行状态条 + 可展开的流式输出，像 AI 管理菜单一样实时回显
- 对话窗口全屏（软件内）：抽屉右上角 ⤢ 全屏按钮展开整个抽屉；总控台对话卡片 ⤢ 全屏占据主工作区，侧栏/工具栏自动隐藏
- 测试 151 个通过，覆盖率 83.45%（门槛 80%）
### 安装包
- ProjectDock_Setup_v1.3.0.exe（本 Release 资产，自动更新将下载此安装包）

## [1.2.0] - 2026-08-13
### Added（新图标 + GitHub README 正确渲染 + AI 输入坞/分类预设 + 首页视图排序）
- 全新极简图标：以「版本卡片」为创意（靛紫渐变 + 三张错位卡片叠放，左上微调构图），替换 exe/Setup/侧栏 logo 全套图标资源
- GitHub README 渲染修复：支持表格、有序/无序列表、引用块、徽章链接、行内/相对图片（自动修正为 raw.githubusercontent 绝对地址）、内嵌 HTML（白名单标签/属性过滤防 XSS）；默认分支跟随仓库实际 default_branch
- AI 输入坞修复：输入栏悬浮于面板下 1/3 的毛玻璃浮层（此前贴底），消息区独立滚动
- AI 快捷指令改分类折叠：软件/网站/游戏/脚本/PPT/文稿/其他按类型提供分组指令（Git 与版本 / 构建与发布 / 文档 / 质量 / AI 协作等），首组默认展开，点击填入
- 首页项目展示：图格/列表视图切换、排序方式（置顶优先/最近更新/创建时间/名称/类型）、置顶项目与其余分区显示（「📌 置顶」「全部项目」），偏好本地持久化
- 测试 149 个通过，覆盖率 83.32%（门槛 80%）；headless Chrome E2E 19/19、0 JS 错误
### 安装包
- ProjectDock_Setup_v1.2.0.exe（本 Release 资产，自动更新将下载此安装包）

## [1.1.0] - 2026-08-13
### Added（GitHub 仓库管理 + 项目信息编辑 + AI 菜单升级 + 日志增强）
- 项目 GitHub 远程仓库管理：设置内可登录 GitHub（优先 gh 命令行登录态，或粘贴 PAT 令牌）；软件/网站等类型新增「GitHub 仓库」Tab，内嵌查看远程仓库信息、README（自动渲染并修正相对图片）、最近提交、发行版，支持一键创建仓库并推送、手动设置 origin、在浏览器打开仓库
- 项目信息编辑：概览页新增「编辑信息」，可随时修改项目名称（自动重命名文件夹并保留编号前缀）、类型、描述；置顶/图标状态保留
- AI 管理菜单升级：输入栏改为悬浮于面板下 1/3 位置的毛玻璃输入坞，下方提供 10 种软件类快捷指令 / 5 种文稿类指令（点击填入输入框）
- AI 日志增强：日志条目显示来源（应用内/外部 Agent）、备份、Git 变更明细（HEAD/分支/变更数），详情可展开；总控台活动列表每条带项目名标签（点击直达项目）
- 测试 149 个通过，覆盖率 83.36%（门槛 80%）；headless Chrome E2E 9/9
### 安装包
- ProjectDock_Setup_v1.1.0.exe（本 Release 资产，自动更新将下载此安装包）

## [1.0.0] - 2026-08-12
### Added（正式版：置顶 + 图标管线 + 全量合规 + 精美 README）
- 项目置顶：卡片左上角 📌 一键置顶/取消，置顶项目排序优先并高亮边框；概览操作行同步支持，状态持久化到本地库
- 图标生成管线：新增 `iconmaker`（纯标准库），按类型渐变配色 + 12 种几何符号一键生成 iOS 风图标；也支持上传自定义 PNG/JPEG/WebP/GIF（≤8MB）；生成默认 256px（约 1 秒），前端增加「生成中…」加载反馈
- 全量合规化：GinyVoC 等软件项目的重复构建产物仅保留归档副本，全部本地项目完成合规（README/VERSION/CHANGELOG/git init/产物归档）
- 详细美观 README：徽章头部、特性总览、安装/快速上手/AI 协作/管理规范/开发/FAQ/目录结构，配真实主界面截图
- 自动化更新链路就绪：GitHub Releases 检查 → Setup 下载 → 静默安装，随 v1.0.0 正式版首次全链路激活
### Quality
- 测试 140 个通过，覆盖率 86.80%（门槛 80%）
- headless Chrome E2E：置顶/图标/版本折叠/抽屉 14 项全过，0 JS 错误
### 安装包
- ProjectDock_Setup_v1.0.0.exe（本 Release 资产，自动更新将下载此安装包）

## [0.5.1] - 2026-08-12
### Fixed（并发 500 + AI 不执行任务 + 版本读取失败 + 切换串数据）
- 修复 SQLite 并发访问：多请求同时访问共享连接导致随机 sqlite3.InterfaceError（首次打开项目「版本信息读取失败」、GinyVoC/ProjectDock 版本构建读不出产物的根因）；db.py 全部操作加全局锁串行化
- 修复 AI agent 只介绍项目不执行任务：ProjectDock 管理上下文改经 --append-system-prompt 注入系统提示词（临时文件），消息体只留用户任务 + 「直接执行」指令；pi/claude 均支持
- 版本构建 Tab 分段折叠：当前版本/更新日志/构建产物/构建脚本 4 段默认折叠（当前版本默认展开），支持逐段点击展开/折叠与「全部展开/折叠」，丝滑动画
- 版本信息加载失败前端增强：失败提示 + 「重新加载」按钮，加载中占位
- 产物列表去重：同版本 dist/ 与 installer/、根目录 installer/ 与 build/ 的同名同大小产物只列一次
- 新增报告：03_管理逻辑与AI协作报告.md 梳理项目文件夹管理与 AI 协作全链路
- 测试 137 个通过，覆盖率 85.36%（门槛 80%）

## [0.5.0] - 2026-08-12
### Added（图标 + 备份管理 + AI 对话升级 + 产物扫描归档）
- 全新 iOS 风格图标：蓝靛紫渐变圆角方块 + 玻璃高光 + Dock 托盘 + 4 枚彩色应用块；assets/icon.png（1024）/icon.ico（多尺寸）/web/logo.png，接入 debug/exe 构建、Setup 安装包与 Web favicon/侧栏
- 备份管理面板（每个项目概览页）：立即备份 / 备份列表 / 一键恢复（恢复前自动再备份）/ 删除备份；备份存 versions/backups/pd_backup_*.zip，恢复跳过 .git/versions/dist 等顶层目录并做路径穿越防护
- AI 对话 Markdown 渲染：标题/列表/代码块/链接/粗体安全渲染，原文保留；每条 AI 回复带「复制」按钮；聊天区文本可自由选中复制
- AI agent 活动状态条：实时显示「正在思考 / 正在备份 / 正在调用 CLI / 正在汇总报告」等处理中内容
- AI 任务解读系统提示词：明确「整理版本归档 ≠ 改 CHANGELOG」，只有明确要求发布才走完整发布流程，避免 agent 听不懂指令
- 构建产物扫描升级：识别根 dist/installer/build 与 versions/*/dist|installer 下的构建产物（exe/msi 等）；合规化一键归档带版本号产物（如 GinyVoC-Debug-v0.6.0.exe → versions/v0.6.0/dist/），重复文件保留原地，工具不删除任何文件
- 修复：所有 subprocess 调用补 creationflags=0x08000000，消除切换项目时弹出控制台
- 修复：切换项目竞态——抽屉序号守卫，旧项目的 versions/builds/Git/文档/AI 日志不再覆盖新项目显示
- 修复：AI 日志列表按 (mtime, name) 排序，同秒文件不再错序
- 修复：config.py APP_VERSION 与 VERSION 同步（此前硬编码导致 health 接口版本号滞后）；update/github/contract 缺失 os 导入导致更新检查 500 与 Git 状态异常
- 数据操作：本地 7 个软件项目全部合规化（补 README/VERSION/CHANGELOG/.gitignore/git init）并将散落 dist/installer/build 产物归档到 versions/vX.Y.Z/dist/
- 测试 135 个通过，覆盖率 84.88%（门槛 80%）

## [0.4.0] - 2026-08-12
### Added（自动更新 + Setup 安装包）
- 自动更新链路：检查 GitHub Releases → 下载 Setup 安装包 → 静默安装，全链路打通
- 设置面板新增「软件更新」：显示当前版本、一键检查更新、发现新版本展示更新说明并下载安装；启动时自动静默检查并提示
- 更新仓库可配置（Settings.update_repo，默认 GinyvaXu/ProjectDock）；检查用 gh CLI（私有仓库），失败回落 GitHub API
- 新端点：GET /api/update/check、POST /api/update/download、POST /api/update/install
- Setup 安装包构建：build_setup.py（PyInstaller windowed + Inno Setup 6 编译），
  安装到 %LOCALAPPDATA%/Programs/ProjectDock（无需管理员），CloseApplications=force 自动关闭旧进程，
  创建桌面/开始菜单快捷方式，安装后可选立即运行
- 测试 126 个通过，覆盖率 85.30%（门槛 80%）；GitHub Release 上传 Setup 安装包即激活更新链路
### Fixed（更新链路修复）
- gh release view 误用字面 latest 参数导致 release not found，改为不带 tag 默认取最新 Release；
  GitHub API 兜底增加 gh 令牌鉴权，私有仓库也能正常检查更新

## [0.3.0] - 2026-08-12
### Added（v0.2 阶段 3：CLI 工具链 + 确认策略）
- projectdock-cli 新增 init / build / release / archive 子命令（供外部 AI agent 对接）
- init：按内置/自定义类型预设新建项目（骨架 + git + 契约 AGENTS.md），并注册到 ProjectDock
- build：运行项目构建脚本（默认取优先级最高），--archive 构建成功后把根目录 dist/ 产物归档到 versions/vX.Y.Z/dist/
- release：一键发布（备份 → 版本 → 日志 → 测试门禁 → 构建 → git tag → push/GitHub Release），复用发布向导引擎
- archive：把根目录 dist/ 构建产物归档到版本目录（支持 --version 覆盖）
- 确认策略（Q6）：设置面板新增「确认策略」，默认 push / 删除文件 / 创建 GitHub 仓库 / 发布 Release / 归档移动产物均需用户确认；CLI 对应操作要求 --confirm，未确认拒绝执行
- 契约 AGENTS.md 新增「确认策略」章节与 CLI 工具用法；内置 agent 提示词注入确认策略
- Settings 持久化 confirm_policy；API /api/settings 支持读写
- 测试 111 个通过，覆盖率 85.36%（门槛 80%）
- Dogfood：ProjectDock 自身契约同步确认策略，本轮迭代继续走契约流程

## [0.2.0] - 2026-08-12
### Added（v0.2 阶段 2：AI 闭环 UI 化 + 类型模板 + 总控台）
- 主页总控台：跨项目聚合 AI 操作时间线 / 运行中任务 / 项目合规与版本状态 / 失败计数，卡片式 iOS 风格布局
- 批量下指令：总控台勾选多个项目，统一向 AI agent 下达指令，逐项目生成任务并自动写 AI 日志
- AI 日志时间线：每个项目独立「AI 日志」菜单，只读展示操作记录（agent/时间/动作/结果/详情/备份/Git），running 状态脉冲提示
- AI 管理与日志分离：项目抽屉三区（AI 管理对话 / AI 日志 / 概览状态），符合 agent 交互习惯
- 类型菜单模板：设置面板为每个类型勾选显示的菜单（概览/版本构建/合规/文稿版本/AI 管理/AI 日志），可持久化覆盖；文稿类型默认显示「文稿版本」分组而非版本/构建
- 文稿版本分组：按文件类型（Word/PDF/PPT/表格/Markdown/文本）分组展示，组内按修改时间倒序，跳过 versions/dist/.venv 等目录
- /api/console、/api/jobs、/api/agent/batch、/api/projects/{id}/documents?scope=all 等新端点；/api/types 返回 tabs 模板与 tab_labels
- 文档整理扫描 scan_documents() 与跨项目日志聚合 collect_activity()
- Dogfood 阶段 2：ProjectDock 自身迭代继续按契约执行（本条目即由该流程产生）
## [0.1.0] - 2026-08-12
### Added
- 项目创建与管理：支持 软件/网站/游戏/PPT/文稿/脚本/其他 类型，自动命名 项目NN-类型-名称
- 统一管理：SQLite 索引 + 文件系统扫描，支持导入已有文件夹
- 一键初始化预设：按类型生成骨架文件并 git init + 首次提交，可自动创建 GitHub 仓库并推送
- 自定义项目类型：设置面板可新增/删除类型（目录结构 / 骨架文件 / 是否 git）
- AI 项目助手：App 内嵌聊天面板，可切换 claude / pi 后端（默认 pi），流式输出回显；全自动执行 + 任务前自动备份 + 任务后操作/Git 报告
- 版本与构建展示：解析本地约定文件 VERSION / CHANGELOG.md / versions/ / dist/，提供一键构建入口
- 发布向导：版本号 → 更新日志 → 构建脚本 → git tag → 提交，构建失败自动中止并报告；支持补丁/次版本/主版本快速递增
- 概览页 Git 状态面板：最新提交 / 工作区变更数 / 变更文件列表，可一键刷新
- 搜索与筛选空状态区分（无项目 / 无匹配结果）
- 抽屉面板切换加入淡入动画；聊天任务结束即复位输入框
- iOS 风格 UI：毛玻璃侧边栏、弹簧动画、深色/浅色/跟随系统主题
- 项目 Logo 展示：卡片与详情抽屉显示项目 Logo（优先读取项目内 logo.png / icon.png / favicon.ico 等文件，缺失时按类型渐变底色 + emoji 兜底）
- 版本产物次级菜单：每个版本目录可「打开文件夹 / 位置」，dist 内每个构建产物（exe/zip 等）可「打开 / 位置 / 复制」，支持直接运行或定位文件
- 项目文档面板：概览页「项目文档」列出 README 与计划书/企划书/方案/设计/需求/说明书等文档，支持「打开 / 位置」
- 最新构建视图：版本与构建页顶部「最新构建」按修改时间跨 版本目录 + 根目录 dist/ 合并展示，未归档构建带标记并可一键去合规归档
- 项目合规化：新增「合规」Tab，按类型展示管理规范（必需/建议/预设目录）、逐项检查结果，一键修复（创建缺失标准文件、git init、归档根 dist 构建产物）；归档/移动类动作默认不勾选并需显式确认，工具不删除任何文件
- 项目列表与概览展示合规状态徽标；修复 VERSION 文件带 UTF-8 BOM 时版本号读取异常
- AI 开发闭环地基（v0.2 阶段 1）：项目契约 AGENTS.md（版本/git/归档/日志/流程规范，按类型渲染）+ 动态上下文注入 agent
- AI 操作日志：每项目 logs/ai/ 持久化（agent 主动写 + App 内任务自动写），CLI/API 双入口
- projectdock-cli：contract / context / status / log / logs 子命令，供外部 AI agent 对接
- API 新增 /ai-logs、/contract；合规修复新增「生成 AGENTS.md 项目契约」动作
- 设计文档：02_AI开发闭环设计.md（含 dogfood 方案与 v0.2 路线图）；ProjectDock 自身 AGENTS.md 已契约化（dogfood）
- 修复 PyInstaller windowed 版启动崩溃：stdout/stderr 重定向 + 崩溃日志（%LOCALAPPDATA%/ProjectDock/crash.log）；构建加入 --paths src
- 健壮性修复：文件夹重命名/移动不再触发 UNIQUE(path) 冲突；更换根目录自动刷新注册路径；移除管理的项目不会重新出现在列表
- 安全修复：项目名清理 Windows 非法字符与 `..` 路径穿越
- 勾选 GitHub 但关闭预设时自动 git init + 首次提交后再建仓
- AI 命令无法启动时输出失败任务报告；任务注册表自动清理防内存累积
- 备份改用 os.walk 剪枝（跳过 .venv/node_modules/versions 等大目录）；未注册项目类型推断
- 修复 UI 无法交互：hidden 属性被 display:flex 覆盖，空状态/模态遮罩始终显示并拦截点击；新增 [hidden]{display:none!important} 并限定 .empty 于主区
