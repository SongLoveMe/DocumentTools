# 架构说明

## 1. 分层

```text
main.py / python -m documenttools
    -> documenttools.app（兼容导出层）
        -> documenttools.ui.main_window
            -> ui.conversion_tab / ui.merge_tab / ui.pdf_workbench
                -> ui.tasking / ui.widgets
                -> conversions / pdf_tools / paths
                    -> engines（仅 Office/WPS 转 PDF）
```

依赖方向从界面指向领域逻辑；领域模块不依赖 PyQt。`engines.py` 是内置 LibreOffice 运行时的唯一适配位置。

## 2. 模块职责

- `conversions.py`：图片、Office、PDF 到 Word/PPT/Excel/图片的转换流程和错误翻译。
- `pdf_tools.py`：PDF 合并、目录、书签、封面、加密处理、页面拆分/提取/删除/重排序、页码、旋转和纯 Python 压缩。
- `paths.py`：文件类型分类和不覆盖输入的冲突路径策略。
- `engines.py`：只解析程序随附的 LibreOffice 运行时；Windows 子进程使用无窗口启动参数。
- `ui/tasking.py`：项目唯一的 `Task`/`WorkerSignals` 实现。
- `ui/widgets.py`：项目共享的 `FileTable`、`OutputLog`、输出目录控件和通用 UI 辅助函数。
- `ui/conversion_tab.py`：仅处理“转为 PDF”，不放置 PDF 转 Word/PPT。
- `ui/merge_tab.py`：PDF 合并、封面、目录、标题和页面规格。
- `ui/pdf_workbench.py`：PDF 页面操作、页码、旋转、压缩和从 PDF 转换。
- `ui/main_window.py`：左侧导航、页面组装和全局样式。
- `app.py`：保持 `documenttools.app` 的 `run`、`MainWindow`、`ConversionTab`、`MergeTab` 兼容导出。

## 3. UI 约束

- 参数面板必须与当前操作匹配；不要创建并隐藏大量无关控件来模拟动态 UI。
- 只有重排序页面允许缩略图拖拽；提取、删除、旋转、页码和拆分均禁止拖拽。
- 转为 PDF 只显示 Word/PPT/Excel/图片输入；PDF 转换入口只在“从 PDF 转换”。
- 图片合并选项只有在当前列表至少有两张图片时出现。
- 所有输出型页面提供选择输出目录和打开输出目录；输出日志记录真实路径并支持双击打开。
- 所有耗时操作通过 `ui.tasking.Task` 执行，不能在 UI 线程直接处理 PDF。

## 4. 数据流

1. UI 收集路径、页码和选项。
2. UI 创建领域函数闭包并交给 `Task`。
3. 后台任务执行 `conversions.py` 或 `pdf_tools.py`。
4. 成功结果携带输出 `Path` 回到 UI。
5. `OutputLog` 保存输出路径到 `Qt.UserRole`，双击时验证文件存在后打开。
6. 失败只更新当前任务状态，不影响其他任务。

## 5. 运行时与交付

- 开发运行时：`vendor/libreoffice`。
- 安装后运行时：`runtime/libreoffice`。
- 程序不调用系统 Office、WPS 或 LibreOffice。
- PyInstaller 使用 `--windowed`；LibreOffice 子进程使用 Windows 隐藏窗口标志。
- 版本号必须同步于 `pyproject.toml`、`src/documenttools/__init__.py` 和 `installer/DocumentTools.iss`。

## 6. v2.1 PDF 压缩

PDF 压缩使用已锁定的 PyMuPDF Python 包，不调用 Ghostscript、qpdf 命令行程序或用户系统中的其他 PDF 软件。压缩模块通过图片重编码、可选降采样、内容流压缩和安全垃圾回收减少体积。

`estimate_pdf_compression` 只读取 PDF 页面和嵌入图片信息，不创建正式输出；`compress_pdf` 在目标目录生成临时文件、校验页数后再提交输出。压缩结果使用 `CompressionPreset` 和 `CompressionResult` 表达，UI 不直接处理 PDF 对象。
