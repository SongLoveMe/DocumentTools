# Project structure

DocumentTools 当前采用单包、桌面应用结构：

```text
启动入口 main.py
    -> src/documenttools/app.py
        -> conversions.py -> engines.py
        -> pdf_tools.py
        -> paths.py
```

## 模块职责

- `app.py` 只负责 PyQt5 窗口、列表交互、后台任务和状态显示。
- `conversions.py` 负责用户可见的转换流程和错误翻译。
- `engines.py` 是内置 LibreOffice 运行时的唯一适配位置。
- `pdf_tools.py` 负责 PDF 页面、目录、书签、封面和加密规则。
- `paths.py` 提供文件分类与不覆盖输入文件的输出路径策略。

## 资源与交付

- `assets/` 保存应用静态资源。
- `vendor/libreoffice/` 是本地运行时占位目录；安装包内的目标路径为 `runtime/libreoffice`。
- `scripts/` 只包含开发辅助和打包脚本。
- `installer/` 只包含 Inno Setup 定义。
- `tests/` 通过模块公共接口验证功能，不依赖构建产物。

## 当前结构约束

1. `app.py` 仍同时承载转换页和合并页，修改 GUI 时需要保持两个页面共享的 `Task`、`FileTable` 行为。
2. 运行时路径同时出现在 `engines.py`、`scripts/build.ps1` 和安装定义中，路径变化需要同步检查。
3. 版本号同时出现在 `pyproject.toml`、`src/documenttools/__init__.py` 和安装脚本中，发布时需要同步更新。

## 维护规则

- 新增模块前先确认它是否提供真实的接口和测试 seam；不要为了减少文件长度拆出浅模块。
- 领域行为优先放在 `conversions.py`、`pdf_tools.py` 和 `paths.py`，界面只编排调用。
- 新的架构决策应记录在 `docs/`，并同步更新 README 的项目结构和 AGENTS.md 的约束。
