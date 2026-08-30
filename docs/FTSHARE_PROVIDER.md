# FTShare Provider（资格说明）

应用内的 `FTShareProvider` 是默认关闭的只读 HTTP 适配器，不执行
`ftshare-market-data` Skill 脚本，也不接受前端传来的 URL、工具名或 Shell 参数。

固定端点来自固定 Skill commit `cbcfb6283e075fbaa65487a2cb1a75b70c5d4308`（Skill 代码为 MIT；
服务端访问和数据使用受独立 FTShare 条款约束）：

- `GET /api/v1/market/data/etf-description-all`
- `GET /api/v1/market/data/daec/history/ohlcs`
- `GET /api/v1/market/data/daec/history/prices`

默认设置为 `FTSHARE_ENABLED=false`、`FTSHARE_QUALIFICATION=unverified`、
`FTSHARE_BASE_URL=https://market.ft.tech/gateway`、`FTSHARE_ALLOW_CUSTOM_BASE_URL=false`、
20 秒超时、最多 10 页/10,000 条/366 天、响应体最多 2,000,000 字节，并限制页数、记录数和日线日期跨度。响应在进入应用记录前会校验来源元数据（通用
envelope）、代码/日期、OHLC 关系、非负数量、重复和未来时间；空响应、截断、超时、单位或
schema 不符均 fail closed。FTShare 的现价目前始终写作 `is_realtime=false`，并保留降级原因，
直到另行完成可验证的源时间资格。

`scripts/qualify_ftshare.py` 只执行一个有界 ETF 列表、日线和分时只读探测，向 stdout 输出脱敏
JSON。三个探测都必须有记录才会返回成功；失败/拒绝行仍记录有界脱敏耗时和允许的上游错误代码（仅限适配器从结构化响应精确识别的 `UPSTREAM_REJECTED`，绝不解析异常文本），但 `schema_fields`、`unit_findings` 与 `timestamp_findings` 必须为 `null`，绝不从失败响应推断字段、单位或时间口径。成功行只列出已转换的 typed record 字段；单位不会依据字段名或数值形状猜测。该报告不是实时、生产、权限或部署资格证明。

资格探测示例（不会写数据库、修改配置或执行 Skill）：

```bash
python scripts/qualify_ftshare.py --code 510300.SH > ftshare-qualification.json
```

只有在报告中三个 operation 均为 `ok`、记录数大于零，并由运营者确认数据服务额度、许可、缓存和
再分发条款后，才可以在服务器本地 `.env` 将 `FTSHARE_QUALIFICATION=qualified` 与
`FTSHARE_ENABLED=true` 成对设置。出现 `UPSTREAM_REJECTED`、空响应、字段单位不明或 schema
变化时保持 `unverified`/`rejected`；应用会跳过 FTShare，继续使用已配置的公开源，不回退 Mock。
资格报告应保存到受控的部署证据目录，禁止包含 Token、Cookie、账户号、完整响应或私人 URL。

本次本地只读探测证据见 [`ftshare-qualification-2026-08-30.json`](ftshare-qualification-2026-08-30.json)。
探测未取得三项有效记录，因此当前仍为 `unqualified`，不能作为生产启用依据。

Skill 仓库源码未进入本项目、镜像或 API 运行时；应用只重实现固定端点契约。
