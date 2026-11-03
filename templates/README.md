# Templates · 文件与项目骨架

本目录保存 `sa new`、报告写作、PPT 设计和文献分析所使用的结构模板。产品级权威关系见 [产品组件与资产](../docs/14-产品组件与资产.md)。

## 目录

| 目录 | 内容 |
|---|---|
| [project/](project/) | 新调研项目的完整初始目录、元数据、台账和发布/打包骨架 |
| [report/](report/) | Markdown 报告初稿结构 |
| [ppt/](ppt/) | PPT 大纲、设计意图、设计案例记录 |
| [research/](research/) | 关键论文分析与研究循环记录样例 |
| [output/](output/) | 输出请求、三种 Output Plan、Render Layout 与登记记录样例 |
| [dialect/](dialect/) | 用户级本地方言的起始清单；不会被复制进产品发布历史 |
| [program/](program/) | Program superproject 的最小清单与操作说明 |

## 规则

- 模板只提供结构和占位符，不保存真实研究结论。
- `templates/project/` 由 `sa new` 复制并替换占位符。
- `templates/project/_dev/` 是研究项目内部兼容模板，不是开发仓治理目录。
- 修改项目骨架时必须同步检查 `src/sa/project.py`、`tests/` 和 [docs/02-项目布局.md](../docs/02-项目布局.md)。
- PPT 模板由 [presentation-design 技能](../.agents/skills/presentation-design/SKILL.md) 使用；规范和案例入口见 [docs/11-PPT设计方法与模式.md](../docs/11-PPT设计方法与模式.md)。

