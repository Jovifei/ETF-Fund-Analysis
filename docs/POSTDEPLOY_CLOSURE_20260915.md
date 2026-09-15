# v106 后续修复关闭矩阵

审计依据：用户提供的 2026-09-14 下一阶段只读审计；接续既有 e44e9de，不从旧 main 重建。
固定接收：c219185e608dc95e4d3e82e8142c08a9590eca94；tree c5d13ef4f92d850e58840e66f7447f3d4247ec0c。
本表区分基线已有、此次新增、未提交接线、真实现场未完成。仅代码/测试关闭不等于生产升级和数据资格。

| 审核项 | 代码落点 | 本轮准确状态 |
|---|---|---|
| R01 scheduler 外部终止原因 | runtime_observation.py、runtime_diagnostics.py、scheduler.py | 基线已有阶段观测；真实 137 根因、资源压力和主机事件未现场验证。 |
| R02 收盘独立补跑/full_pipeline | scheduler.py、settlement.py、task_service.py、test_postdeploy_pipeline.py | 基线已有，保留并回归，不重复宣称重写。真实交易周期待验。 |
| R03 无界 latest/历史对象 | decision_board_service.py；本次 data_contract.py、indicator_service.py、forecast_service.py、input_lineage.py | 基线有界 latest/快照清理；新增分标的读取、释放中间帧和复用完整历史 hash。没有截短计算历史，没有宣称生产 RSS 降幅。 |
| R04 ShellCheck/备份 | scripts/backup_postgres.sh | 接手基线已经修复；最终 CI 再验，备份与生产恢复不是同一证据。 |
| C01 静态 self / S-R 读取 | decision_board_service.py、support_resistance_service.py | 基线已有修复与只读读取。 |
| C02 期限转换异常计数 | decision_board_service.py | 基线已有，保持分组不丢异常。 |
| C03 源时间/今日涨幅 | return_observation.py、decision_board_service.py | 基线已区分源时间与抓取时间；运行资产是否同版仍需现场检查。 |
| C04 版本/日期一致性 | snapshot_contract.py、workspace/read_model.py | 本轮将基线守卫接入详情指标/预测，暴露多日期和缺口；历史图表仍独立显示。 |
| C05 空预测与重新锚定 | decision_board_service.py、read_model.py | 基线修空情景；本轮详情仅用通过合同的预测构造情景。 |
| C06 月研究/相关性断点 | research_outlook.py、read_model.py | 新增价格连续性、未知基准拒绝、NaN 量额、同日修订缓存失效，异常相关性为空。未实现通用公司行动调整器。 |
| C07 支撑压力缺量额 | support_resistance_service.py | 基线守卫保留；未放宽量额认证。 |
| C08/C09 前端误解读 | decision_board_workbuddy.js | 精确识别下破；缺失数值不落入 KDJ/RSI 数值阈值；仅展示评分变更，不改 canonical action。 |
| C10 有缓存掩盖连接错 | decision_board_embed.js | 新增错误与缓存独立状态；旧模板与宿主消息来源检查保留。 |
| C11 任务摘要/健康页 | task_summary.py、data_health.py、DataHealth.vue | 健康页显示目标覆盖和安全摘要；worker 委托接线写入被拦截，因此 TaskProgress 端尚未完全关闭。 |
| settings 路由接线 | workspace/api.py | 整文件写入被拦截，未提交；read 默认设置路径仍在，不把本地候选结果当远端事实。 |
| F01 真实来源、复权 | providers、价格合同及外部数据证据 | 正确拒绝坏数据不等于修复真实数据；Sina 绝对量额、拆分/分红调整序列与 14:30 PIT/OOS 仍待。 |
| F02 E 盘冷数据 | archive_protocol/store/parquet、archive_local.py | 已实现离线私有包、HMAC、大小/期限/字段校验、Parquet ZSTD 查询；在线队列/轮询/消费账本/TTL/自动回取未实现。 |
| 真实 AI/OCR/分钟资格 | 既有 Bridge、AI profiles、OCR、market_bars | 保留接口与门禁，无本人登录、实际费用、真实数据资格或生产启用声明。 |

## 回归与原结论修正

1. 报告中“480 分钟徽标”与固定源码的 8 分钟 + 后端 freshness 判定不一致；未盲改已有正确逻辑。需核对实际挂载的资产哈希和页面路径。
2. 健康检查、HTTP 200、任务写出记录、异常数量减少不是数据认证；本次不会把缺失量能重新填 0、用比值认证单位或把 588200 价格乘 3。
3. 云端历史不能为了“冷存储”直接裁成 250–300 根；当前算法输入历史和 hash 合同不允许这样悄悄改变。
4. Windows 测试只对新建一次性目录配置 ACL；已有宽 ACL 必须拒绝且不修改。CI 路径不代表用户 E 盘现场。
5. 测试矩阵以最终固定提交为准；早期本地全量使用了两个未提交接线，属于不同树，单独记账。
