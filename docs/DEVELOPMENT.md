# 开发说明

## 1. 环境准备

项目要求 Windows x64 与 Python 3.13。依赖版本固定在 `requirements.lock`。

```bash
conda env create -f environment.yml
conda activate documenttools
python -m pip install -r requirements.lock
```

`environment.yml` 只负责创建基础 Python 环境，其余依赖一律由 `requirements.lock` 固定。
新增第三方依赖必须同时更新 `requirements.lock` 与 `THIRD_PARTY_NOTICES.md`。

开发启动：

```bash
python main.py
# 或
python -m documenttools
```

## 2. 运行测试

```bash
python -m pytest
```

无桌面环境下运行 Qt 测试前先设置 `QT_QPA_PLATFORM=offscreen`。
测试临时目录默认位于系统临时目录；若该目录不可写，可用 `TMPDIR`/`TEMP` 指向项目内的
`pytest-*` 目录（已被 `.gitignore` 忽略）。

## 3. 模块边界

- UI 代码放在 `ui/`；领域逻辑放在 `conversions.py`、`pdf_tools.py`、`paths.py`。
- 引擎检测与调用集中在 `engines.py`；COM 自动化只允许出现在 `office_worker.py`。
- 不要在 `app.py` 重新实现窗口、任务或控件；它必须保持兼容薄层。
- 只有一个 `Task`/`WorkerSignals`（`ui/tasking.py`）与一套共享控件（`ui/widgets.py`）。
- 禁止引入任何外部文档转换可执行文件、运行时目录或命令行调用。
- 转换期间不得出现任何 Office/WPS 窗口；修改 COM 参数后必须重新验证这一点。

## 4. Office/WPS 引擎开发须知

- 检测只读注册表：`HKCU`/`HKLM` 的 `Software\\Classes` 默认视图与 32 位视图。
- **不能只看 ProgID 判断引擎归属**：WPS 会注册 Microsoft 的 ProgID，必须解析
  `CLSID\\{...}\\LocalServer32` 并按可执行文件路径判断。
- WPS 的类信息位于 32 位视图；读取注册表时要用 `KEY_WOW64_32KEY` 单独打开，
  不要与 `KEY_READ` 直接相或（`KEY_READ` 已含 64 位标志）。
- Word/Excel 使用 `Visible = False`；PowerPoint 不接受该属性，必须改用
  `Presentations.Open(..., WithWindow=False)`。不要给 PowerPoint 设置 `Visible`。
- 子进程模式由隐藏参数 `--documenttools-office-worker <请求.json> <响应.json>` 触发，
  必须在创建 `QApplication` 之前处理，保证打包后无控制台也能运行。
- 超时或失败时只结束辅助进程自身创建的引擎 PID，绝不结束用户已打开的 Word/WPS。
- 设置页的“重新检测引擎”按钮用于安装/升级 Office/WPS 后即时刷新，不需要重启程序。
- 排查“装了 Office 却转换失败”时，先看设置页复制出的诊断信息（ProgID、CLSID、EXE 路径、版本），
  再检查杀毒软件或 EDR 是否拦截了 Office 自动化，以及文档是否处于受保护视图。

## 5. UI 一致性检查

- 复用 `FileTable`、`LogSection`、输出目录/输出文件控件与 `ui.tasking.Task`。
- 主操作按钮使用 `objectName="primaryAction"`；全局样式只写在 `ui/main_window.py`。
- 页面结构统一为标题、说明、源文件、参数、输出位置、右对齐主操作按钮、进度、日志。
- 日志“清除日志”只清空当前工作区，不自动清空、不取消任务。
- 新增或修改 UI 必须补充 Qt 回归测试。

## 6. 构建

构建脚本会用 PyInstaller 生成 `dist/DocumentTools`，并在安装了 Inno Setup 6 时继续生成安装包：

```powershell
.\scripts\build.ps1
```

用 `-Environment` 指定用于构建的 Python 环境目录：

```powershell
.\scripts\build.ps1 -Environment "<你的 Conda 环境目录>"
```

构建脚本会自动：

- 剔除未使用的重型依赖（`cv2`、`numpy`、`pandas`、`scipy`、`matplotlib`、`tkinter`、Qt Qml/Quick）。
- 排除 `win32comext`、`pythonwin` 与 `win32com.gen_py` 等不需要的 pywin32 子模块。
- 校验 `pythoncom` 确实被打包（否则发布包的 COM 调用会失败）。
- 在结束后删除 `build/` 中间目录。

手动清理构建产物：

```powershell
.\scripts\clean.ps1
```

## 7. 发布检查清单

1. `git diff --check` 无输出。
2. `python -m pytest` 全部通过。
3. 版本号 `2.2.0` 在 `pyproject.toml`、`src/documenttools/__init__.py`、`installer/DocumentTools.iss` 中一致。
4. `requirements.lock` 与 `THIRD_PARTY_NOTICES.md` 同步，且未出现 `openpyxl`、`pdf2docx`、`cv2`、`numpy`。
5. 仓库中不存在 `vendor/`、`assets/fonts/`、`office_pdf.py`、`fonts.py` 等已移除内容。
6. `scripts/build.ps1` 成功产出 `dist/DocumentTools`，且 `pythoncom` 已打包。
7. 在装有 Office 与 WPS 的机器上手工验证：
   - `doc`/`docx`/`ppt`/`pptx`/`xls`/`xlsx` 六种格式都能转为 PDF。
   - 转换全过程**没有任何 Office/WPS 窗口出现**。
   - 日志与表格状态显示实际使用的引擎。
   - 在另一处打开 Word 的同时执行转换，转换结束后该 Word 不受影响。
   - 批量转换结束后没有残留的 WINWORD/EXCEL/POWERPNT/wps/et/wpp 进程。
8. 在未安装任何引擎的机器上验证：仅弹出在线转换引导，不产生任何输出文件。
9. 检查设置页只列出已检测到的引擎，且保存后重新打开仍然生效。
10. 检查设置页不再出现 PDF/A 或 PDF 转 Word 后端选项，并列出三个在线转换服务入口。
11. 检查“重新检测引擎”按钮可即时刷新引擎状态与下拉框。

## 8. 约定

- 不修改或删除用户的输入文件；输出冲突时生成 `文件名 (1).扩展名`。
- 加密 PDF 只尝试空密码，不猜密码。
- 新增架构决策写入 `docs/ARCHITECTURE.md`；变更记录写入 `docs/CHANGELOG.md`。
- 不提交 `build/`、`dist/`、`release/`、缓存与测试临时目录。
