# Frontend attribution

The ETF workspace UI and ChartAdapter are original integration code. KairoTrend was used only as a user-supplied information-layout reference; no Kairo/QuantDinger/tick branding, CSS, proprietary source or account screenshots are distributed.

Runtime dependencies: Vue 3 (MIT), Vue Router (MIT), Pinia (MIT), KLineCharts 9.8.12 (Apache-2.0), lucide-vue-next (ISC, including its upstream icon attribution). Exact versions and transitive dependencies are pinned in package-lock.json. Dependency licenses remain part of their packages and are copied into the production image at `/app/THIRD_PARTY_LICENSES`.

KLineCharts renders backend-provided financial series. Its built-in MACD/KDJ/RSI formulas are not used as a second authority. This integration does not imply endorsement by any upstream project.
