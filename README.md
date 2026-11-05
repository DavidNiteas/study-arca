# Study Arca · 信息资产工程系统

Study Arca 把研究信息当作**可寻址、可引用、可验证、可版本化的信息资产**，并通过受约束的工具链，把这些资产投影为报告、演示、网页和其他可交付产物。

它不只管理“文档”，而是管理信息从来源、理解、设计、冻结、编排到发布的整个生命周期。

## 核心思想

```text
材料、证据与工作记录
        ↓ 规范化
工作状态 / Research IR
        ↓ 对齐与冻结
Snapshot
        ↓ 受众与叙事适配
ReportPlan / ContentMap / NarrativePlan
        ↓ 编译
ReportDocument
        ↓ 展示后端
DeckPlan + RenderLayout
        ↓
DOCX / HTML / PPTX
        ↓ 审查与登记
Output / Review / Manifest
        ↓
Deliverable / Publish / Archive
```

可以把这套关系理解为信息工程版的“源码 → 类型系统 → 中间表示 → 构建计划 → 编译器后端 → 构建产物”。

| 软件工程概念 | Study Arca |
|---|---|
| 源码 | 材料、来源、工作记录、设计记录 |
| 依赖 | 跨工作区引用、外部数据、材料哈希 |
| 类型系统 | 事实、推断、未知、冲突、来源、权威与置信层 |
| 静态分析 | `sa lint`、`synthesis validate`、`report validate`、引用与哈希校验 |
| 中间表示 | Research IR、Work Model、Work Snapshot、ReportDocument |
| 构建清单 | ReportPlan、ContentMap、NarrativePlan |
| 代码生成 IR | DeckPlan、RenderLayout |
| 编译器后端 | DOCX、HTML、PPTX 渲染器 |
| 构建溯源 | output registry、review、manifest |
| 发布物 | `deliverables/`、`publish/` |
| 工作区 / 包 | 一个 `p-*` Workspace |
| 工作区依赖图 | Program |
| 本地编译配置 | 用户方言、工作区方言 |

## 三个核心对象

### Program

Program 是薄索引，只负责组织下层 Workspace 和记录版本 pin。它不承载来源、结论、工单、报告或输出。

### Workspace

Workspace 是事实和输出的归属单元，分为：

- `research`：面向外部问题的调研、分析与论证；
- `synthesis`：面向自身工作的复盘、设计与对齐。

材料、工单、引用、快照、报告和发布物都必须有明确归属。

### Information IR

信息在进入输出前，必须形成可检查的中间表示：

- 什么被观察到；
- 谁提供或发布了它；
- 哪部分是事实、推断、未知或争议；
- 哪些对象和关系被建立；
- 当前结论依赖哪些快照与版本。

不同格式可以改变叙事、详略和表达方式，不能静默改变信息本身。

## `sa` 是什么？

`sa` 是 Study Arca 的**信息语言服务、校验器和构建编排器**。

它负责：

- 创建和验证 Workspace、Program 与本地工单；
- 解析材料、来源、引用和版本依赖；
- 检查 schema、证据链、阶段门与发布边界；
- 冻结 Snapshot 和 Research IR；
- 编排 ReportPlan、ReportDocument 与多格式输出；
- 编译 DeckPlan/RenderLayout 为原生 PPTX；
- 登记输出、预览、审查和发布。

`Pylance` 是 `sa` 的一个重要类比，但不是全部。更完整的说法是：

> `sa` = 信息语言服务 + 静态检查器 + 依赖解析器 + 构建系统。

## Deck 是什么？

Deck 是面向人类受众的展示编译器后端之一。

```text
Snapshot
→ ReportPlan / NarrativePlan
→ ReportDocument
→ DeckPlan + RenderLayout
→ PPTX
```

PPT 编译是有设计的压缩，不是无损复制。编译器必须保证被释放的事实、证据关系、未知和限制保持语义一致，同时记录受众、披露范围、省略内容、渲染环境和视觉审查状态。

## 主要能力

- Research 与 Synthesis 两种工作区身份；
- 材料登记、哈希校验、跨工作区引用物化和作用域方言；
- 复盘、设计、对齐、顾问委员会、研究专员和知识/设计基线；
- 来源台账、claim/fact/conflict、Research IR 和冻结 Snapshot；
- ReportPlan、ContentMap、NarrativePlan、ReportDocument；
- DOCX、自包含 HTML 和原生 PPTX 输出；
- DeckPlan/RenderLayout、PowerPoint 实际渲染、逐页测量和看图返修；
- 输出登记、审查记录、不可变发布目录和稳定 release 副本；
- 发布压缩包、开发历史冷归档和 Git 历史维护；
- 面向人的使用指南、规范中心、代理技能、模板和案例；
- Program 子模块、递归 cloneable 检查和离线迁移包。

