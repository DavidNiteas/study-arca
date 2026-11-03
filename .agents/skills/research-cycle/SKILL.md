---
name: research-cycle
description: 在 Study Arca 项目中执行专业调研循环，接手研究问题、补证、分析、讨论反馈与可追溯呈现。适用于已有研究项目和新研究轮次，不用于仓级软件开发工单。
---

# 专业调研循环

本 skill 随 Study Arca 仓库使用。先从当前目录或父目录找到同时包含 scripts/sa.py 与 docs/09-专业调研循环.md 的仓库根；找不到时说明缺少宿主框架，不猜路径或调用其他同名工具。

组件关系见[产品组件与资产](../../../docs/14-产品组件与资产.md)：本 skill 只定义执行路由，规范真源在 `docs/`，文件骨架在 `templates/`，真实研究数据在项目 `workspace/`。

1. 先读[代理工作协议](../../../docs/10-代理工作协议.md)，按本次工作域阅读[专业调研循环](../../../docs/09-专业调研循环.md)的相关段落。它们是权威，不在 skill 复制 schema。
2. 读项目 brief 与 project.json，运行 `python scripts/sa.py status <项目>`；存在 research/cycle.json 时再运行 `python scripts/sa.py cycle status <项目>`。旧项目没有研究循环时，按既有记录接手，不杜撰历史批准或复核。
3. 围绕当前问题与后续任务执行。记录使用 `cycle capture` 冻结材料、`cycle apply --file <记录JSON>` 追加历史；语法见 docs/09，示例见 [records.example.json](../../../templates/research/records.example.json)。
   分析关键文献和综合结论时读[研究分析与论证](../../../docs/13-研究分析与论证.md)，解释研究问题、实验/对照、观察及推理桥梁，不能只列来源、年份和结论。阅读范围不足的细节标未知，不补造实验。
4. 输出按格式分流：DOCX 使用 `sa document convert|validate|build`，HTML 使用 `sa experience convert|validate|build`，PPT 按[PPT 设计方法与模式](../../../docs/11-PPT设计方法与模式.md)和[presentation-design 技能](../presentation-design/SKILL.md)执行。三者只消费冻结 Research Snapshot；旧 `sa render html/docx` 保留兼容。对目标软件生成的最终图片实际看图，再登记 review。文字边界校验不替代看图，self 不冒充 independent。
5. 工作结束运行 `cycle lint` 和项目 `lint`，交接当前约定、轮次、任务 ID 与限制。研究轮次结束与正式发布分开；发布完成也不自动打包，只有用户明确要求时才运行 `sa pack`，产物固定在项目 `publish/packed/`。

只在用户已授权的范围内推进；改变目标、受众或实质范围时记录修订提案。批准凭据是原话转录，不能自动证明人的身份，也不能把无回复当批准。

对外内容保持事实、推论、对称选项；内部讨论和本地材料核对不自动成为外部事实来源。独立角色验收必须由实际独立实例执行。
