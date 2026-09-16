# 架构说明

## 1. 分层

```text
main.py / python -m documenttools
    -> documenttools.app（兼容导出层）
        -> documenttools.ui.main_window
            -> ui.conversion_tab / ui.merge_tab / ui.pdf_workbench / ui.settings_tab
                -> ui.tasking / ui.widgets / ui.dialogs
                -> conversions / pdf_tools / paths
                    -> engines -> office_worker
                -> settings
```

依赖方向从界面指向领域逻辑；领域模块不依赖 PyQt（`settings.py` 除外的少数模块会读取 `QSettings`）。
`engines.py` 是 Office 转 PDF 的唯一适配位置，`office_worker.py` 是唯一执行 COM 自动化的位置。

## 2. 模块职责

- `conversions.py`：图片、Office 转 PDF，以及 PDF 到 Word/PPT/Excel/图片的转换流程和错误翻译。
- `engines.py`：只读注册表检测本机 Microsoft Office / WPS，选择引擎，并在独立辅助进程中调用转换。
- `office_worker.py`：隐藏的辅助进程入口，通过 COM 驱动 Office/WPS 导出 PDF；不导入 PyQt。
- `settings.py`：`QSettings` 持久化引擎偏好与转换超时。
- `pdf_tools.py`：PDF 合并、目录、书签、封面、加密处理、页面拆分/提取/删除/重排序、页码、旋转和纯 Python 压缩。
- `paths.py`：文件类型分类和不覆盖输入的冲突路径策略。
- `ui/tasking.py`：项目唯一的 `Task` / `WorkerSignals` 实现。
- `ui/widgets.py`：项目共享的 `FileTable`、`OutputLog`、`LogSection`、输出控件和通用 UI 辅助函数。
- `ui/dialogs.py`：共享的引擎选择对话框、在线转换引导对话框与诊断信息生成。
- `ui/conversion_tab.py`：仅处理“转为 PDF”，不放置 PDF 转 Word/PPT。
- `ui/settings_tab.py`：引擎选择、导出选项与引擎诊断。
- `ui/merge_tab.py`：PDF 合并、封面、目录、标题和页面规格。
- `ui/pdf_workbench.py`：PDF 页面操作、页码、旋转、压缩和从 PDF 转换。
- `ui/main_window.py`：左侧导航、页面组装、状态栏和全局样式。
- `app.py`：保持 `documenttools.app` 的 `run`、`MainWindow`、`ConversionTab`、`MergeTab` 兼容导出。

## 3. 引擎检测与调用

```text
detect_local_engines()
    -> 只读 HKCU / HKLM 的 Classes 与 32 位视图
    -> 解析 ProgID 的 CLSID 与 LocalServer32
    -> 按解析到的 EXE 路径判定 Office 或 WPS
    -> 绝不创建 COM 实例，也绝不启动任何进程
```

- 支持的应用：Word（`doc`/`docx`）、Excel（`xls`/`xlsx`）、PowerPoint（`ppt`/`pptx`）。
- 探测的 ProgID：`Word.Application`、`Excel.Application`、`PowerPoint.Application`，以及 WPS 专有的 `KWPS.Application`、`KET.Application`、`KWPP.Application`。
- **归属以解析到的可执行文件为准**：WPS 会在用户注册表下注册 Microsoft 的 ProgID，只看 ProgID 会把 WPS 误报为 Office。
- WPS 的类信息注册在 32 位视图下，因此必须同时探测默认视图与 `WOW64` 32 位视图。
- 引擎一旦确定，`convert_with_local_engine` 会把请求写成 JSON，启动一个独立辅助进程执行，父进程按超时强杀。
- 检测结果不缓存：每次开始转换前重新检测，以便识别刚安装或刚卸载的引擎。

## 4. 无窗口与故障隔离

- Word 与 Excel：`Visible = False`，并以只读方式打开文档。
- PowerPoint：`Visible = False` 会被 Office 与 WPS 拒绝，因此不设置该属性，改用
  `Presentations.Open(..., WithWindow=False)` 打开，窗口始终不会出现。
