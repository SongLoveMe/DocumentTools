# DocumentTools

DocumentTools 是 Windows x64 本地文档处理工具。输入文件、临时文件和输出文件默认都留在本机，不调用云端 API，也不会探测或调用系统 Office、WPS 或 LibreOffice。

## v1 功能

- Office/WPS 创建的 `doc`、`docx`、`ppt`、`pptx`、`xls`、`xlsx`，以及 `jpg`、`jpeg`、`png`、`bmp`、`tif`、`tiff` 转 PDF。
- PDF 合并：按用户列表顺序合并，支持封面、目录页、源电子书签、目录标题模板、页面规格统一和保持原始页面规格。
- 合并 PDF 时，源文件开头可识别的视觉目录页会删除；源书签会挂到对应的自定义顶级目录下，并按合并后的页码重新映射。
- DocumentTools 生成的多页目录 PDF 可再次作为源文件合并，所有标记的旧目录页会去重，不会重复出现在正文中。
- PDF 转 Word（尽力保持可编辑）和 PDF 转 PPT（每页一张视觉保真幻灯片）。
- 输出文件不覆盖输入文件；同名输出自动生成 `文件名 (1).扩展名`。

不承诺 WPS 专有的 `.wps`、`.dps`、`.et` 格式，也不保证复杂字体、宏、动画或特殊版式完全一致。

## 开发环境

项目使用 Conda 环境 `documenttools`，Python 3.13、PyQt5/Qt 5.15.2。依赖分为两部分：`environment.yml` 提供 Conda/Qt 基础环境，`requirements.lock` 锁定 Python 包版本。

```powershell
D:\Anaconda\Scripts\conda.exe env update -f environment.yml
& D:\Anaconda\envs\documenttools\python.exe -m pip install -r requirements.lock
```

启动开发版：

```powershell
& D:\Anaconda\envs\documenttools\python.exe main.py
```

开发目录若没有 `vendor/libreoffice/program/soffice.exe`，Office/WPS 转 PDF 会显示运行时缺失；不会回退到系统 Office、WPS 或 LibreOffice。

## 测试

```powershell
& D:\Anaconda\envs\documenttools\python.exe -m pytest
```

测试覆盖路径分类和冲突命名、图片/PDF 转换、Qt 合并列表交互，以及 PDF 合并目录、书签、页码、加密和页面规格行为。

## 打包发布

1. 将经过审核的 Windows x64 LibreOffice 官方发行包放入 `vendor/libreoffice`，并确认存在 `program/soffice.exe`。
2. 在隔离环境中安装 `requirements.lock`。
3. 执行：

   ```powershell
   .\scripts\build.ps1
   ```

PyInstaller 输出到 `dist`；若安装了 Inno Setup 6，安装包输出到 `release`。这些目录只用于本地构建，不能提交到版本库。发行包必须同时包含 `THIRD_PARTY_NOTICES.md` 和 LibreOffice 原始许可证/归属文件。

## 项目结构

```text
DocumentTools/
├─ src/documenttools/       # 应用界面、转换、路径和 PDF 领域模块
├─ tests/                   # 与公共模块接口对应的测试
├─ scripts/                 # 图标生成和 Windows 打包脚本
├─ installer/               # Inno Setup 安装包定义
├─ vendor/libreoffice/      # 本地开发/发布使用的内置转换运行时占位目录
├─ assets/                  # 应用图标等静态资源
├─ docs/                    # 项目结构和维护说明
└─ main.py                  # 开发版启动入口
```

## 维护约束

- 不覆盖输入文件；单个任务失败不能影响同批次其他任务。
- 合并加密 PDF 只尝试空密码；真实打开密码必须明确失败。
- 生成目录页固定 A4 竖版，正文页默认 A4 竖版并等比缩放、居中、留白、不裁切。
- 不提交 `build`、`dist`、`release`、缓存、临时文件或本机配置。
