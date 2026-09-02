# PR 准备清单

两个待合并分支，均由我（WorkBuddy）基于 main 提交，改动已本地验证 + 推送到远端。PR 由你在 GitHub 网页创建。

---

## PR 1：`fix-docker-egginfo-ci-smoke`（0d5f7e4）

**标题**
```
fix(docker): exclude stale egg-info, add CI container smoke test, disable scheduler HTTP healthcheck
```

**正文**
```markdown
本地部署 `main@866a2af` 时发现的三个问题，均已修复：

1. **`.dockerignore` 补 `*.egg-info`**：源码树遗留的陈旧 `backend/china_fund_decision.egg-info`
   （未跟踪的本地构建产物，依赖清单缺 argon2-cffi/pwdlib）会被 COPY 进镜像并被 setuptools 复用，
   导致运行时报 `ModuleNotFoundError: argon2`。排除后重建即恢复。

2. **CI 增加生产镜像冒烟测试**：原 CI 只 `docker build` 不起容器，import/启动期错误（如上）漏检。
   新增步骤用临时 PostgreSQL + 生产配置真正跑起容器，`alembic upgrade head` 后轮询 `/api/health`，
   失败打印容器日志。

3. **scheduler 关闭镜像级 HEALTHCHECK**：scheduler 是后台 worker 无 HTTP 监听，镜像里烘焙的
   curl 健康检查永远报 unhealthy。

改动：`.dockerignore`、`.github/workflows/ci.yml`、`docker-compose.yml`（+36 行）。
已验证：`docker compose config` OK、ci.yml YAML 解析 OK。
```

---

## PR 2：`fix-akshare-sector-kline-fallback`（816a9f7）

**标题**
```
fix(providers): wire sector data through composite + add free-tier fallbacks and market-context index/proxy support
```

**正文**
```markdown
免费数据源（AKShare）接入的完整修复与增强，解决"决策看板无 ETF/板块数据"问题。

### 修复的真 bug
- `CompositeProvider` 漏定义 `fetch_sector_snapshots` / `fetch_concept_snapshots` /
  `fetch_market_breadth`，导致 `public_composite`/`composite` 模式下板块数据永远抛
  `CapabilityUnavailable`（落到 base 默认实现）。已补齐三个转发方法。

### 免费层降级链（东财反爬断连时的替代源）
- **K线**：东财 `fund_etf_hist_em` 断连时降级新浪 `fund_etf_hist_sina`（pre_close 由前日 close 回填）。
- **行业板块**：东财 → 同花顺 `stock_board_industry_summary_ths`（90 行业，含涨跌家数）。
- **概念板块**：东财 → 新浪 `stock_sector_spot('概念')`（175 概念，含板块涨跌幅+成分股数）→ 同花顺。

### 新增 market_context 能力（A股/美股大盘 + 可交易代理）
- akshare 实现 `fetch_market_context`：index 卡片（上证/沪深300/中证全指 + 标普500/纳指综合/纳指100）
  走新浪 `stock_zh_index_daily` / `index_us_stock_sina`；tradable_proxy 卡片走 `fetch_spot_quotes`。
- 新浪日线无涨跌幅字段，用最后两根 close 推算 pct_change。
- 配置启用 6 指数 + 1 半导体 ETF 代理卡片（`market_context.json`）。

### 已知限制（如实说明）
- 概念板块「涨跌家数」免费层无稳定源（东财被反爬、同花顺/新浪均无涨跌家数），
  当前概念板块为「名称 + 成分股数量 + 板块涨跌幅」，涨跌家数显示 "—"。

### 验证
- 容器实测：行业 90 / 概念 175 / 全市场 1 / 大盘指数 6 / 可交易代理 1 / K线 20691 根，全部真实数据（is_mock=false）。
- 新增单测 8 个（板块降级链、概念三级降级、K线降级、market_context index/proxy 观测）。

改动：`akshare.py`、`composite.py`、`market_context.json`、`test_sector_snapshots.py`、`docs/ETF_DATA_ONBOARDING_PLAN.md`（+671/-35）。
```

---

## 合并建议

- 两个 PR 相互独立，可分别合并；建议先合 PR 1（docker/CI），再合 PR 2（数据接入）。
- 合并后若要立即看到真实数据，本地 `.env` 需设：
  `MARKET_PROVIDER=public_composite`、`SCHEDULER_ENABLED=true`、`ALLOW_MOCK_FALLBACK=false`。

## Tushare token 实测结论（2026-09-02 更新）

用户已提供免费档 token，实测结论：**免费档无法解决概念板块涨跌家数**。

| 接口 | 频率限制 | 结论 |
|---|---|---|
| `daily(trade_date=)` | ~1次/分钟 | ✅ 一次拿全市场 5547 只行情（含 pct_chg），可聚合涨跌家数 |
| `stock_basic()` | 1次/分钟 | ✅ 一次拿全市场行业分类 |
| `index_daily` | **1次/小时** | ❌ 6 指数需 6 小时，不可用 |
| `ths_index`/`ths_member`（概念涨跌家数唯一正源） | 无权限 | ❌ 需 2000+ 积分 |

**结论**：概念板块涨跌家数仍无解——tushare 免费档无概念分类接口（`ths_member` 需付费积分）。
token 已写入 `.env` 作兜底（public_composite 下 akshare 优先、tushare 兜底），保留供将来升级付费积分后启用。

**最终定论**：免费数据接入已达天花板。概念板块涨跌家数需要 tushare 付费积分（2000+）或东财反爬缓解，二者均不在当前可行范围。
