# Local acceptance ef777ad — 2026-10-04

Remote source ef777ad0a192fc1689b828485fbb04984f37bbb6 received without local business edits. Backend/app and config are identical to 29c25d7; backend full regression was launched before this frontend-only update, backend bytes remained unchanged throughout.

- Chromium modal entrypoints: six passed,48.4s. Desktop/390/320/Overview/Search/original-board navigation all passed, including actual candle height, pan/click single dialog,36 Tabs, SUMMARY, hidden-details exclusion.
- Chromium persisted fractals/projection: three passed,43.2s (desktop1440 and narrow320; markers disappear when disabled; actual zone painting and repeated toggles).
- Vue172 passed; typecheck/build passed. Earlier source-identical backend focused138 passed; compileall/JS syntax/Node11 passed.
- Full backend: CHANGES_REQUIRED, one failure in backend/tests/test_postdeploy_board.py:180. Test still hardcodes support-resistance-v4-structure, but deliberately upgraded service now returns support-resistance-v5-indicators. Remote must reconcile current-version assertions while retaining old snapshot rejection and GET read-only/structure behavior assertions. No local test edits.
- Exact hosted CI: platform37184096508 SUCCESS; workspace37184096470 and full37184096465 still running at last independent check.

Full JUnit: E:/Claude_allow/Download/etf-remote-77-full.xml. Deployment pending remote corrected commit, acceptance and exact CI. Real data qualification UNKNOWN/actionable=false/not_calibrated.
