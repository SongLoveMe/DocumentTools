# AGENTS.md instructions for D:\other\Tool_Collection\DocumentTools

## 项目定位

DocumentTools 是 Windows x64 本地文档处理工具。V2 提供 doc/docx/ppt/pptx/xls/xlsx 与图片转 PDF、
PDF 合并目录/书签/封面、PDF 页面排列与编辑、PDF 转 Word/PPT/Excel/PNG/JPG。
所有输入和输出留在本机；软件自身不调用云端 API，也不会把文档上传到任何服务。

Office 转 PDF 由**用户本机已安装的 Microsoft Office 或 WPS** 通过 COM 自动化完成。
DocumentTools 不携带、不打包、不附带任何排版引擎、外部可执行文件或运行时。

## 开发环境

- 项目环境：`D:\Anaconda\envs\documenttools`（仅本机开发使用；其他文档不得写死本机路径）。
- Python 3.13、PyQt5/Qt 5.15.2；基础环境见 `environment.yml`，全部 Python 包版本见 `requirements.lock`。

## 支持格式

- “转为 PDF”支持 `doc`、`docx`、`ppt`、`pptx`、`xls`、`xlsx` 与图片（jpg/jpeg/png/bmp/tif/tiff）。
- WPS 专有格式 `.wps/.dps/.et` 不支持。
- Office 转 PDF 的质量取决于本机安装的 Office/WPS 版本；未安装任何引擎时不提供本地降级，改为引导在线转换。

## 实现约束

- 不覆盖输入文件；输出冲突自动生成 `文件名 (1).扩展名`。
- 加密 PDF 只尝试空密码；需要真实打开密码时明确失败，不猜密码。
- 页面操作参数必须按当前操作动态显示，不显示无关控件。
- 输出日志保存真实路径；双击打开前检查文件是否存在，文件不存在时明确提示。
- 任务失败只影响当前任务，界面必须显示可定位的错误信息。
- **禁止打包、携带或命令行调用任何外部转换 EXE 或运行时。**
- **允许通过 COM 自动化调用用户本机已安装的 Microsoft Office / WPS**，这是 Office 转 PDF 的唯一途径。
- **检测引擎只允许读取注册表，不得在检测阶段启动 Office/WPS 或创建 COM 实例。**
- **转换期间不得出现任何 Office/WPS 窗口**：Word/Excel 用 `Visible=False`，
  PowerPoint 不接受该属性，必须用 `Presentations.Open(..., WithWindow=False)`，且不得给 PowerPoint 设置 `Visible`。
- COM 调用只允许出现在 `office_worker.py`，并且必须运行在独立辅助进程中，以便超时强杀。

## 模块职责

- `src/documenttools/app.py`：兼容导出层，只导出 `run`、`MainWindow`、`ConversionTab`、`MergeTab`。
- `src/documenttools/conversions.py`：图片/Office/PDF 转换领域流程，含在线转换引导常量。
- `src/documenttools/engines.py`：本机 Office/WPS 的注册表检测、引擎选择与辅助进程调用，是转换引擎的唯一入口。
- `src/documenttools/office_worker.py`：隐藏的 COM 辅助进程，唯一允许驱动 Office/WPS 导出的位置；不得导入 PyQt。
- `src/documenttools/settings.py`：`QSettings` 持久化引擎偏好与转换超时。
- `src/documenttools/paths.py`：文件类型分类和冲突路径生成。
- `src/documenttools/pdf_tools.py`：PDF 合并、目录、书签、页面规格、加密和页面操作。
- `src/documenttools/ui/tasking.py`：唯一的 `Task` / `WorkerSignals` 实现。
- `src/documenttools/ui/widgets.py`：唯一的 `FileTable`、`OutputLog`、`LogSection` 和共享 UI 辅助函数。
- `src/documenttools/ui/dialogs.py`：共享的引擎选择、在线转换引导与诊断信息生成。
- `src/documenttools/ui/conversion_tab.py`：转为 PDF 工作区。
- `src/documenttools/ui/settings_tab.py`：设置、引擎诊断与在线转换服务入口。

## 已移除的功能

- 不要重新引入 PDF/A 选项：用户明确要求删除。
- 不要重新引入“PDF 转 Word 使用本机引擎”：Word/WPS 打开 PDF 时会弹无法抑制的模态框并挂死，与“不得弹窗”冲突，实际只会静默回退到纯 Python。
- PDF 转 Word 固定使用 PyMuPDF + python-docx 重建。
- `src/documenttools/ui/merge_tab.py`：PDF 合并工作区。
- `src/documenttools/ui/pdf_workbench.py`：拆分、提取、删除、重排序、页码、旋转和 PDF 转换工作区。
- `src/documenttools/ui/main_window.py`：主窗口、左侧导航、状态栏和全局样式。
- `tests/`：从公共接口和 UI 行为验证功能；不依赖构建产物。
- `scripts/`、`installer/`、`assets/`：打包、安装和静态资源，不参与领域逻辑。

## UI 统一规范

- 所有工作区必须复用 `FileTable`、`OutputLog`/`LogSection`、输出目录/输出文件控件和 `ui.tasking.Task`，不得复制实现。
- 页面结构统一为：标题、说明、源文件或列表、操作参数、输出位置、右对齐主操作按钮、进度、日志区。
- 主操作按钮使用 `objectName="primaryAction"`；次要按钮使用默认样式。
- 所有按钮、标签、提示和错误使用一致中文术语；禁止在单个页面混用英文文案。
- 日志区固定使用 `LogSection`；“清除日志”只清空当前工作区，始终可用，不弹确认，也不自动清空。
- 全局样式只放在 `ui/main_window.py`；新增控件不得写入一次性样式。
- 新增或修改 UI 必须补充 Qt 回归测试。

## 维护规则

- 不要在 `app.py` 重新实现窗口、任务或控件；它必须保持兼容薄层。
- 不要在多个模块复制 `Task`、`WorkerSignals`、`FileTable`、`OutputLog`、`LogSection`。
- 新增 UI 工作区放到 `src/documenttools/ui/`；领域行为放在 `conversions.py`、`engines.py`、`office_worker.py`、`pdf_tools.py` 或 `paths.py`。
- 新增第三方依赖必须同步 `requirements.lock` 与 `THIRD_PARTY_NOTICES.md`。
- 版本 `2.2.0` 必须同步于 `pyproject.toml`、`src/documenttools/__init__.py`、`installer/DocumentTools.iss`。
- `README.md`、`docs/` 中不得出现本机绝对路径或绑死某个用户的目录。
- 新架构决策记录到 `docs/ARCHITECTURE.md`；开发与发布流程记录到 `docs/DEVELOPMENT.md`。
- 不提交 `build`、`dist`、`release`、缓存、测试临时目录或本机配置。

## 验证

使用以下命令运行全部测试：

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
D:\Anaconda\envs\documenttools\python.exe -m pytest
```

构建前运行：

```powershell
git diff --check
```

构建使用 PyInstaller `--windowed`，并自动剔除外部运行时与未使用的重型依赖。
发布包必须确保 `pythoncom` 已打包，且转换过程中不会出现任何 Office/WPS 窗口。
