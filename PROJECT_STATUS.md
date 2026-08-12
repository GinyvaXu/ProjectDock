# ProjectDock 项目状态

- 版本：0.1.0（MVP）
- 状态：✅ 已完成初始化与核心功能实现
- GitHub：https://github.com/GinyvaXu/ProjectDock（私有，main 分支）

## v0.1.0 完成项
1. 项目创建与管理（7 种类型，自动命名 项目NN-类型-名称，SQLite 索引 + 扫描）
2. 预设一键初始化（骨架文件 + git init + 首次提交）
3. 版本与构建展示（VERSION / CHANGELOG / versions/ / dist/ 解析，一键构建入口）
4. AI 项目助手（claude / pi 可切换，流式输出，已用真实 claude CLI 验证）
5. iOS 风格 UI（毛玻璃 / 弹簧动画 / 深色浅色跟随系统）
6. 测试与质量门禁：44 个用例通过，覆盖率 86%（门槛 80%）
7. 构建脚本：build_debug.py / build_exe.py（PyInstaller → versions/vX.Y.Z/dist/）

## 待办（v0.2+）
- 模板编辑器（自定义预设）
- GitHub Releases 拉取与发布向导
- 多根目录、托盘、全局快捷键
