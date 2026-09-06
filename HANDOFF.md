# 接手说明：P0–P4 全源码交付

先读 AGENTS.md → START_HERE.md → docs/DELIVERY_P0_P4.md → docs/TEST_REPORT_20260906.md → docs/LOCAL_WORKSPACE_DEPLOYMENT.md → docs/planning/WORKSPACE_PLANNING_V2.md。

当前包不是生产main原样归档：main3c7bdc7 + PR28的7adfbc0 + 本轮修复，未推送。自行提交步骤见 docs/SELF_SUBMIT.md。
旧原文位于 docs/archive/main-3c7bdc7/，不再据旧文档“Canvas是当前唯一UI”否定新Vue/KLine实现。

后端FastAPI/PostgreSQL/Provider/确定性指标保留；current action唯一五档；forecast 1/3/5/10。
新UI精确路由开关，旧壳可回退；所有ETF详情统一 /etf/{code}。
浏览器真实部署为HttpOnly Cookie+CSRF；无localStorage认证；AUTH_ENABLED=true、生产AUTH_COOKIE_SECURE=true、AUTO_CREATE_SCHEMA=false、DATABASE_URL使用私密PostgreSQL配置。
数据库Alembic head d40609090002，首位管理员仍用 `fund-decision auth-bootstrap-admin` 交互建立，不含默认密码。

本轮测试证明基础工程路径，并非研究收益、真实模型、真实Provider或生产部署资格。Q线和Vibe真实模型验收未结束。
不要恢复已删除的workspace-finalize一次性自动patch/commit工作流。不要自动装完全部开源依赖，不复制登录文件，不降级Mock冒充真实。
模型只解释，设备不能发布/写持仓/改策略；外部Vibe包是未验证候选，保留来源证据和人工审核。
