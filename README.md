# Study Arca · 人类—代理调研协作系统

Study Arca 提供一套可追溯、可复核、可版本化的专业调研工作流。系统把立项、调研、分析、讨论和呈现组织成持续反馈循环，并用来源、结论、冲突和基准事实记录支撑研究表达。

## 快速开始

```powershell
python scripts/sa.py new ai-chip-market --title "AI 芯片市场格局"
python scripts/sa.py lint work-root/nodes/p-*-ai-chip-market
python scripts/sa.py selftest
```

`sa new` 会在项目目录内初始化独立 Git 仓库并写入 `work-root/nodes/`。`work-root/` 是根 program；每个研究项目仍拥有自己的历史和边界。

## 主要能力

- 五域研究循环：立项、调研、分析、讨论、呈现。
- 两类工作区身份：`research` 与 `synthesis`，身份写入工作区元信息。
- Synthesis 的四阶段业务：复盘、对齐、复盘-对齐循环、按受众适配输出。
- 工作区本地工单、用户材料清单、物化引用和作用域方言。
- Program superproject、Git submodule pin 与显式 cloneable 检查。
- Synthesis 工作模型、复盘-对齐记录、标准对齐产物、冻结快照追踪与 HTML/Word 汇总报告生成。
- 来源信封、claim/fact/conflict 台账与置信度校验。
- Markdown 报告、自包含 HTML 和 Word 输出。
- 研究呈现设计方法、内容/布局 LR 与视觉返修流程。
- 按版本发布，并在用户明确要求时显式打包到 `publish/packed/`。
- `research-cycle`、`presentation-design` 等代理工作技能。

## 目录

```text
study-arca/
├── src\                 # 公共 Python 实现
├── scripts\             # 公共 CLI 入口
├── docs\                # 调研与交付规范
├── templates\           # 项目、报告和研究模板
├── .agents\skills\      # 代理执行入口
├── work-root\           # 根 program；成员工作区是独立 Git 子模块
├── LICENSE
├── README.md
├── AGENTS.md
├── HANDOVER.md
└── RELEASE.json
```

## 文档入口

- [`docs/README.md`](docs/README.md)
- [`docs/01-调研治理.md`](docs/01-调研治理.md)
- [`docs/09-专业调研循环.md`](docs/09-专业调研循环.md)
- [`docs/10-代理工作协议.md`](docs/10-代理工作协议.md)
- [`docs/14-产品组件与资产.md`](docs/14-产品组件与资产.md)
- [`docs/15-工作区身份工单与方言.md`](docs/15-工作区身份工单与方言.md)
- [`docs/16-复盘对齐与适配输出.md`](docs/16-复盘对齐与适配输出.md)
- [代理技能索引](.agents/README.md)
- [模板索引](templates/README.md)

## 版本与发布

本仓库是 Study Arca 的产品主仓。开发治理、内部工单和回归测试位于同级的 `study-arca-dev` 开发仓；产品源码、公开规范、模板和技能在本仓维护。版本与文件完整性记录在 [`RELEASE.json`](RELEASE.json)。

研究项目及其证据、分析和交付物保存在各自的 `work-root/nodes/*` 仓库中，不进入本产品仓的 Git 历史。迁移期兼容旧 `workspace/`。

## 许可证

Study Arca 产品代码、规范、模板和技能采用 [MIT License](LICENSE)。

`work-root/` 中的研究项目可能包含第三方材料或单独的许可条款；其许可应分别在对应项目仓库内核验，不因本仓采用 MIT 而自动变更。

