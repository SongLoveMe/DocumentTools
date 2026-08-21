# AGENTS.md instructions for D:\other\Tool_Collection\DocumentTools

## 项目定位

DocumentTools 是 Windows x64 本地文档处理工具。V2 提供标准 Office/WPS 文档与图片转 PDF、PDF 合并目录/书签/封面、PDF 页面排列与编辑、PDF 转 Word/PPT/Excel/PNG/JPG。所有输入和输出留在本机，不调用云端 API。

## 开发环境

- Conda：`D:\Anaconda\Scripts\conda.exe`，项目环境：`D:\Anaconda\envs\documenttools`。
- Python 3.13、PyQt5/Qt 5.15.2；Conda 基础依赖见 `environment.yml`，Python 包版本见 `requirements.lock`。
- 转换运行时必须随安装包放在 `runtime/libreoffice`；开发目录对应 `vendor/libreoffice`。应用不探测或调用系统 Office、WPS、LibreOffice。
- 运行时应从官方发行包获取，并在 `THIRD_PARTY_NOTICES.md` 记录版本、来源、SHA-256 和许可证。

## 实现约束

- 不覆盖输入文件；输出冲突自动生成 `文件名 (1).扩展名`。
- WPS 兼容指 WPS 创建的 `doc/docx`、`ppt/pptx`、`xls/xlsx`；不承诺 `.wps/.dps/.et` 专有格式。
- 合并 PDF 只调用 `decrypt("")`，支持可查看但禁止编辑的 PDF；需要真实打开密码时明确失败，不猜密码。
- 合并列表顺序由用户决定；移除、拖拽或按钮排序后自动标题按位置更新，手工标题保持不变。
- 页面操作参数必须按当前操作显示，不得保留无关的冗余控件。
- 只有重排序 PDF 允许缩略图拖拽；拆分、提取、删除、旋转、页码操作禁止拖拽。
- “转为 PDF”只处理 Word、PPT、Excel、图片；PDF 转 Word/PPT/Excel/PNG/JPG 只放在“从 PDF 转换”。
- 图片合并选项只有当前选择列表至少有两张图片时才显示。
- 输出日志必须保存真实路径；双击前检查文件存在，文件不存在时明确提示。
- 任务失败只影响当前任务，界面必须显示可定位的错误原因。

## 目录职责

- `src/documenttools/app.py`：兼容导出层，只导出 `run`、`MainWindow`、`ConversionTab`、`MergeTab`。
- `src/documenttools/conversions.py`：图片/Office/PDF 转换领域流程。
- `src/documenttools/engines.py`：内置 LibreOffice 转换运行时适配器。
- `src/documenttools/paths.py`：文件类型分类和冲突路径生成。
- `src/documenttools/pdf_tools.py`：PDF 合并、目录、书签、页面规格、加密和页面操作。
- `src/documenttools/ui/tasking.py`：唯一的 `Task`/`WorkerSignals` 实现。
- `src/documenttools/ui/widgets.py`：唯一的 `FileTable`、`OutputLog` 和共享 UI 辅助函数。
- `src/documenttools/ui/conversion_tab.py`：转为 PDF 工作区。
- `src/documenttools/ui/merge_tab.py`：PDF 合并工作区。
- `src/documenttools/ui/pdf_workbench.py`：拆分、提取、删除、重排序、页码、旋转和 PDF 转换工作区。
- `src/documenttools/ui/main_window.py`：主窗口、左侧导航和全局样式。
- `tests/`：从公共接口和 UI 行为验证功能；不依赖构建产物。
- `scripts/`、`installer/`、`vendor/`：打包、安装和运行时交付，不参与领域逻辑。

## 维护规则

- 不要在 `app.py` 重新实现窗口、任务或控件；它必须保持兼容薄层。
- 不要在多个模块复制 `Task`、`WorkerSignals`、`FileTable`、`OutputLog`。
- 新增 UI 工作区放到 `src/documenttools/ui/`；领域行为放在 `conversions.py`、`pdf_tools.py` 或 `paths.py`。
- 修改运行时路径时同时检查 `engines.py`、`scripts/build.ps1` 和 `installer/DocumentTools.iss`。
- 版本 `2.0.0` 必须同步于 `pyproject.toml`、`src/documenttools/__init__.py`、`installer/DocumentTools.iss`。
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

正式构建前必须确认 `vendor/libreoffice/program/soffice.exe` 存在；构建脚本使用 PyInstaller `--windowed`，LibreOffice 子进程在 Windows 使用无窗口创建标志。
