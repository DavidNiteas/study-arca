# 发布仓交接

本仓库是 Study Arca 的发布快照，不是开发源。

## 接手顺序

1. 阅读 `README.md` 和 `AGENTS.md`。
2. 从 `docs/README.md` 进入研究规范。
3. 核对 `RELEASE.json` 的版本、来源提交、生成时间和文件哈希。
4. 在 `workspace/` 中创建或接手具体研究项目。

## 修改边界

- 研究项目的问题、证据、分析和交付物在各自项目仓库中维护。
- 框架代码、公共规范、模板和技能的新版本由开发仓生成后发布到本仓。
- 不直接在本仓修改由开发仓生成的公共文件。

## 验证

```powershell
python -m compileall -q src scripts
python scripts/sa.py selftest
```

发布仓的完整目录、命令和研究项目均可独立迁移；外部数据源、凭据和模型读图能力仍需按具体任务核验。

