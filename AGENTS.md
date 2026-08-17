# AGENTS.md

## 项目定位

DocumentTools 是 Windows x64 本地文档处理工具。v1 提供标准 Office/WPS 文档与图片转 PDF、PDF 合并目录/书签/封面、PDF 转 Word/PPT。所有输入和输出都留在本机，不调用云端 API。

## 开发环境

- Conda：`D:\Anaconda\Scripts\conda.exe`，项目环境：`D:\Anaconda\envs\documenttools`。
- Python 3.13、PyQt5/Qt 5.15.2；只在上述环境安装 `requirements.lock` 中的依赖。
- 转换运行时必须随安装包放在 `runtime/libreoffice`，应用不探测或调用系统 Office、WPS、LibreOffice。
- 运行时应从官方发行包获取，并在 `THIRD_PARTY_NOTICES.md` 记录版本、来源和许可证。

## 实现约束

- 不覆盖输入文件；输出冲突自动生成 `文件名 (1).扩展名`。
- WPS 兼容指 WPS 创建的 `doc/docx`、`ppt/pptx`、`xls/xlsx`；不承诺 `.wps/.dps/.et` 专有格式。
- 合并 PDF 只调用 `decrypt("")`，支持可查看但禁止编辑的 PDF；需要真实打开密码时明确失败，不猜密码。
- 合并列表顺序由用户决定；移除、拖拽或按钮排序后自动标题要按位置更新，手工标题保持不变；目录标题支持数字、中文数字、英文字母和无序号初始模板，并可逐行编辑；自动目录页可关闭；检测到源文件开头的视觉目录页时删除它，源电子书签必须同时显示在新目录页和自定义顶级书签下，并重新映射页码。
- 对 `Creator=DocumentTools` 的再次合并必须兼容数值型书签目的地，并按生成目录页数量去重；新生成的目录页必须带 `/DocumentToolsToc` 页面标记，以便元数据被改写后仍可删除旧目录页。
- 页面规格默认统一为 A4 竖版，等比缩放、居中、白边、不裁切；提供 A3/A4/A5/B5/Letter、横竖方向和“保持原始页面规格”。封面和自动目录固定 A4 竖版。
- 任务失败只影响当前任务，界面必须显示可定位的错误原因。

## 验证

使用 `D:\Anaconda\envs\documenttools\python.exe -m pytest` 运行测试。不要提交 `build`、`dist`、`release`、缓存、临时文件或本机配置。
