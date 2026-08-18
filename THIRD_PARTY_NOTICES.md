# Third-party notices

发行包必须同时携带各组件的原始许可证和归属信息。本文件记录项目锁定版本和上游入口；发布前还要把对应许可证原文放入安装包。

| 组件 | 版本 | 用途 | 上游入口 |
| --- | --- | --- | --- |
| Python | 3.13 | 运行时 | <https://www.python.org/> |
| PyQt5 / Qt | 5.15.10 / Qt 5.15.2 | Windows GUI | <https://pypi.org/project/PyQt5/> |
| pypdf | 5.9.0 | PDF 读写、书签和目录 | <https://pypi.org/project/pypdf/> |
| PyMuPDF | 1.26.3 | PDF 页面渲染 | <https://pypi.org/project/PyMuPDF/> |
| pdf2docx | 0.5.8 | PDF 转 Word | <https://pypi.org/project/pdf2docx/> |
| python-pptx | 1.0.2 | PDF 转 PPT | <https://pypi.org/project/python-pptx/> |
| python-docx | 1.2.0 | Office 文档依赖 | <https://pypi.org/project/python-docx/> |
| Pillow | Conda 环境版本 | 图片读取和图片转 PDF | <https://pypi.org/project/Pillow/> |
| reportlab | 4.4.2 | 自动目录页和测试夹具 | <https://pypi.org/project/reportlab/> |
| PyInstaller | 6.15.0 | Windows 可执行文件打包 | <https://pypi.org/project/PyInstaller/> |
| LibreOffice | 发行包实际版本 | 内置 Office/WPS 转 PDF 运行时 | <https://www.libreoffice.org/> |

## 许可证交付要求

- `requirements.lock` 中的 Python 包按各自上游许可证交付。
- PyQt5/Qt 的许可和归属信息随 PyQt5/Qt 发行包交付。
- LibreOffice 必须使用官方 Windows x64 发行包，并记录实际版本、下载地址、SHA-256 和原始许可证文件；当前仓库只保留 `vendor/libreoffice/README.md` 占位说明。
- DocumentTools 不依赖系统 Office、WPS 或系统 LibreOffice，也不会上传用户文档。
