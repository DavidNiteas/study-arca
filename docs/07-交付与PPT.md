# 07 · 呈现与交付

> 原则：**一源三渲染；报告是主干，PPT/HTML 是派生。**
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
- 使用 `gorden-ppt-skill` 时遵守其更新、字数与出框规则；模板仅供个人学习研究。
- 当前项目级试点为农用杀菌剂演示 v7.2（30 页，内容/布局 LR、原生图解、PowerPoint 实际渲染与看图返修）；可迁移经验见 [案例](presentation/fungicide-diagrams.md)。项目产物留在独立仓，本路径不是框架内置资源。
- 前一版：`v5.0` 为模板拼页版，保留对比；`sa render pptx` 尚未集成。
- 通用 `sa deck convert|validate|build` 已提供 DeckPlan/RenderLayout 到原生 PPTX 的可复用路径；实际预览、测量与审查后端仍由呈现流程继续集成。

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
└── p-<project>-v1.0.zip        # 按版本打包
```

- `publish/vX.Y/` 是**对外交付层**：文件名带序号与中文用途，三份文件复制自冻结快照，哈希必须与源文件一致。
- `publish/release/` 始终等于当前最新版本目录，**整目录复制、不用符号链接**，保证复制、压缩、跨机器打开都不失效。
- 每个版本另出 `p-<project>-vX.Y.zip`（UTF-8 文件名，解压为单层目录），便于邮件/IM 发送。
- 发布层只放成品与说明，不放底稿、脚本或中间图；底稿留在 `report/`、`deck/`，内部快照留在 `deliverables/`。
- 版本目录**只读**：改稿另起 `v1.1`，并同步替换 `release/`；旧版本目录不改。
- manifest 记录版本、日期、as-of、claims 版本、文件 sha256、复核级别；发布层 manifest 另记自包含检查结果（docx/pptx 无 External rels、HTML 无外部资源）。

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

按 [09](09-专业调研循环.md) capture 冻结内容、布局、输出和实际预览，再登记 presentation，绑定约定与轮次。visual_review 区分 pending/passed/failed 以及 self/independent。真实看图是视觉通过的前置条件。首页与分簇试验支持布局 LR 到原生 PPT、PowerPoint PNG 和视觉返修；通用 sa render pptx 尚未集成，不将实验能力写成已完成的跨媒介渲染器。
