# Study Arca · 人类—代理调研协作系统

Study Arca 提供一套可追溯、可复核、可版本化的专业调研工作流。系统把立项、调研、分析、讨论和呈现组织成持续反馈循环，并用来源、结论、冲突和基准事实记录支撑研究表达。

## 快速开始

```powershell
python scripts/sa.py new ai-chip-market --title "AI 芯片市场格局"
python scripts/sa.py lint workspace/p-*-ai-chip-market
python scripts/sa.py selftest
```

`sa new` 会在项目目录内初始化独立 Git 仓库。`workspace/` 根目录不是仓库，每个研究项目拥有自己的历史和边界。

## 主要能力

- 五域研究循环：立项、调研、分析、讨论、呈现。
- 来源信封、claim/fact/conflict 台账与置信度校验。
- Markdown 报告、自包含 HTML 和 Word 输出。
- 研究呈现设计方法、内容/布局 LR 与视觉返修流程。
- `research-cycle`、`presentation-design` 等代理工作技能。

## 目录

```text
study-arca/
├── src\                 # 公共 Python 实现
├── scripts\             # 公共 CLI 入口
├── docs\                # 调研与交付规范
├── templates\           # 项目、报告和研究模板
├── .agents\skills\      # 代理执行入口
├── workspace\           # 独立研究项目工作区
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

## 版本与发布

本仓库是发布快照，不作为日常开发工作区。版本、生成时间和来源开发提交记录在 [`RELEASE.json`](RELEASE.json)。修改研究规范、工具或技能应进入开发仓完成，再重新生成发布快照。

研究项目及其证据、分析和交付物保存在各自的 `workspace/p-*` 仓库中，不隶属于本发布仓。

