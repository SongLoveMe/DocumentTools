# Embedded conversion runtime

这是内置转换运行时的占位目录。发布前必须放入经过审核的官方 Windows x64 LibreOffice 发行包，并确认：

```text
vendor/libreoffice/program/soffice.exe
```

构建脚本会将该目录复制到安装包的 `runtime/libreoffice`。应用只使用随包交付的运行时，不探测机器级 Office、WPS 或 LibreOffice。

每次发布前请在 `THIRD_PARTY_NOTICES.md` 或发行记录中补充实际 LibreOffice 版本、下载来源、SHA-256 和原始许可证文件。不要把 WPS/Microsoft Office 文件放入此目录，也不要提交构建生成物。
