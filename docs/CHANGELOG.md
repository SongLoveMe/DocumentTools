# Changelog

## 2.2.0 - 2026-09-16

- 上一版 2.2.0 采用纯 Python 进程内排版，实际转换效果未达预期，本版整体推翻并重新实现。
- 移除 `office_pdf.py`、`fonts.py`、随包中文字体子集与字体生成脚本；项目不再包含任何自制排版引擎。
- Office 转 PDF 改为通过 COM 自动化调用用户本机已安装的 Microsoft Office 或 WPS。
- 引擎检测只读取注册表，不启动任何进程；WPS 会注册 Microsoft ProgID，因此按解析到的可执行文件判定归属。
- 转换在独立辅助进程中执行，支持超时强杀；Word/Excel 使用 `Visible=False`，PowerPoint 使用 `WithWindow=False`，全程无窗口。
- 未检测到本机引擎时不进行本地转换，改为弹出在线转换引导（Smallpdf、iLovePDF、PDF24）并可复制诊断信息。
- 重新支持旧版格式 `doc`、`ppt`、`xls`；`.wps/.dps/.et` 仍不支持。
- 新增“设置”页：引擎选择（只列已检测到的引擎）、转换超时与引擎诊断。
- 移除 PDF/A 选项，以及设置页中的 PDF 转 Word 后端选项。
- 引擎诊断新增“重新检测引擎”按钮，安装或升级 Office/WPS 后无需重启程序。
- 设置页写明显式列出 Smallpdf、iLovePDF、PDF24 三个在线转换服务入口。
- PDF 转 Word 默认保持纯 Python 重建，并新增可选的本机引擎重流后端（实验性，失败自动回退）。
- 依赖统一到 `requirements.lock`，新增 `PyQt5`、`Pillow`、`pytest`、`pywin32`，移除 `openpyxl` 与 `fonttools`。
- 删除 `vendor/`、`DocumentTools.spec` 与不再使用的字体资源，构建脚本改为排除 pywin32 中不需要的子模块。
- 重写 README、架构与开发文档，移除所有与本机环境绑定的绝对路径。

## 2.1.1 - 2026-09-15

- 修复源码模式查找 `vendor/libreoffice` 运行时失败的问题，并列出实际查找路径。
- 新增可审计的运行时锁文件、离线准备脚本、SHA-256 校验、构建复制与转换烟雾测试。

## 2.1.0 - 2026-09-12

- 新增本地 Python PDF 压缩，提供无损、轻度、平衡和强力四档预设。
- 新增本地压缩大小预估和实际压缩结果记录。
- 统一各工作区的输出目录控件和操作区布局。
- 新增每个工作区的“清除日志”，清除操作不会自动发生，也不影响其他工作区。
- 统一日志区、主操作按钮和中文提示，并在 `AGENTS.md` 增加 UI 统一规范。
