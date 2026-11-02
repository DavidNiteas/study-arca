# `.agents` · 代理执行入口

本目录只保存代理工具如何执行 Study Arca 任务的入口。产品级权威关系见 [产品组件与资产](../docs/14-产品组件与资产.md)。

## Skills

- [research-cycle](skills/research-cycle/SKILL.md)：专业研究循环。
- [presentation-design](skills/presentation-design/SKILL.md)：研究呈现设计与视觉返修。

## 边界

- 技能是指令和任务路由，不保存当前研究事实。
- 规范权威在 `docs/`；技能只引用，不复制完整 schema。
- 文件骨架在 `templates/`；技能可以引用模板，但不拥有模板。
- `.agents/` 不会被 `sa new` 复制到研究项目。

