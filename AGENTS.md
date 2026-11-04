# AGENTS · Study Arca 发布工作区

本文件是发布仓的代理入口。发布仓提供稳定的研究标准、模板、工具和技能；它不是框架开发的编辑场所。

## 读什么

| 你要做的事 | 读 |
|---|---|
| 理解专业调研原则与职责 | `docs/01-调研治理.md` |
| 新建或理解调研项目目录 | `docs/02-项目布局.md` |
| 录入来源、写结论、判置信度 | `docs/03-证据与溯源.md` |
| 分析关键文献、解释实验与形成综合判断 | `docs/13-研究分析与论证.md` |
| 执行五域研究循环 | `docs/09-专业调研循环.md`、`docs/04-工作流.md` |
| 代理接手与视觉验收 | `docs/10-代理工作协议.md` |
| 写报告 | `docs/05-报告规范.md` |
| 出 PPT 或交付 | `docs/07-交付与PPT.md`、`docs/11-PPT设计方法与模式.md` |
| 理解能力边界 | `docs/12-系统定位与能力管理.md` |
| 理解技能、模板、规范与代码的分工 | `docs/14-产品组件与资产.md`、`.agents/README.md`、`templates/README.md` |
| 理解工作区类型、本地工单、引用和方言 | `docs/15-工作区身份工单与方言.md` |
| 执行总结、复盘、对齐或多受众报告 | `docs/16-复盘对齐与适配输出.md` |

## 中立性

对外研究材料只放事实、推论和对称选项，不替客户决策。使用“建议、推荐、应该、必须、优先做、不做、Go/No-Go”等方向性表达前，必须按 `docs/01-调研治理.md` 的规则改写。内部倾向与来源、分析分开保存。

## 环境绑定

- 平台：Windows；Python 3.11，命令使用 `python`。
- 工作区：优先 `work-root/`，迁移期兼容 `workspace/`；每个 `p-*` 项目目录各自一个 Git 仓库。
- 验证：

```powershell
python -m compileall -q src scripts
python scripts/sa.py selftest
python scripts/sa.py lint <project-dir>
```

## 工作区纪律

- `work-root/` 是独立根 program；不把 `work-root/` 内容纳入产品仓，也不把成员工作区合并进同一个 Git 历史。
- 不修改发布仓中的框架文件来承载单个项目特例。
- 项目专用脚本只调用 `scripts/sa.py` 的公开接口。
- 新研究的问题、轮次、讨论和回答以项目 `research/cycle.json` 为准。
- 现代工作区的类型、工单和方言以 `docs/15-工作区身份工单与方言.md` 为准；用户级 `dialect/` 不进入产品 Git 或发布包。
- 总结型工作区必须先复盘和对齐，再由冻结快照适配输出；当前 `sa synthesis build` 不等于完整复盘循环已实现，契约见 `docs/16-复盘对齐与适配输出.md`。
- 研究和呈现完成不等于打包；只有用户明确要求时才运行 `sa pack`，压缩包只进入项目的 `publish/packed/`。

## 发布仓边界

- 发布仓内容由开发仓生成；日常开发、实验和内部治理不在本仓进行。
- 修复框架问题或更新规范应回到开发仓，重建后形成新发布快照。
- `RELEASE.json` 是发布来源、版本和文件完整性的机器可读入口。

## 可用技能

- `research-cycle`：专业研究入口，见 `.agents/skills/research-cycle/SKILL.md`；组件关系见 `docs/14-产品组件与资产.md`。
- `presentation-design`：研究 PPT 的设计、渲染、读图与返修，见 `.agents/skills/presentation-design/SKILL.md`；模板入口见 `templates/README.md`。
- `workspace-system`：工作区类型、本地工单、引用物化和方言边界，见 `.agents/skills/workspace-system/SKILL.md`。
- `engineering-governance`：开发仓中的工单与角色模型；发布仓的研究项目不自动套用工程工单。

