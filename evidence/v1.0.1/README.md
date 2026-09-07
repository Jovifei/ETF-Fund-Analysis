# v1.0.1 证据

这些记录来自本次隔离测试，不是 Jovi Windows/生产数据记录。pytest-package-final.xml 为本次最终全量；HTTP 为非 Mock 配置的空持久数据库，但没有调用公网行情。browser-result.json 为 Mock 离线实际组件，不是标准网络导航 E2E。local-provider-availability.json 明确未接通本容器外部数据，不能将 probe_complete 当作 readable。

截图单独提供，不包含认证文件、Cookie、Token、真实持仓或字体。详情见 ../../docs/VALIDATION_V101.md。

文本日志副本仅规范化尾部空行，未改写测试结果。
