# 07 · 呈现与交付

> 原则：**一源三渲染；报告是主干，PPT/HTML 是派生。**

独立报告的内容映射、叙事计划和三格式统一输出契约见 [18](18-报告编排与输出.md)。本文件继续负责交付、PPT 设计与视觉审查规则。
> 呈现材料必须遵守 `docs/01` §8 的中立性：只放事实、推论、对称选项，不替读者决策。

## 1. 派生链

```text
claims / facts / conflicts / datasets / chart specs
                    ↓
            report/document.json
                    ↓
     ┌──────────────┼──────────────┐
  HTML（研究版）   Word（正式版）   PPT（会议版）
  自包含/可交互     归档/签收        一页一主张
```

- `report/`：呈现层工作区，可再生；`document.json` + 生成物。
- `deliverables/`：冻结快照，带版本与 manifest，只读。

## 2. HTML（研究版，P1）

```bash
python scripts/sa.py render build <project>   # Markdown → report/document.json
python scripts/sa.py render html <project>    # document.json → report/index.html
```

独立 HTML 流程：

```bash
python scripts/sa.py experience convert <project> --source report/document.json --snapshot <artifact-id> --plan-id <artifact-id> --output <experience-plan.json>
python scripts/sa.py experience validate <project> --plan <experience-plan.json>
python scripts/sa.py experience build <project> --plan <experience-plan.json> --output <report.html>
```

特性：

- 单文件、离线可开、无 CDN；图片内嵌 base64。
- 三层过滤：事实 / 推论 / 选项。
- 引用 `[^s-0001]` 渲染为可点击链接，右侧抽屉显示来源元数据与链接。
- 搜索、打印/PDF。
- 生成物是可再生的，不作为交付快照；确认交付时冻结到 `deliverables/`。

## 3. Word（正式版，P2）

```bash
python scripts/sa.py render docx <project>   # report/document.json → report/report.docx
```

独立 DOCX 流程：

```bash
python scripts/sa.py document convert <project> --source report/document.json --snapshot <artifact-id> --plan-id <artifact-id> --output <document-plan.json>
python scripts/sa.py document validate <project> --plan <document-plan.json>
python scripts/sa.py document build <project> --plan <document-plan.json> --output <report.docx>
```

- 依赖 `python-docx`（optional extra）；缺失时给出安装提示，不静默失败。
- 目录（TOC 域，打开时自动更新）、引用编号、来源附录、图表编号；数字来自 `facts.json`。
- 样式模板统一：中文正文、标题层级、表格、图注、页脚页码。
- 限制：`python-docx` 不支持原生脚注，引用以上标编号 + 文末“来源与引用”呈现；目录需 Word 更新域。

## 4. PPT（会议版，P3）

- 一页一个主张；标题写结论句，不写“市场分析”。
- 一页一个主张不限制每个分子的页数；复杂机制按[13](13-研究分析与论证.md)展开关键实验与跨文献综合，正文、HTML和PPT都要解释证据怎样支持结论。
- 每页数据来自 `document.json` / `facts.json`；口径与期间放页脚。
- **不设“建议页”**：改为“选项与条件页”——对称呈现路径、成立条件、代价、反证。
- 默认依据 [设计方法与模式](11-PPT设计方法与模式.md) 原创构图，先写设计意图，再落布局 LR。用户明确采用模板时，再让用户看实际预览选择，不默认进入选模板流程。
- PPT 设计与构建只使用 Study Arca 自身规范与工具链：`docs/11`、`presentation-design`、ReportDocument、DeckPlan/RenderLayout 和 `sa deck`。不引入第三方 PPT 技能作为中间层或硬性流程；用户主动指定自己的模板时，按用户要求处理。
- 当前项目级试点为农用杀菌剂演示 v11.1（67 页，DeckPlan/RenderLayout、原生图解、PowerPoint 实际预览与看图返修）；可迁移经验见 [案例](presentation/fungicide-diagrams.md)。项目产物留在独立仓，本路径不是框架内置资源。
- 前一版：`v5.0` 为模板拼页版，保留对比。旧 `sa render pptx` 入口仍不提供；PPT 统一走独立 Deck 流程。
- 通用 `sa deck convert|validate|build` 已提供 DeckPlan/RenderLayout 到原生 PPTX 的可复用路径。
- `sa deck preview` 可选调用本机 PowerPoint 导出逐页 PNG、PDF、文字溢出测量、联系表和全篇总览；核心编译不依赖 PowerPoint COM。

## 5. 交付物快照与发布

```text
deliverables/                  # 内部冻结快照，不直接对外
├── report/v5.0/               # 报告底稿与图表（带 manifest）
└── deck/v6.0/                 # 演示底稿（带 manifest）

publish/                       # 对外发布层，接收方只看这里
├── README.md                  # 发布约定
├── v1.0/                      # 不可变版本目录
│   ├── README.md              # 阅读顺序、口径边界、复核入口
│   ├── 01-研究报告.docx
│   ├── 02-汇报演示.pptx
│   ├── 03-交互报告.html
│   └── manifest.json
├── release/                   # 最新版整目录副本（稳定入口）
└── packed/                    # 用户明确要求后才生成压缩包
    └── p-<project>-v1.0.zip
```

