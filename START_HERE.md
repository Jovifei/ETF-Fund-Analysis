# 接收入口（2026-10-02）

从这里开始，不要以归档的 v1.0.1 交付说明当作当前产品事实。

## 必读顺序

1. [STATUS.md](STATUS.md) — 当前 main tip、Alembic head、已落地能力与边界  
2. [HANDOFF.md](HANDOFF.md) — 接手动作与保护边界  
3. [docs/README.md](docs/README.md) — 文档地图  
4. [docs/SUPPORT_RESISTANCE_SEMANTICS.md](docs/SUPPORT_RESISTANCE_SEMANTICS.md) — 支撑压力 vs `chan_zone_approx` vs 持久化缠论笔/中枢  
5. [docs/DATA_ACCESS_V101.md](docs/DATA_ACCESS_V101.md) — Provider 与 `etf-flow-share-v1`  
6. [docs/INTRADAY_REFRESH_CADENCE.md](docs/INTRADAY_REFRESH_CADENCE.md) — 仓内盘中槽位（Bot digest ≠ 本仓库功能）

当前工程 tip：`63c426a` · Alembic `f0e1d2c3b4a5` · 真实数据资格 UNKNOWN · 无自动交易。

## 本地只读核对（可选）

```powershell
git fetch origin
git log -1 --oneline origin/main
# 应看到含 R4C / chart layers / flow-share 的合并 tip
```

数据库迁移：`backend` 下 `alembic upgrade head` 的唯一 head 应为 `f0e1d2c3b4a5`。先备份，再迁移。

## 历史交付包

2026-09-07 的 v1.0.1 数据接入交付说明已移入叙事归档语义：仍可在 Git 历史与 `docs/archive/`、`docs/versions/` 查阅，**不覆盖**本页与 STATUS 的当前结论。旧启动示例见 [DATA_ACCESS_V101.md](docs/DATA_ACCESS_V101.md) 与 [QUICKSTART.md](QUICKSTART.md)。
