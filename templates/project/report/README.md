# report · 呈现层工作区

> 这里是**可再生**的呈现产物；冻结交付件在 `deliverables/report/vX/`。

## 文件

| 文件 | 说明 |
|---|---|
| `document.json` | 结构化文档模型：章节、块、引用、层（fact/inference/option） |
| `index.html` | 自包含 HTML（生成物，可离线打开） |
| `report.docx` | Word（生成物，可选） |
| `deck.pptx` | PPT（生成物，可选） |

## 规则

- 数字只从 `analysis/findings/facts.json` 取；不在渲染文件里二次录数。
- 每个内容块带 `layer`：`fact` / `inference` / `option`；不放“建议/优先/不做”等方向性内容。
- 引用写成 `[^s-0001]` / `[^f-0001]`，由渲染器解析为可点击链接。
- `report/` 可随时删除重建；确认交付时，把最终文件冻结到 `deliverables/report/vX/` 并写 manifest。

## 当前可用生成命令

```bash
python scripts/sa.py render html <project>
python scripts/sa.py render docx <project>
```

通用 sa render pptx 尚未实现；当前 PPT 布局适配器为仓级呈现实验。新循环用 cycle capture 冻结内容、布局、成品、预览，再登记 presentation 与实际视觉审查；工作文件可重建的前提是相关输入已保留。
