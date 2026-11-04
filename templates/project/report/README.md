# report · 呈现层工作区

> 这里是**可再生**的呈现产物；冻结交付件在 `deliverables/report/vX/`。

## 文件

| 文件 | 说明 |
|---|---|
| `document.json` | 结构化文档模型：章节、块、引用、层（fact/inference/option） |
| `index.html` | 自包含 HTML（生成物，可离线打开） |
| `report.docx` | Word（生成物，可选） |
| `deck.pptx` | PPT（生成物，可选） |
| `rpt-NNNN/` | 正式独立报告：ReportPlan、来源映射、格式计划、产物和预览 |

## 规则

- 数字只从 `analysis/findings/facts.json` 取；不在渲染文件里二次录数。
- 每个内容块带 `layer`：`fact` / `inference` / `option`；不放“建议/优先/不做”等方向性内容。
- 引用写成 `[^s-0001]` / `[^f-0001]`，由渲染器解析为可点击链接。
- `report/` 可随时删除重建；确认交付时，把最终文件冻结到 `deliverables/report/vX/` 并写 manifest。

## 当前可用生成命令

```bash
python scripts/sa.py render html <project>
python scripts/sa.py render docx <project>
python scripts/sa.py report init <project> --id rpt-0001 --title "..."
python scripts/sa.py report validate <project> --id rpt-0001
python scripts/sa.py report build <project> --id rpt-0001 --format html
python scripts/sa.py report register <project> --id rpt-0001 --format html
```

正式报告见 [docs/18](../../../docs/18-报告编排与输出.md)。根目录 `document.json` 等文件保留给旧 `synthesis build`/`render` 快捷路径；PPT 正式构建走 `sa report build --format pptx` 与 `sa deck preview`。
