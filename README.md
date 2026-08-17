# DocumentTools

Windows x64 本地文档工具，安装后即可使用，不要求用户另装 Office、WPS 或 LibreOffice。转换运行时随完整安装包交付。

## 功能

- 标准 Word、WPS 创建的 Word、PPT、Excel 文件和 JPG/JPEG/PNG/BMP/TIFF 转 PDF。
- PDF 合并：拖拽、移除或按钮调整顺序后自动重排目录标题；可选择是否生成目录页；支持数字、中文数字、英文字母和无序号目录标题模板，并允许逐行修改；源 PDF 开头检测到的视觉目录页会删除，其书签会同时成为新目录页和阅读器侧栏中对应顶级条目的下级目录，并使用合并后的页码，可设置 PDF/图片封面。
- DocumentTools 自己生成的带目录 PDF 可以再次作为源文件合并，目录页会被去重，源书签和新页码会同步保留。
- 支持可打开但禁止编辑的加密 PDF：只尝试空密码，不猜测真实密码。
- 合并时可统一到 A3/A4/A5/B5/Letter、自定义宽高，或选择“保持原始页面规格”。
- PDF 转 Word（尽力可编辑）和 PDF 转 PPT（每页一张视觉保真幻灯片）。
- 每个转换任务支持自定义导出文件名，重名自动编号，不覆盖源文件。

## 开发运行

```powershell
& D:\Anaconda\envs\documenttools\python.exe -m pip install -r requirements.lock
& D:\Anaconda\envs\documenttools\python.exe main.py
```

开发目录若没有 `runtime/libreoffice/program/soffice.exe`，Office/WPS 转 PDF 会明确提示运行时缺失；不会改用系统 Office/WPS。

## 打包

将经过审核的 Windows x64 转换运行时放入 `vendor/libreoffice`，然后执行：

```powershell
./scripts/build.ps1
```

安装包包含运行时及 `THIRD_PARTY_NOTICES.md`。复杂字体、宏、动画和 WPS 专有格式可能产生版式差异或失败。
