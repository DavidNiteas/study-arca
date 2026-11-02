# 输出登记

本目录使用 `sa.outputs/1` 记录 DOCX、HTML 和 PPT 输出运行。

```powershell
python scripts/sa.py output init <project>
python scripts/sa.py output apply <project> --file <records.json>
python scripts/sa.py output status <project>
python scripts/sa.py output lint <project>
```

`output` 记录绑定 research snapshot、输出请求、计划、布局（如适用）、成品和预览；`review` 记录追加实际阅读/看图后的审查结论。输出记录只引用冻结 artifact，不复制事实台账。

