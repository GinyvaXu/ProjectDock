# ProjectDock 项目状态

- 版本：0.1.0（MVP）
- 状态：✅ 已完成初始化与核心功能实现
- GitHub：https://github.com/GinyvaXu/ProjectDock（私有，main 分支）

## v0.1.0 完成项
1. 项目创建与管理（内置 7 类型 + 自定义类型，自动命名 项目NN-类型-名称，SQLite 索引 + 扫描）
2. 预设一键初始化（骨架文件 + git init + 首次提交 + 可选自动创建 GitHub 仓库）
3. 版本与构建展示（读取本地约定文件 VERSION / CHANGELOG / versions/ / dist/，一键构建入口）
4. 发布向导（版本号 → 更新日志 → 构建脚本 → git tag → 提交，构建失败自动中止并报告）
5. AI 项目助手（App 内嵌聊天，claude / pi 可切换，默认 pi；全自动执行 + 任务前备份 + 任务后操作/Git 报告）
6. iOS 风格 UI（毛玻璃 / 弹簧动画 / 深色浅色跟随系统，面板切换淡入动画）；修复 hidden 与 display:flex 冲突导致的界面被遮罩锁定（空状态层/模态遮罩不再拦截交互）
7. 概览页 Git 状态面板（最新提交 / 工作区变更 / 一键刷新）、搜索空状态区分、发布向导版本快速递增
8. 测试与质量门禁：65 个用例通过，覆盖率 83.17%（门槛 80%）
9. 构建脚本：build_debug.py / build_exe.py（PyInstaller → versions/vX.Y.Z/dist/），debug/release 均已构建验证，windowed 版崩溃已修复（devnull + crash.log）
10. GitHub：私有仓库已推送（main 分支），新项目可一键自动建仓

## 逻辑链路审查与修复（R3）
1. 数据层：upsert 冲突处理（重命名/移动/换根目录）、移除管理不再复活
2. 安全：项目名消毒（Windows 非法字符、路径穿越）
3. GitHub：无预设勾选建仓时自动 git init + 提交
4. 任务链路：agent 启动失败也出报告、任务队列自动清理
5. 性能：备份 os.walk 剪枝、未注册项目类型推断
6. 默认值对齐：AI 后端统一回落 pi

## 待办（v0.2+）
- 批量 AI 任务（多项目同时下指令）
- 模板导入/导出、GitHub Releases 拉取
- 自动更新（检查 GitHub 新版本 → 下载 → 安装）
- 多根目录、托盘、全局快捷键
