# Synthesis records

本目录提供 `sa synthesis apply --file` 使用的记录样例。

- `records.example.json` 展示一轮复盘、问题、回答、修正和对齐记录。
- 示例中的 `u-0001`、`w-0001` 和轮次 ID 必须与实际工作区一致，不能直接当作事实。
- `review`、`correction`、`alignment` 的 `model_sha256` 由 CLI 写入，不需要手工填写。
- 关闭轮次后使用 `sa synthesis snapshot` 冻结工作模型。
