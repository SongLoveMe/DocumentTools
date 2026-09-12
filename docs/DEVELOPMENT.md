# 开发与发布指南

## 环境

```powershell
D:\Anaconda\Scripts\conda.exe env update -f environment.yml
& D:\Anaconda\envs\documenttools\python.exe -m pip install -r requirements.lock
```

项目要求 Python 3.13、PyQt5/Qt 5.15.2。不要在系统 Python、系统 Office 或系统 LibreOffice 上运行转换逻辑。

## 启动

```powershell
& D:\Anaconda\envs\documenttools\python.exe main.py
& D:\Anaconda\envs\documenttools\python.exe -m documenttools
```

## 测试

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
& D:\Anaconda\envs\documenttools\python.exe -m pytest
```

测试临时目录应使用项目内的 `pytest-*` 目录或由 pytest 管理的临时目录；这些路径已被 `.gitignore` 忽略。测试完成后不得把测试输出留在版本库中。

## 结构维护

- UI 共享任务只能放在 `ui/tasking.py`。
- UI 共享控件只能放在 `ui/widgets.py`。
- 新工作区放入 `ui/`，领域逻辑放入 `conversions.py` 或 `pdf_tools.py`。
- `app.py` 只作为兼容导出层，不重新实现窗口和控件。
- 新增公共领域接口必须补充测试；UI 行为必须补充 Qt 回归测试。
- 修改运行时路径时同时检查 `engines.py`、`scripts/build.ps1` 和 `installer/DocumentTools.iss`。

## 打包

发布前确认：

- `vendor/libreoffice/program/soffice.exe` 存在。
- `requirements.lock` 与 `THIRD_PARTY_NOTICES.md` 一致。
- 版本 `2.1.0` 在 `pyproject.toml`、`src/documenttools/__init__.py`、`installer/DocumentTools.iss` 中一致。
- 执行 `git diff --check` 无输出。
- 执行完整 pytest 且全部通过。
- 构建目录不包含用户文件、测试文件或缓存。

执行构建：

```powershell
.\scripts\build.ps1
```

脚本生成 PyInstaller `--windowed` EXE；如果安装 Inno Setup 6，会继续生成安装包。

## 发布检查

- 验证 EXE 启动无控制台窗口。
- 验证 Office/WPS 转 PDF 时 LibreOffice 子进程无控制台窗口。
- 验证输出不覆盖输入和既有文件。
- 验证加密 PDF 的空密码/真实密码行为。
- 验证日志双击打开输出文件和文件不存在提示。
- 不提交 `build/`、`dist/`、`release/`、`pytest-*`、`.pytest-tmp/`、缓存或本机配置。

## v2.1 PDF 压缩验证

- PDF 压缩只允许使用 `requirements.lock` 中的 Python 依赖，不添加外部 PDF 可执行程序。
- 验证无损、轻度、平衡、强力四个档位都能生成可重新打开的 PDF。
- 验证输入文件不被覆盖，输出冲突时使用 `文件名 (1).pdf`。
- 验证真实打开密码不会被猜测，可查看但禁止编辑的 PDF 按空密码规则处理。
- 验证预估信息明确标注为参考值，实际压缩结果记录原始大小、输出大小和压缩比例。
- 图标源文件为 `assets/documenttools.svg`，Windows 打包图标为 `assets/documenttools.ico`。