- 统一设置 `DisplayAlerts = 0`；Word/Excel 额外尝试 `AutomationSecurity = 3` 以禁用宏。
- 每次转换都在独立辅助进程中运行：Office 因对话框或损坏文档挂起时，主程序可超时强杀子进程，
  且不会影响用户已经打开的 Word/WPS。
- 辅助进程启动后会把自身创建的引擎 PID 写入状态文件，父进程超时后只结束这些 PID。
- 转换结果会校验 PDF 文件头与页数，不合法即视为失败，不留下可疑的半成品。
- 转换前若源文件位于网络路径或带有“来自网络”标记，会先复制到临时目录，避免受保护视图阻塞转换。

## 5. UI 约束

- 参数面板必须与当前操作匹配；不要创建并隐藏无关控件来模拟动态 UI。
- 只有重排序页面允许缩略图拖拽；提取、删除、旋转和拆分均禁止拖拽。
- 转为 PDF 接受 doc/docx/ppt/pptx/xls/xlsx 与图片；`.wps/.dps/.et` 在文件分类层即判定为不支持。
- 图片合并选项只在列表至少有两张图片时出现。
- 输出型页面提供输出目录或输出文件控件；输出日志记录真实路径并支持双击打开。
- 所有耗时操作通过 `ui.tasking.Task` 执行，不能在 UI 线程直接处理文档。
- 所有工作区共用 `LogSection` 展示日志；“清除日志”只操作当前工作区，不取消任务也不自动清空。
- 页面结构、主操作按钮、中文术语和全局样式遵循 `AGENTS.md` 的 UI 统一规范。

## 6. 数据流

1. UI 收集路径、页码和选项。
2. UI 创建领域函数闭包并交给 `Task`。
3. 后台任务执行 `conversions.py` 或 `pdf_tools.py`。
4. Office 格式由 `conversions.py` 选出一个已检测到的引擎，经 `engines.py` 启动辅助进程，
   由 `office_worker.py` 通过 COM 导出 PDF。
5. 成功结果携带输出 `Path` 与引擎标签回到 UI。
6. `LogSection` 内的 `OutputLog` 保存输出路径到 `Qt.UserRole`，双击时验证文件存在后打开；清除按钮只重置当前工作区列表。
7. 失败只更新当前任务状态；Office 文件全部失败时弹在线转换引导。

## 7. 交付与体积

- 项目不携带、不打包任何转换运行时或外部可执行文件；安装包只包含 PyInstaller 产物。
- Office 转 PDF 依赖用户本机已安装的 Microsoft Office 或 WPS，通过 COM 调用。
- 第三方 Python 依赖：`PyQt5`、`Pillow`、`pypdf`、`PyMuPDF`、`python-docx`、`python-pptx`、`reportlab`、`XlsxWriter`、`pywin32`。
- `scripts/build.ps1` 使用 PyInstaller `--windowed` 构建，剔除外部运行时与未使用的重型依赖，并在结束后清理 `build/`。
- `scripts/clean.ps1` 用于手动清理构建产物；所有删除目标都会校验位于项目根目录内。
- 版本号必须同步于 `pyproject.toml`、`src/documenttools/__init__.py` 和 `installer/DocumentTools.iss`。
- `installer/DocumentTools.iss` 只打包 `dist/DocumentTools`，确保安装包内容与构建产物一致。

## 8. 转换保真度边界

- Office 转 PDF 的排版保真度取决于用户安装的 Microsoft Office 或 WPS 版本，不做跨版本一致保证。
- 未安装任何本机引擎时不提供本地降级方案，UI 会引导用户使用在线转换服务。
- `.wps/.dps/.et` 专有格式不支持。
- PDF 转 Word 默认是简化重建；仅在设置中开启实验性选项时才会尝试本机引擎重流，失败自动回退。
- PDF 转 Excel 只提取可识别表格，不做 OCR。
