# Study Arca Documentation Center

[中文](../README.md) | English

This directory is the English-language companion for **human-facing** documentation. Agent-facing instructions remain Chinese-only. The Chinese files remain the canonical normative text when wording differs.

## Choose an entry point

| Task | Start here |
|---|---|
| First use | [Getting started](00-getting-started.md) |
| Workspaces and Programs | [Project layout](02-project-layout.md), [Workspaces and Programs](15-workspaces-and-programs.md) |
| External research | [Research loop](09-research-loop.md), [Evidence and traceability](03-evidence-and-traceability.md) |
| Analysis and argument | [Research analysis](13-analysis-and-argument.md) |
| Review and design | [Synthesis and output](16-synthesis-and-output.md), [Collaboration roles](17-collaboration-roles.md) |
| Reports and PPT | [Report orchestration](18-report-orchestration.md), [PPT design](11-ppt-design.md), [Delivery and PPT](07-delivery-and-ppt.md) |
| Product components | [Product components](14-product-components.md), [System scope](12-system-scope.md) |
| Agent continuation | [Agent protocol](../10-代理工作协议.md) (Chinese only) |

## System model

```text
Program
  └─ Workspace
       ├─ brief / work-orders / references
       ├─ research or synthesis
       ├─ report: ReportPlan → ReportDocument → output
       ├─ outputs: output and review registry
       ├─ deliverables: frozen snapshots
       ├─ archive: retired development history
       └─ publish: external releases
```

- Program is a thin graph of member nodes and commit pins.
- Workspace owns facts, work orders, reports, and outputs.
- Formal reports derive from frozen content.
- PPTX remains editable and must pass real-render visual review.
- Release packaging, development archive, and Git history cleanup are separate actions.

## Documentation set

| Chinese | English |
|---|---|
| [00 · 使用指南](../00-使用指南.md) | [Getting started](00-getting-started.md) |
| [01 · 调研治理](../01-调研治理.md) | [Research principles](01-research-principles.md) |
| [02 · 项目布局](../02-项目布局.md) | [Project layout](02-project-layout.md) |
| [03 · 证据与溯源](../03-证据与溯源.md) | [Evidence and traceability](03-evidence-and-traceability.md) |
| [04 · 工作流](../04-工作流.md) | [Workflow](04-workflow.md) |
| [05 · 报告规范](../05-报告规范.md) | [Report standard](05-reporting.md) |
| [06 · 数据源地图](../06-数据源地图.md) | [Data source map](06-data-source-map.md) |
| [07 · 交付与 PPT](../07-交付与PPT.md) | [Delivery and PPT](07-delivery-and-ppt.md) |
| [08 · 调研军火库](../08-调研军火库.md) | [Research toolbox](08-research-toolbox.md) |
| [09 · 专业调研循环](../09-专业调研循环.md) | [Research loop](09-research-loop.md) |
| [11 · PPT 设计方法](../11-PPT设计方法与模式.md) | [PPT design](11-ppt-design.md) |
| [12 · 系统定位](../12-系统定位与能力管理.md) | [System scope](12-system-scope.md) |
| [13 · 研究分析](../13-研究分析与论证.md) | [Research analysis](13-analysis-and-argument.md) |
| [14 · 产品组件](../14-产品组件与资产.md) | [Product components](14-product-components.md) |
| [15 · 工作区与 Program](../15-工作区身份工单与方言.md) | [Workspaces and Programs](15-workspaces-and-programs.md) |
| [16 · Synthesis](../16-复盘对齐与适配输出.md) | [Synthesis and output](16-synthesis-and-output.md) |
| [17 · 研究协作角色](../17-研究协作角色.md) | [Collaboration roles](17-collaboration-roles.md) |
| [18 · 报告编排](../18-报告编排与输出.md) | [Report orchestration](18-report-orchestration.md) |
| [呈现案例](../presentation/README.md) | [Presentation cases](presentation/README.md) |

## Authority

1. Human guide: navigation and task selection.
2. Normative documents: executable rules, fields, gates, and quality boundaries.
3. Agent skills: task routing and minimum checks.
4. Templates and cases: structures and bounded experience.
5. Workspace: actual sources, state, outputs, and release records.

`docs/legacy/` is retained only for migration reference.

## Maintenance

- Update the entry points, normative document, skill, template, and CLI help together when behavior changes.
- Keep paths, commands, and implementation status aligned with the product tree.
- Cases entering the product repository must be stripped of project identity, objects, version/page statistics, local paths, personnel information, and unauthorized screenshots.
- Hard constraints should map to lint, schema checks, stage gates, or review checklists.
- `AGENTS.md`, `.agents/` skills, and the agent work protocol are agent-facing and stay Chinese-only. Do not add English companions for them.
