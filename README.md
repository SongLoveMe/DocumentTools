# DocumentTools

DocumentTools 是 Windows x64 本地文档处理工具。所有输入、输出与临时文件都保留在本机，不调用云端 API。

## 项目版本

当前项目版本：`2.2.0`。版本号属于 DocumentTools 项目，不代表任何第三方依赖版本。

## 转换引擎说明

Office 文档（Word / Excel / PowerPoint）转 PDF 由**本机已安装的 Microsoft Office 或 WPS** 完成：

- DocumentTools 自身不携带、不打包、不附带任何排版引擎、外部可执行文件或运行时。
- 转换通过 COM 自动化在独立辅助进程中完成，**全程不会显示任何 Office/WPS 窗口**。
- 使用前请先安装 Microsoft Office 或 WPS；两者都安装时默认优先使用 Microsoft Office。
- 若本机没有任何可用引擎，DocumentTools 不会进行本地转换，而是提示使用在线转换服务。
- 检测引擎只读取注册表，不会在检测阶段启动任何 Office/WPS 进程。

首次转换时会弹出引擎选择框列出**已检测到**的引擎，可勾选“记住我的选择”，之后可在“设置”页修改。

## 核心特性

- **无捆绑体积**：安装包只包含 Python 运行时与必要依赖，不含文档排版引擎。
- **无窗口转换**：转换过程中不会出现 Word / Excel / PowerPoint / WPS 窗口。
- **故障隔离**：每次转换在独立辅助进程中执行，超时可强制结束，不会拖垮主界面或影响你已打开的文档。

## V2 功能

### 转为 PDF

- 支持 `doc`、`docx`、`ppt`、`pptx`、`xls`、`xlsx` 与图片（jpg/jpeg/png/bmp/tif/tiff）。
- Office 文档由本机 Microsoft Office 或 WPS 转换，排版保真度取决于所安装的引擎版本。
- 图片转 PDF 由本地 Python 组件完成，不需要 Office/WPS。
- 可同时添加多个文件，按列表顺序依次转换；重复文件自动跳过。
- 不支持的格式会记入日志并跳过，不会中断其他文件。

### PDF 工作台

- 排列 PDF：合并、拆分、提取指定页、删除指定页、重排序。
- 编辑 PDF：添加页码、旋转页面、压缩 PDF。
- 压缩提供无损、轻度、平衡、强力四个档位，并使用本地 Python 组件处理。
- 从 PDF 转换：Word、PowerPoint、可识别表格 Excel、逐页 PNG/JPG。
  Word 转换是从 PDF 重建可编辑文档，不是版式还原。
- 页面操作支持后台生成缩略图；只有重排序操作允许拖拽页面。
- 操作参数按当前选择动态显示，不显示无关控件。
- 每个工作区的日志区提供“清除日志”，只清除当前工作区记录。
- 输出日志支持双击打开对应输出文件；文件不存在时显示提示。

### 设置

- 选择转换引擎：自动（Office 优先、失败后尝试 WPS）、仅 Office 或仅 WPS，只列出**已检测到**的引擎。
- 转换超时：单个文件的最长等待时间，超时后强制结束本机转换进程。
- 引擎诊断：显示每个应用的可用性、COM 标识、程序路径与版本，可一键复制用于问题反馈。
- 重新检测引擎：刚安装或升级 Office/WPS 后点一下即可刷新，无需重启程序。
- 在线转换服务：本机没有引擎时，页面上直接列出 Smallpdf、iLovePDF、PDF24 三个在线服务入口。

### 输出与安全规则

- 不覆盖输入文件或已有输出；冲突时自动生成 `文件名 (1).扩展名`。
- 拆分结果放入源文件对应的专用文件夹。
- 加密 PDF 只尝试空密码；需要真实打开密码时明确失败，不猜密码。
- WPS 专有格式 `.wps/.dps/.et` 不在支持范围内。
- PDF 转 Excel 只提取可识别的数字 PDF 表格，不做 OCR。
- PDF 转 Word 默认为简化重建，不保证版式还原。
- 转换前不会修改源文件；带有“来自网络”标记的文件会先复制到临时目录再转换。

## 项目结构

```text
DocumentTools/
├─ main.py                         # 开发/打包入口，同时承载隐藏的 COM 辅助进程模式
├─ src/documenttools/
│  ├─ __init__.py                  # 包版本
│  ├─ __main__.py                  # python -m documenttools 入口
│  ├─ app.py                       # 兼容导出层
│  ├─ conversions.py               # 文件格式转换领域逻辑
│  ├─ engines.py                   # 本机 Office/WPS 检测与调用
│  ├─ office_worker.py             # 隐藏的无窗口 COM 辅助进程
│  ├─ settings.py                  # 配置持久化
│  ├─ paths.py                     # 文件分类和冲突路径
│  ├─ pdf_tools.py                 # PDF 合并、压缩与页面领域逻辑
│  └─ ui/                          # PyQt5 界面
├─ assets/                         # 图标
├─ docs/                           # 架构、开发与变更文档
├─ installer/                      # Inno Setup 定义
├─ scripts/                        # 构建与清理脚本
└─ tests/                          # 公共接口与 UI 回归测试
```

## 开发环境

需要 Windows x64 与 Python 3.13。依赖版本固定在 `requirements.lock`。

```bash
conda env create -f environment.yml
conda activate documenttools
python -m pip install -r requirements.lock
```

开发启动：

```bash
python main.py
# 或
python -m documenttools
```

运行测试：

```bash
python -m pytest
```

在无桌面环境下运行 Qt 测试时，先设置环境变量 `QT_QPA_PLATFORM=offscreen`。

构建脚本可用 `-Environment` 指定用于构建的 Python 环境目录，未指定时使用你本机配置的默认环境：

```powershell
.\scripts\build.ps1 -Environment "<你的 Conda 环境目录>"
```

## 构建与发布

1. 安装 Inno Setup 6 后可自动生成安装包，否则只产出 `dist/DocumentTools`。
2. 构建脚本会自动剔除未使用的重型依赖与任何外部运行时，并在结束后删除 `build/` 中间目录。
3. 安装包内容与 `dist/DocumentTools` 保持一致，全部来源于已验证的构建产物。

发布检查清单见 `docs/DEVELOPMENT.md`。
