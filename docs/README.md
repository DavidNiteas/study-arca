# Study Arca 文档中心

中文 | [English](en/README.md)

这里是面向人的文档入口，也是产品规范的权威索引。第一次使用先读 [00 · 使用指南](00-使用指南.md)；需要精确字段、阶段门或交付规则时，再进入对应规范。

## 先选你的入口

| 你现在的任务 | 从这里开始 |
|---|---|
| 第一次了解 Study Arca | [00 · 使用指南](00-使用指南.md) |
| 新建或判断工作区类型 | [02 · 项目布局](02-项目布局.md)、[15 · 工作区身份、工单与方言](15-工作区身份工单与方言.md) |
| 做外部调研 | [09 · 专业调研循环](09-专业调研循环.md)、[03 · 证据与溯源](03-证据与溯源.md) |
| 分析关键材料并形成判断 | [13 · 研究分析与论证](13-研究分析与论证.md) |
| 整理当前工作、复盘或设计 | [16 · 复盘、设计、对齐与适配输出](16-复盘对齐与适配输出.md)、[17 · 研究协作角色](17-研究协作角色.md) |
| 编排正式 DOCX / HTML / PPT | [18 · 报告编排与输出](18-报告编排与输出.md) |
| 设计或修改研究 PPT | [11 · PPT 设计方法与模式](11-PPT设计方法与模式.md)、[呈现案例库](presentation/README.md) |
| 发布、打包或清理历史版本 | [07 · 交付与 PPT](07-交付与PPT.md) |
| 管理多个工作区或迁移 Program | [15 · 工作区身份、工单与方言](15-工作区身份工单与方言.md) |
| 理解技能、模板、代码和产品资产 | [14 · 产品组件与资产](14-产品组件与资产.md)、[12 · 系统定位与能力管理](12-系统定位与能力管理.md) |
| 接续一个已有代理会话 | [10 · 代理工作协议](10-代理工作协议.md) |
| 创建或编辑正式 Word 报告 | [05 · 报告规范](05-报告规范.md)、[18 · 报告编排与输出](18-报告编排与输出.md) |

## 系统在做什么

```text
Program
  └─ Workspace
       ├─ brief / work-orders / references
       ├─ research 或 synthesis
       ├─ report：ReportPlan → ReportDocument → 成品
       ├─ outputs：输出与审查登记
       ├─ deliverables：冻结快照
       ├─ archive：退役开发历史
       └─ publish：对外发布
```

- Program 是薄索引，只维护下层节点和版本 pin。
- Workspace 是事实、工单、结论和输出的归属单元。
- 正式报告必须从冻结内容派生；PPT 仍保留可编辑原生对象并经过实际渲染验收。
- 发布包、开发历史归档和 Git 历史维护是三个不同动作。

## 规范权威表

冲突时以本表列出的文件为准：左侧为权威规范，技能、模板和 CLI 应服从并指向它。