- `publish/vX.Y/` 是**对外交付层**：文件名带序号与中文用途，三份文件复制自冻结快照，哈希必须与源文件一致。
- `publish/release/` 始终等于当前最新版本目录，**整目录复制、不用符号链接**，保证复制、压缩、跨机器打开都不失效。
- **完成报告或版本发布不等于自动生成 zip。** 只有用户明确要求打包时，才执行：

  ```powershell
  python scripts/sa.py pack <project> --version vX.Y
  ```

- 压缩包只落在 `publish/packed/p-<project>-vX.Y.zip`，基于不可变版本目录
  `publish/vX.Y/` 生成；文件名使用 UTF-8，解压后只有一个
  `p-<project>-vX.Y/` 根目录。同名文件默认拒绝覆盖，用户确认替换后才加
  `--force`。
- `publish/` 根目录和 `workspace/` 根目录不再散放 zip。
- 发布层只放成品与说明，不放底稿、脚本或中间图；底稿留在 `report/`、`deck/`，内部快照留在 `deliverables/`。
- 版本目录**只读**：改稿另起 `v1.1`，并同步替换 `release/`；旧版本目录不改。
- manifest 记录版本、日期、as-of、claims 版本、文件 sha256、复核级别；发布层 manifest 另记自包含检查结果（docx/pptx 无 External rels、HTML 无外部资源）。

### 5.1 开发阶段历史归档

发布版本进入稳定阶段后，旧 `v0.x` 开发产物会显著增加工作树噪声。使用以下命令先查看归档计划，再显式执行：

```powershell
sa report archive <project> --id <report-id> --before v1.0
sa report archive <project> --id <report-id> --before v1.0 --apply
sa report archive <project> --id <report-id> --before v1.0 --verify
```

- 默认只做计划，不修改文件；`--apply` 才创建归档并清理旧源。
- 归档位于 `archive/reports/<report-id>/pre-vX.Y-development.zip`，同目录保留 manifest。
- 默认 `--preview-retention summary`：保留每个旧版本的 PPTX、`all-slides-overview.jpg` 和 `measurements.json`；逐页 PNG、联系表与 PDF 视为可由 PPTX 重新生成的派生预览。
- `--preview-retention full` 可保留完整预览，`none` 可只归档 PPTX。
- `--keep-source` 只创建归档、不删除源；同名归档默认拒绝覆盖，替换需 `--force`。
- 归档写入后先校验 ZIP 条目和 SHA-256，校验通过才允许删除源文件。v1.0 当前产物、评审记录和 `publish/` 不进入清理范围。
- `--verify` 可随时复核现有归档的 manifest、ZIP 总哈希和逐文件哈希。
- `archive/**/*.zip` 默认被 Git 忽略；manifest 入库用于记录恢复内容与归档哈希。
- 此机制压缩当前工作树和后续提交噪声，但**不会自动重写已有 Git 历史**。需要缩小 `.git` 历史体积时，另做显式历史维护和备份。

### 5.2 Git 历史维护

历史重写会改变提交哈希，必须由用户明确授权。推荐流程：

1. 先完成开发阶段归档，并关闭所有写操作，确认工作树 clean。
2. 用 `git bundle create --all` 备份完整历史，并通过 `git bundle verify`。
3. 用 `git filter-repo --dry-run` 和明确的路径 glob 检查过滤范围；优先只移除已被发布版本取代、且已进入冷归档的路径。
4. 执行重写后运行 `git fsck --full --strict`，并验证目标旧路径为 0、当前发布路径仍完整。
5. 保存旧/新 HEAD、过滤规则、备份 bundle 哈希和 `commit-map`。
6. 更新 Program superproject 的子模块指针；协作者需要重新 clone 或显式同步新历史。

历史重写不是常规发布步骤。只要远端已经共享旧历史，就必须先协调协作者并明确强制同步要求。

## 6. 交付验收

- [ ] 三种格式的结论、数字、口径一致（以 `facts.json` 为准）
- [ ] 每张图/表可追到 source 或 fact；引用存在
- [ ] 无“建议/推荐/应该/必须/优先做/不做/Go-No-Go”等方向性表达
- [ ] 选项对称，附条件、资源、时间、风险、反证
- [ ] HTML 单文件离线可开；Word 目录/脚注/编号正确；PPT 图形语义、可读性与全篇节奏通过实际看图检查；使用模板时另核许可
- [ ] 快照 `manifest.json` 完整，sha256 可校验
- [ ] 对外交付前已确认密级与引用许可

## 7. 口头简报（10 分钟版）

固定四段：核心发现（2 分钟）→ 关键证据（3 分钟）→ 不确定性与分歧（3 分钟）→ 待决策信息与选项（2 分钟）。从同一套 claim 取材，不另造口径，不替听众做选择。


## 8. 新研究循环的呈现绑定

按 [09](09-专业调研循环.md) 冻结 Research Snapshot，再登记独立 output。PPT 使用 DeckPlan/RenderLayout 原生编译；预览通过 `sa deck preview` 生成逐页图、PDF、测量和联系表。`review` 作为追加事件绑定实际预览 artifact，区分 pending/passed/failed 以及 self/independent。机器测量只能证明产物完整和文字溢出等事实；真实看图仍是视觉通过的前置条件，失败与返修记录不得覆盖。
