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
6. iOS 风格 UI（毛玻璃 / 弹簧动画 / 深色浅色跟随系统）
7. 测试与质量门禁：56 个用例通过，覆盖率 82.26%（门槛 80%）
8. 构建脚本：build_debug.py / build_exe.py（PyInstaller → versions/vX.Y.Z/dist/）
9. GitHub：私有仓库已推送（main 分支），新项目可一键自动建仓

## 待办（v0.2+）
- 批量 AI 任务（多项目同时下指令）
- 模板导入/导出、GitHub Releases 拉取
- 自动更新（检查 GitHub 新版本 → 下载 → 安装）
- 多根目录、托盘、全局快捷键
