# v106 生产数据验收标准

这份标准用于判断“代码能运行”和“数据可以作为当前研究输入”之间的差异。它不抓行情、不改库、不填补缺失值；输入是项目范围内的脱敏只读 freshness receipt 或备份副本审计结果。

## Gate 0：版本和运行时

| 检查 | 通过条件 | 失败处理 |
|---|---|---|
| API/worker/scheduler 源码 | 三个进程源码清单 hash 与发布 SHA/tree 一致 | 停止部署，不能只看 APP_VERSION |
| 镜像/依赖 | 镜像 ID、Python/Node、前端资源 hash 与收据一致 | 重新封包和验证 |
| 迁移 | Alembic head 与发布合同一致 | 先备份，禁止自动迁移生产 |
| scheduler | 观察窗口无新增 OOM/137/restart，阶段终态可解释 | 返回运行时修复 |

## Gate 1：目标交易日和日线

- 目标交易日必须来自已验证交易日历与 15:15 结算合同。
- 启用 ETF/LOF 集合中每个标的都必须有目标日 OHLC。
- 日期不能未来、不能把抓取时间当源时间。
- OHLC 必须有限、`low <= open/close <= high`。
- `adjust`、source、单位必须属于已核验合同；未知单位只能保留 NULL 并阻断完整量价资格。

## Gate 2：量额和报价

- `volume`/`amount` 缺失不能填 0 后宣布完整。
- 价格-only 记录可以用于价格展示，但必须带 `price_only`/`historical_price_only` 状态。
- 实时发布必须要求 `is_realtime=true` 且 `timestamp_verified=true`。
- 抓取时间、源时间和页面显示时间必须分别保存。
- 未来时间、旧源时间、无源时间均阻断实时资格。

## Gate 3：指标、预测和信号

- 指标 `as_of_date` 必须覆盖目标日，版本/config/schema/input hash 必须一致。
- 预测必须按 1/3/5/10 每个期限单独检查目标日和输入 hash；缺失期限不能补平。
- price-only 或解释不了的价格断点只能产生研究展示，不得生成共享量价信号。
- `partial`/`failed` 任务不能写成 `succeeded`；失败下游必须保持可重试。
- 任意核心输入阻断时 `actionable=false`，不得因页面有数值而提升资格。

## Gate 4：决策板和页面

- 决策快照生成时间必须晚于本次目标日衍生任务；旧快照不得冒充当前快照。
- 分组必须覆盖所有 rows，`数据异常` 必须单独计数，且异常行保留 `grade_reason/data_status`。
- 总览、详情、数据健康页的日期、来源和 freshness 必须一致。
- 桌面 1440/1920/3840 宽度不能出现无意义固定空白；手机 390/430 宽度不能产生 body 横向溢出。
- K 线容器宽度/高度变化后必须触发 chart resize；全屏、缩放、拖拽和移动端抽屉必须回归。

## Gate 5：副本和发布

- 先对生产库和报告做备份，再在副本运行审计。
- 本机真实数据审计退出 3 表示确有阻断；不能通过重试或改标签消除。
- 专用 PostgreSQL、Windows ACL、Parquet、普通/认证浏览器分别记录退出码和跳过原因。
- 任一 Gate 未通过，发布状态为 `blocked`；修复后从失败 Gate 开始重测，再跑必要的组合回归。

## 当前生产判定模板

`scripts/production_data_gate.py` 消费脱敏 `freshness_by_instrument.json`：

```powershell
python scripts/production_data_gate.py `
  --input <freshness_by_instrument.json> `
  --output <gate-result.json> `
  --require-realtime
```

退出码 `0` 只代表所选 Gate 全部通过；退出码 `3` 代表数据阻断，不能解释为程序崩溃。当前生产预期会因缺量额、指标/预测目标日不足和报价非实时而返回 `3`，这是保护行为，不能通过猜单位、填零或删除异常记录来改成通过。
