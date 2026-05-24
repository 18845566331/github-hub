# GitHub Hub

一个用于管理、安装和运行 GitHub 项目的 Windows 桌面应用。

## 功能

- 添加 GitHub 项目并克隆到本地。
- 自动识别 Python、Node.js、Go 与 Rust 依赖流程。
- 为 Python 项目创建隔离环境并安装依赖。
- 启动可运行项目，识别本地 Web 服务地址。
- 为经过真实测试的仓库使用内置安装/启动配方，减少入口误判。
- 浏览 GitHub 热门项目与分类列表。
- 提供镜像设置、依赖状态管理与环境诊断工具。

## 快速开始

要求：

- Windows 10/11
- Python 3.10+
- Git
- Node.js / pnpm（仅 Node 项目需要）

```bash
python -m pip install -r requirements.txt
python main.py
```

## 配置安全

应用首次运行后会在本地生成配置。`config.json` 可能包含本机项目路径与 GitHub Token，因此已从版本控制排除。

需要准备配置示例时，请基于 `config.example.json` 创建本机配置，不要提交真实 Token 或本机路径。

## 测试

```bash
python -m compileall -q main.py app tests
python -m unittest discover -s tests -p "test_dependency_workflow.py" -v
```

`tests/ui_real_github_e2e.py` 与 `tests/ui_real_feature_walkthrough.py` 会执行真实网络、安装与项目启动操作，仅在明确了解其影响时运行。

## 打包

```bash
python -m pip install pyinstaller
python build_exe.py
```

## 贡献

欢迎提交 Issue 与 Pull Request。提交问题时请删除配置、日志中的 Token 和本机路径等隐私内容。

## License

[MIT](LICENSE)