## 快速开始

```powershell
# 新建 research 工作区
python scripts/sa.py new market-scan --title "市场扫描" --type research

# 新建 synthesis 工作区
python scripts/sa.py new project-review --title "阶段复盘" --type synthesis

# 查看工具能力
python scripts/sa.py --help
python scripts/sa.py report --help
python scripts/sa.py synthesis --help
python scripts/sa.py deck --help

# 产品自检
python scripts/sa.py selftest
```

`sa new` 默认把工作区创建在 `work-root/nodes/`，并为每个工作区建立独立 Git 仓库。根 `work-root/` 本身是 Program。

## 典型流程

### 外部研究

```powershell
python scripts/sa.py cycle init <workspace>
python scripts/sa.py source <workspace> --title "..."
python scripts/sa.py research-ir build|validate|snapshot <workspace>
python scripts/sa.py lint <workspace>
```

### 复盘与设计

```powershell
python scripts/sa.py input add <workspace> --file <material>
python scripts/sa.py synthesis init|status|apply|alignment|snapshot|build <workspace>
python scripts/sa.py synthesis validate <workspace>
```

### 正式报告与 PPT

```powershell
python scripts/sa.py report init <workspace> --id rpt-0001 --title "报告标题"
python scripts/sa.py report build <workspace> --id rpt-0001 --format pptx
python scripts/sa.py deck validate <workspace> --plan <plan.json> --layout <layout.json>
python scripts/sa.py deck build <workspace> --plan <plan.json> --layout <layout.json> --output <deck.pptx>
python scripts/sa.py deck preview <workspace> --pptx <deck.pptx> --out-dir <preview-dir>
python scripts/sa.py output lint <workspace>
```

### 发布与历史治理

```powershell
# 对外交付包：仅由用户明确触发
python scripts/sa.py pack <workspace> --version v1.0

# 开发历史归档：默认先计划
python scripts/sa.py report archive <workspace> --id rpt-0001 --before v1.0
python scripts/sa.py report archive <workspace> --id rpt-0001 --before v1.0 --apply
python scripts/sa.py report archive <workspace> --id rpt-0001 --before v1.0 --verify
```

## 设计边界

- **编译器成功不等于事实为真。** `sa` 保证结构、引用、完整性和投影一致性；科学事实仍需来源、分析与人工复核。
- **不同输出可以取舍，但不能篡改。** 受众适配可以删减、概括或脱敏，但必须保留影响理解的未知、限制与证据边界。
- **材料是依赖，不是结论。** 研究结论必须说明它来自用户陈述、原始材料、代理推断还是未知。
- **快照是构建输入。** 正式输出绑定冻结版本，不从仍会变化的聊天记忆或工作草案直接生成。
- **发布是独立动作。** 生成、打包、发布和历史清理各有自己的授权与校验边界。
- **workspace 是独立仓库。** 产品仓不承载真实研究内容；Program 只保存成员关系和版本 pin。

## 文档入口

- [面向人的使用指南](docs/00-使用指南.md)
- [文档中心与权威索引](docs/README.md)
- [项目布局](docs/02-项目布局.md)
- [证据与溯源](docs/03-证据与溯源.md)
- [Research 循环](docs/09-专业调研循环.md)
- [复盘、设计、对齐与适配输出](docs/16-复盘对齐与适配输出.md)
- [研究协作角色](docs/17-研究协作角色.md)
- [报告编排与输出](docs/18-报告编排与输出.md)
- [PPT 设计方法与模式](docs/11-PPT设计方法与模式.md)
- [交付、发布与历史维护](docs/07-交付与PPT.md)
- [代理技能索引](.agents/README.md)
- [模板索引](templates/README.md)

## 仓库结构

```text
study-arca/
├── src/                 # 信息模型、校验、编排与渲染实现
├── scripts/             # 公共 CLI 入口
├── docs/                # 人类文档与权威规范
├── templates/           # 项目、报告、PPT 与研究模板
├── .agents/skills/      # 代理任务入口
├── work-root/           # 本地根 Program；项目是独立 Git 子模块
├── LICENSE
├── README.md
├── AGENTS.md
├── HANDOVER.md
└── RELEASE.json
```

`work-root/` 由根 `.gitignore` 排除，不属于产品 Git 历史。研究项目中的第三方材料和数据可能适用单独许可，需在各自项目中核验。

## 版本与发布

产品版本记录在 [`VERSION`](VERSION)，文件完整性、产品树哈希和仓库元数据记录在 [`RELEASE.json`](RELEASE.json)。产品开发与内部工单位于同级的 `study-arca-dev` 开发仓；本仓只保存发布后的规范、源码、模板和技能。

## 许可证

Study Arca 产品代码、规范、模板和技能采用 [MIT License](LICENSE)。
