# 对外发布

这里只放可交付的对外内容：

- `vX.Y/`：不可变版本目录；修改另起版本。
- `release/`：当前最新版本的稳定副本。
- `packed/`：用户明确要求打包后才出现的 zip。

普通研究和呈现完成不等于打包。需要发送压缩包时，在 Study Arca 仓根运行：

```powershell
python scripts/sa.py pack <project> --version vX.Y
```

压缩包名形如 `p-YYYYMMDD-slug-vX.Y.zip`，解压后只有一个
`p-YYYYMMDD-slug-vX.Y/` 根目录。同名文件默认拒绝覆盖；用户确认替换后加
`--force`。
