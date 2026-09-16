# 第三方组件声明

DocumentTools 本身不含任何文档排版引擎，也不分发转换类可执行文件。
Office 转 PDF 由用户自行安装的 Microsoft Office 或 WPS 通过 COM 自动化完成，
其许可与使用条款由用户与该软件的提供方约定。

## Python 依赖

| 组件 | 版本 | 许可证 | 用途 |
| --- | --- | --- | --- |
| PyQt5 / Qt 5 | 5.15.x | GPL v3 / 商业许可 | 桌面界面 |
| Pillow | 11.x | HPND（MIT 类） | 图片转 PDF |
| pypdf | 5.x | BSD-3-Clause | PDF 合并与页面操作 |
| PyMuPDF | 1.26.x | AGPL v3 / 商业许可 | PDF 解析、渲染、压缩 |
| python-docx | 1.2.x | MIT | PDF 转 Word |
| python-pptx | 1.0.x | MIT | PDF 转 PowerPoint |
| reportlab | 4.x | BSD-3-Clause | 页码与目录页生成 |
| XlsxWriter | 3.x | BSD-2-Clause | PDF 转 Excel |
| pywin32 | 312 | PSF-2.0 | 调用本机 Office/WPS 的 COM 接口 |

## 说明

- 打包时使用的 PyInstaller 仅用于构建，不随应用分发为运行组件。
- 所有第三方组件的许可证原文可在其各自发行包中找到；分发本软件时请一并保留本文件。
- 本项目不包含、不再引用 LibreOffice 运行时，也不包含 pdf2docx、opencv、numpy 或 fonttools。
- Microsoft Office、WPS Office 均为其各自权利人的商标，本软件与其无隶属或背书关系。
