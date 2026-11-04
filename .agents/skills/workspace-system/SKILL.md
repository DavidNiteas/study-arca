---
name: workspace-system
description: 在 Study Arca 中识别工作区类型、创建本地工单、登记用户材料、处理跨工作区引用和分层方言。适用于 workspace 管理，不替代专业调研或总结呈现技能。
---

# Workspace system

先找到同时包含 `scripts/sa.py` 与 `docs/15-工作区身份工单与方言.md` 的 Study Arca 根。

1. 读取目标工作区的 `project.json`，以 `workspace_type` 判断 research 或 synthesis；目录位置不作为类型依据。
2. 工作由哪个 workspace 推进，工单就写入哪个 workspace 的 `work-orders/`，`owner_workspace` 必须一致。不得把工单正文写入 program 或另一个工作区。
3. 用户材料放入 `brief/provided/` 并登记 `manifest.json`。用户指令的第一人称工作记录可以高优先级处理，但外部事实仍按来源和核验状态判断。
4. 跨工作区内容进入分析、汇总或渲染前，必须在当前 workspace 的 `references/` 物化副本。复制不转移证据权威；过程与可信度仍查看目标工作区。
5. Core 硬约束不可被 dialect 覆盖。工作区方言随 workspace 迁移；用户级 `study-arca/dialect/` 不进入 Git 或发布包。影响正式结果的用户方言依赖必须物化到工作区。
6. 不自动启用远端、不自动 push、不自动打包。远端同步范围和打包都由用户显式要求。
7. Program 只保存子节点引用和 Git pin，不保存业务事实；默认 `local`，用户启用远端后才进行 cloneable 检查。
8. Synthesis 按 `docs/16-复盘对齐与适配输出.md` 的管家式协作契约执行：接住用户自然口述，先复述再提出少量高影响问题，允许用户跳过或回答不知道；通过 `sa synthesis apply` 追加复盘-对齐事件，维护 `work-model/model.json`，用 `sa synthesis alignment` 生成标准对齐记录，关闭轮次后用 `sa synthesis snapshot` 冻结，正式呈现用 `sa synthesis build --snapshot`。不得从聊天记忆补写模型没有的工作成果。
9. 用户可把材料放入 `brief/inbox/` 或直接提供路径。`brief/inbox/` 只作暂存，不进入事实模型；代理先盘点并与用户确认，再通过 `sa input add` 登记到 `brief/provided/`。不得擅自扫描未授权路径或修改原件。
10. 工作结束运行相关 `sa lint` 和项目检查，交接工作区类型、工单 ID、引用 ID、方言依赖和限制。

需要理解字段或兼容规则时读[工作区规范](../../../docs/15-工作区身份工单与方言.md)，不在技能中复制 schema。
需要理解复盘、对齐、快照或报告选材时读[复盘对齐规范](../../../docs/16-复盘对齐与适配输出.md)。
