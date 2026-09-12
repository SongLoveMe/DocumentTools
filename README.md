# DocumentTools

DocumentTools 是 Windows x64 本地文档处理工具。所有输入、临时文件和输出均保留在本机，不调用云端 API，也不会探测或调用系统 Office、WPS 或 LibreOffice。

## 项目版本

当前项目版本：`2.1.0`。该版本号属于 DocumentTools 项目，不代表任何第三方依赖版本。

## V2 功能

### PDF 工作台

- 排列 PDF：合并、拆分、提取指定页、删除指定页、重排序。
- 编辑 PDF：添加页码、旋转页面、压缩 PDF。
- PDF 压缩：无损、轻度、平衡、强力四档，使用本地 Python 组件处理。
- 压缩预估：根据页面和嵌入图片信息显示预计大小，最终结果以实际输出为准。
- 从 PDF 转换：Word、PowerPoint、可识别表格 Excel、逐页 PNG/JPG。
- 转为 PDF：Word、PowerPoint、Excel 和图片。
- 页面操作支持后台生成缩略图；只有重排序操作允许拖拽页面。
- 操作参数按当前选择动态显示，不显示无关控件。
- 输出日志支持双击打开对应输出文件；文件不存在时显示提示。

### 输出与安全规则

- 不覆盖输入文件或已有输出；冲突时自动生成 `文件名 (1).扩展名`。
- 拆分结果放入源文件对应的专用文件夹。
- 加密 PDF 只尝试空密码；需要真实打开密码时明确失败，不猜密码。
- WPS 兼容指 WPS 创建的标准 `doc/docx`、`ppt/pptx`、`xls/xlsx`；不承诺 `.wps/.dps/.et`。
- PDF 转 Excel 只提取可识别的数字 PDF 表格，不做 OCR。
- 当前版本暂不支持 PDF 裁剪和水印。PDF 打开密码只尝试空密码，不猜测真实密码。

## 项目结构

```text
DocumentTools/
├─ main.py                         # 开发/打包启动入口
├─ src/documenttools/
│  ├─ __init__.py                  # 包版本
│  ├─ __main__.py                  # python -m documenttools
│  ├─ app.py                       # 兼容导出层
│  ├─ conversions.py               # 文件格式转换领域逻辑
│  ├─ engines.py                   # 内置 LibreOffice 适配器
│  ├─ paths.py                     # 文件分类和冲突路径
│  ├─ pdf_tools.py                 # PDF 合并、压缩与页面领域逻辑
│  └─ ui/
│     ├─ tasking.py                # 唯一的 Qt 后台任务封装
│     ├─ widgets.py                # FileTable、OutputLog 等通用控件
│     ├─ conversion_tab.py         # 转为 PDF 工作区
│     ├─ merge_tab.py              # PDF 合并工作区
│     ├─ pdf_workbench.py          # 页面操作、页码、旋转、PDF 转换
│     └─ main_window.py            # 主窗口、导航和样式
├─ tests/                          # 公共接口与 UI 回归测试
├─ docs/                           # 架构和维护文档
├─ scripts/                        # 图标和打包脚本
├─ installer/                      # Inno Setup 定义
├─ assets/                         # 图标等静态资源
└─ vendor/libreoffice/             # 开发/发布使用的内置运行时
```

## 开发环境

项目使用 Conda 环境 `documenttools`，Python 3.13、PyQt5/Qt 5.15.2。

```powershell
D:\Anaconda\Scripts\conda.exe env update -f environment.yml
& D:\Anaconda\envs\documenttools\python.exe -m pip install -r requirements.lock
```

开发启动：

```powershell
& D:\Anaconda\envs\documenttools\python.exe main.py
# 或
& D:\Anaconda\envs\documenttools\python.exe -m documenttools
```

直接从 PowerShell 启动脚本时，PowerShell 本身会保持可见；正式 EXE 和测试 EXE 使用 PyInstaller `--windowed`，不显示控制台窗口。

## 测试

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
& D:\Anaconda\envs\documenttools\python.exe -m pytest
```

测试不会依赖构建产物。测试临时目录匹配 `pytest-*`、`.pytest-tmp/` 和 `.pytest-work/`，已加入 `.gitignore`。

## 打包发布

1. 将经过审核的 Windows x64 LibreOffice 官方发行包放入 `vendor/libreoffice`，并确认存在 `program/soffice.exe`。
2. 确认 `THIRD_PARTY_NOTICES.md` 已记录版本、来源、许可证和 SHA-256 要求。
3. 执行：

   ```powershell
   .\scripts\build.ps1
   ```

4. PyInstaller 输出到 `dist/DocumentTools`；如安装 Inno Setup 6，安装包输出到 `release/`。
5. 发布前执行 `docs/DEVELOPMENT.md` 中的检查清单。

构建产物、缓存、测试临时目录和本机配置不得提交到版本库。
