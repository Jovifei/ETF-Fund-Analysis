# 开源与原始依据：审核整改

复核日期2026-09-13。此页明确区分原报告、外部新增证据与本项目实现，不从README或测试通过推定收益/数据资格。没有新增整套研究系统的生产运行依赖。

## 公司行动独立于原始价格

- 基金管理人信息披露：https://app.cnstock.com/zzb/zgzqb/html/2026-07/15/nw.D110000zgzqb_20260715_1-B003.htm
  嘉实588200公告列权益登记日2026-07-20、除权日2026-07-21、1:3拆分。原报告未认定原因；这是后续查得的新增资料，不反向更改原报告。并未核验数据库两个价格与量额，未执行复权写入。
- Zipline源码：https://zipline.ml4trading.io/_modules/zipline/data/adjustments.html
  参考SQLiteAdjustmentWriter/Reader将split/dividend、effective/ex/record日期与行情分层的思想。当前落点是拒绝未知价格基准和未解释断点、保留原始数据；完整事件驱动调整器尚未移植，也没有部署Zipline。不能把硬编码某只ETF乘3当作通用方案。
- AKShare官方字段：https://akshare.akfamily.xyz/data/fund/fund_public.html
  固定实际SDK和端点再对字段样本；Sina官方表格与不同实际响应不应用均价容忍度抹平。当前_sina_volume_fields坚持不授予绝对单位资格。

## 隔离与状态工程

- Vibe-Research：https://github.com/simonlin1212/Vibe-Research ，既有固定参考09e8404a33ba0d05e036e01207be4701c61d692c/orchestrator/src/runner.ts。吸收子进程CODEX_HOME、任务版本/超时/事件、实际MCP检查；本项目独立Bridge适配器，不把整个Vibe或其credentials目录放入生产。当前更改落在bridge_runtime、windows_acl与attempt重传状态。完整Vibe真人任务仍待现场。
- Codex认证：https://developers.openai.com/codex/auth/ ，非交互：https://developers.openai.com/codex/noninteractive/ 。官方文档说明本地认证和非交互入口；本项目仍锁定已审版本0.149.0，新文档功能不意味着旧二进制支持。auth.json作为秘密保留本地，不上传或放入Git。认证和费用必须本人批准。
- SQLite官方：https://sqlite.org/wal.html 。WAL并非多写者许可；实现OS文件锁和事务结束释放，在现有SQLite本地模式受控串行写。跨主机业务用PostgreSQL，不增加未经维护的共享SQLite同步系统。

## 用户精心选择的项目继续保留

TradingAgents、QuantDinger、tick-stock-panel、deepseek-harness-quant、KHQuant Skill、Vibe与Kairo的仓库/源码/许可证/实施落点仍见[原登记](../OPEN_SOURCE_ADOPTION_REGISTER_V103.md)、[V104落点](../OSS_APPLIED_V104.md)。本轮没有把它们的前端/策略/密钥机制全量复制并直接获得生产资格。现有参考与隔离脚本保留；证券单位、复权和人工批准不能由外部Agent或框架代为认证。复制具体源码时必须保留对应LICENSE/NOTICE，商业/非自由前端不能按后端许可证处理。
