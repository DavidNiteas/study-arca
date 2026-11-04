# Synthesis records

本目录提供 `sa synthesis apply --file` 使用的记录样例。

- `records.example.json` 展示一轮复盘、问题、回答、修正和对齐记录。
- 示例中的 `u-0001`、`w-0001` 和轮次 ID 必须与实际工作区一致，不能直接当作事实。
- `review`、`correction`、`alignment` 的 `model_sha256` 由 CLI 写入，不需要手工填写。
- 新轮次应声明稳定的 `topic`、可读的 `topic_title` 和 `related_work_items`。
- 对齐事件使用 `items` 逐项记录 `confirmed`、`disputed`、`unknown`、`deferred` 或 `out_of_scope`。
- 对齐关闭后运行 `sa synthesis alignment --round <id>` 生成标准 Markdown 记录。
- 关闭轮次后使用 `sa synthesis snapshot` 冻结工作模型。
- 冻结后由用户决定 `exit`、`continue`、`drill_down` 或 `park`；下钻前可以提供一组带范围、材料、缺口和顺序理由的候选主题，但不得预建轮次。`decision.example.json` 展示下钻决定的格式。
