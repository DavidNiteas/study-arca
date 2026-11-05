# Program template

Program 是只引用子节点的 Git superproject，不保存工作区事实。直接子节点使用
Git submodule 挂载到 `nodes/<node-id>/`；版本由 program 提交中的 gitlink 固定。
Program 应位于用户选择的产品目录之外；产品仓不包含默认数据根。

```powershell
python scripts/sa.py program init <path> --id prog-example --title "示例"
python scripts/sa.py new <slug> --title "示例工作区" --program <path>
python scripts/sa.py program attach <program> <workspace> --path nodes/<id>
python scripts/sa.py program status <program>
python scripts/sa.py program check <program>
```

默认 `distribution=local`。只有所有子节点远端和 pin 提交均可取得时，才能设置
`cloneable`。

初始化后的 `bin/program.ps1` / `bin/program.sh` 是薄启动壳，可执行
`status`、`check`、`clone`、`bundle` 等 program 操作。脚本优先使用 `SA_HOME`，
否则向上寻找 Study Arca 的 `scripts/sa.py`。
