# Workspace work orders

本目录保存属于当前工作区的本地工单。每个 `wo-*.json` 使用
`sa.work-order/1`，并显式记录唯一 `owner_workspace`。

```powershell
python scripts/sa.py work new <project> --title "任务标题" --goal "目标"
python scripts/sa.py work list <project>
```

其他工作区可以引用这些工单，但引用方必须保存不可变副本；工单正文仍以本工作区为权威。
