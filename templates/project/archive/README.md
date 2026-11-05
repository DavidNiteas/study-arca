# archive · 历史开发归档

本目录保存被新发布阶段取代、但仍可能需要本地恢复的开发历史。

- `reports/<report-id>/pre-vX.Y-development.zip`：压缩恢复包，默认不进入 Git。
- `reports/<report-id>/pre-vX.Y-development.manifest.json`：保留文件清单、源 SHA-256、归档 SHA-256、删除范围和省略策略。
- `reports/<report-id>/pre-history-rewrite-vX.Y.bundle`：Git 历史重写前的完整仓库恢复包，默认不进入 Git。
- 当前正式发布始终以 `publish/` 为准，本目录不作为当前研究事实来源。

默认先生成计划，确认后执行：

```powershell
python scripts/sa.py report archive <project> --id <report-id> --before v1.0
python scripts/sa.py report archive <project> --id <report-id> --before v1.0 --apply
python scripts/sa.py report archive <project> --id <report-id> --before v1.0 --verify
```

`--apply` 只有在归档写入且逐文件校验通过后才会删除旧开发源。压缩包不入 Git 只减少后续工作树与提交体积；已有 Git 历史中的对象仍需单独、显式地做历史维护。
