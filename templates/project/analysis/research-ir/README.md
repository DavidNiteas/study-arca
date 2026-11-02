# Research IR

本目录保存可再生的 Research IR 工作版。输出模块只能消费经 `cycle capture` 冻结的 Research Snapshot。

```powershell
python scripts/sa.py research-ir build <project>
python scripts/sa.py research-ir validate <project>
python scripts/sa.py research-ir validate <project> --check-sources
python scripts/sa.py research-ir snapshot <project> --revision v1 --id a-ir-v1 --label "Research IR v1"
```

Research IR 是来源、研究循环、claim/fact/conflict 和研究叙事的物化投影，不是第二套人工事实源。

