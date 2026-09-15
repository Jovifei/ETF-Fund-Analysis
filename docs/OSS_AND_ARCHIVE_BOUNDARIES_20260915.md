# 开源使用与 E 盘归档边界

## 实际新增依赖

DuckDB 通过项目可选 archive extra 引入；本轮实际验证版本 1.4.5。新增适配器使用固定 SQL 投影和参数绑定实现本地 Parquet + Zstandard 读写，单线程、禁用扩展自动安装/加载、设置 128MB buffer memory_limit。该参数不等于操作系统总 RSS 硬封顶；正式资源预算仍需现场测量。

官方依据：
- https://duckdb.org/docs/lts/data/parquet/overview
- https://duckdb.org/docs/lts/sql/statements/copy
- https://github.com/duckdb/duckdb/blob/v1.4.5/LICENSE （MIT）

本项目适配器为新增实现；没有整套复制外部网站或交易系统。安装、打包依赖时继续保留其随附 LICENSE/NOTICE；本次交接包不包含第三方二进制或字体。

## 参考而非已移植

Qlib 0.9.6 Data Layer 区分调整价格/factor/缺失数据；其 NaN 和价格基准思想与本项目输入治理相符，本轮没有安装 Qlib 来赋予收益或数据资格。
https://qlib.readthedocs.io/en/v0.9.6/component/data.html

Zipline 的 adjustments writer/reader 对 splits、dividends 和生效日期分层；它是通用公司行动模块后续可参考设计，本轮没有移植完成事件调整器，也没有依据公告批改原库。
https://zipline.ml4trading.io/_modules/zipline/data/adjustments.html

用户此前选择的 TradingAgents、QuantDinger、tick-stock-panel、Vibe、Kairo 等登记继续保留。它们的许可证、固定版本、架构和凭据边界不能因“移植”两字而跳过。本轮没有新增完整外部 Agent 平台、模型权限或自动交易。

## 归档目前真的能做什么

已有 JSONL gzip export → 私有离线读取 → Parquet/ZSTD 转存/筛选 → 带到期请求的签名包 → 离线验证。请求限制一个代码、固定价格基准、最多 5000 行、日期跨度与 TTL；压缩包/展开内容/JSON 结构有界。未知量能保持 NULL，原 source/adjust 保留，外来传输标为 external_archive，不改成可信供应商。

HMAC 验证证明包与密钥持有，不证明来源真实性、单位、复权、完整交易日覆盖或预测有效。当前 verify 不写库，没有 owner 队列、网络请求、消费幂等账本、缓存清理和自动回传。重复离线 verify 是允许的只读行为，不应宣称线上防重放已落地。

真实密钥需独立、安全输入和私有保存；不使用测试固定字节、Codex auth.json、API主密钥或行情Token。本地主动 HTTPS Agent、云端请求授权/签名生命周期、一次性消费与 TTL 缓存、图表落点尚未开发。不得暴露 E 盘共享、同步正在运行的 SQLite 或删除云端计算历史。