| 文件 | 回答的问题 | 变更方式 |
|---|---|---|
| [`00-使用指南.md`](00-使用指南.md) | 第一次从哪里开始、任务如何串联 | 随产品入口变化更新 |
| [`01-调研治理.md`](01-调研治理.md) | 研究原则、职责、质量、中立性 | 框架工单 |
| [`02-项目布局.md`](02-项目布局.md) | 工作区与项目目录契约、命名和生命周期 | 框架工单 |
| [`03-证据与溯源.md`](03-证据与溯源.md) | 来源、claim/fact/conflict、证据等级与置信度 | 框架工单 |
| [`04-工作流.md`](04-工作流.md) | 五域循环、讨论回流、补证与交接 | 框架工单 |
| [`05-报告规范.md`](05-报告规范.md) | 报告结构、引用、行文和置信度表达 | 框架工单 |
| [`06-数据源地图.md`](06-数据源地图.md) | 数据源路由、能力边界与已知坑 | 随数据源变化更新 |
| [`07-交付与PPT.md`](07-交付与PPT.md) | 报告呈现、快照、发布、打包、开发归档与 Git 历史维护 | 框架工单 |
| [`08-调研军火库.md`](08-调研军火库.md) | 可接入搜索/抓取 MCP 目录 | 随接入变化更新 |
| [`09-专业调研循环.md`](09-专业调研循环.md) | research 工作区的业务与记录契约 | 框架工单 |
| [`10-代理工作协议.md`](10-代理工作协议.md) | 代理接手、视觉检查与交接 | 框架工单 |
| [`11-PPT设计方法与模式.md`](11-PPT设计方法与模式.md) | 内容关系、设计意图、构图、读图返修与案例沉淀 | 框架工单 |
| [`12-系统定位与能力管理.md`](12-系统定位与能力管理.md) | 工作流、技能、工具与环境的职责边界 | 框架工单 |
| [`13-研究分析与论证.md`](13-研究分析与论证.md) | 从问题、实验、观察和边界形成判断 | 框架工单 |
| [`14-产品组件与资产.md`](14-产品组件与资产.md) | skills、templates、docs、代码与工作区的组合关系 | 产品或开发工单 |
| [`15-工作区身份工单与方言.md`](15-工作区身份工单与方言.md) | 工作区身份、本地工单、引用物化、Program 和方言 | 框架工单 |
| [`16-复盘对齐与适配输出.md`](16-复盘对齐与适配输出.md) | synthesis 的复盘、设计、对齐、基线冻结和适配输出 | 框架工单 |
| [`17-研究协作角色.md`](17-研究协作角色.md) | 首席研究员、主代理双身份、研究顾问委员会和研究专员 | 框架工单 |
| [`18-报告编排与输出.md`](18-报告编排与输出.md) | ReportPlan、ContentMap、NarrativePlan、ReportDocument 与多格式输出 | 框架工单 |

## 快速命令地图

以下 `sa` 是 `python scripts/sa.py` 的命令简写。

```powershell
# 新建工作区（推荐显式指定 Program）
sa new <slug> --title <title> --type research|synthesis --program <path>

# research
sa cycle init|status|lint <workspace>
sa source ... / sa research-ir build|validate|snapshot ...

# synthesis
sa input add <workspace> --file <material>
sa synthesis init|validate|status|apply|alignment|snapshot|build <workspace>

# 报告与输出
sa report init|validate|document|build|register|status <workspace> --id <report-id>
sa deck convert|validate|build|preview <workspace>
sa output init|apply|status|lint <workspace>

# Program 与发布生命周期
sa program init|attach|status|check|index|clone|bundle <path>
sa pack <workspace> --version vX.Y
sa report archive <workspace> --id <report-id> --before vX.Y
```

各命令参数以 `python scripts/sa.py <command> --help` 为准。

## 文档层级

1. **使用指南**：帮助选择入口，不复制权威细节。
2. **权威规范**：定义业务契约、字段、阶段门和交付质量。
3. **代理技能**：定义某类任务的执行路由和最小检查，不复制规范全文。
4. **模板与案例**：提供骨架或有边界的经验，不保存当前研究事实。
5. **研究项目**：真实来源、工作状态、输出与发布记录。

`docs/legacy/` 只保留旧契约与迁移参考，不作为当前实现依据。

## 维护规则

- 新增或修改功能时，同时检查本页入口、对应权威规范、技能、模板和 CLI 帮助。
- 文档中的路径、命令和实现状态必须与当前产品树一致；失效条目当场修正。
- 发布案例必须去项目化，移除项目名、业务对象、版本统计、本地路径、人员信息和未授权截图。
- 硬约束应尽量对应 `sa lint`、schema 校验、阶段门或人工检查单；只有口号没有检查路径的内容，应标为建议。

## 与工程治理内核的关系

- `engineering-governance` 管理工作区的开发工单和角色模型。
- 它不替代专业研究、Synthesis 或报告编排的业务契约。
- 开发仓内部工单不进入产品文档或产品 Git 历史。
