# 文档入口：v1.0.4 增量分支

优先阅读 [v1.0.4版本](versions/V1.0.4.md)、[用户操作](USER_GUIDE_V104.md)、[AI安全](AI_CONNECTION_SECURITY_V104.md)、[本地验收](LOCAL_ACCEPTANCE_V104.md)、[开源落点](OSS_APPLIED_V104.md)、[过程](PROCESS_LOG_V104.md)。生产状态仍以目标环境部署收据为准，以下保留v1.0.3完整知识入口。

# 文档入口：v1.0.3 分支交付

这是开发代码与接收文档入口，不是生产升级声明。基线204a31c；v1.0.3 修复已合并到主线，当前主线知识文档提交为 `eccacdc`，服务器运行应用仍以 `c60a157` 收据为准。

## 当前实现与验收

1. [V1.0.3版本记录](versions/V1.0.3.md)：应用改动、资格、回滚及未完成范围。
2. [验证记录](VALIDATION_V103.md)：本机回归与固定提交云端CI分开，真实数据/模型另验。
3. [本地接收L1–L5](LOCAL_ACCEPTANCE_V103.md)：原持久数据、真实行情、图表、收藏、OCR、Codex/Vibe、复盘及归档。
4. [历史展示与存储合同](HISTORY_STORAGE_V103.md)：已有K线不依赖新报价，逐标的门禁，归档不是自动同步。
5. [开源吸收落点](OSS_APPLIED_V103.md)：用户选定项目、源码位置、本项目对应文件与未部署边界。
6. [项目制造过程与文档地图](PROJECT_BUILD_AND_DOCUMENTATION_V103.md)：从需求、实现、接收、真实源试跑到部署合并的证据链，以及各文档的阅读顺序。
7. [项目知识库总览](PROJECT_KNOWLEDGE_BASE_V103.md)：项目目标、制造过程、系统全貌、技术路线、完成能力和下一阶段。
8. [技术路线与工程关系](TECHNICAL_ROUTE_V103.md)：浏览器、API、Provider、worker、数据库、指标、OCR、Bridge 和部署之间的调用关系。
9. [完成项与证据矩阵](COMPLETION_AND_EVIDENCE_MATRIX_V103.md)：区分源码、隔离测试、真实公共源、生产现场和最终资格证据。
10. [开源借鉴登记册](OPEN_SOURCE_ADOPTION_REGISTER_V103.md)：固定 revision、许可证、借鉴点、实际落点和隔离边界。

固定接收SHA以最终交付Prompt/PR为准，不能把中间传输材料提交当成可部署应用。根AGENTS.md仍是安全合同。原WorkBuddy模板在总览中保留；预测期限仍1/3/5/10，不因应用升版而自动calibrated。

## 继续有效的专题

[数据接入v1.0.1](DATA_ACCESS_V101.md)、[部署基础](LOCAL_WORKSPACE_DEPLOYMENT.md)、[UI/UX](UI_UX_CONTRACT.md)、[planning-v2](planning/WORKSPACE_PLANNING_V2.md)、[当前动作唯一来源](CURRENT_DECISION_SOURCE_CONTRACT_20260903.md)、[期限](HORIZON_ALIGNMENT_20260903.md)、[支撑压力](SUPPORT_RESISTANCE_SEMANTICS.md)、[PIT与14:30验证](ETF_1430_VALIDATION.md)。

## 历史证据不可抹掉

[版本索引](versions/README.md)、[上一版原文档入口](archive/pre-v103/docs-README.md)、[原STATUS](archive/pre-v103/STATUS.md)、[原HANDOFF](archive/pre-v103/HANDOFF.md)、[v1.0.1部署收据](DEPLOYMENT_RECEIPT_V101_20260907.md)。归档文档的相对链接按当时仓库位置理解；原正文未删减。

[main原文归档](archive/main-3c7bdc7/README.md)、[初始产品规划](archive/planning-v1/ETF_WORKSPACE_VNEXT.md)、[逐文件开源审阅](archive/planning-v1/OSS_ABSORPTION_20260906.md)保留来龙去脉。旧测试数只描述各自时点，不覆盖当前事实；未读取的视频不是功能或收益证据。
