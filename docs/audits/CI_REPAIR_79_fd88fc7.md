# Exact CI findings — 2026-10-04

Source fd88fc76c93a516db77e5f0d22a4ed74d914caa5, not a local implementation change.

- Platform37184595230 SUCCESS.
- Workspace37184595254 FAILED, job111383801163 responsive step:16PASS2FAIL. Indicator-manager line19 expects false after toggling volume whose new default is false (actual true); layout line109 expects expanded chart after button but prior drag can dispatch click and autoopen, button then closes. Remote already auditing click/drag UX.
- Full37184595257 FAILED, job111383817992 Unit and integration tests:seven calibration tests fail KeyError gate_results/gates_passed/summary. Cases single-horizon mock/no-holdout/NaN; artifact tamper approval;bad h10;empty h10;out-of-range metrics;self-declared source/PIT/lineage;forged validator contract. The same suite passed in local Windows full run; do not treat local PASS as Linux PASS.
- Root-cause clue requiring remote verification: shared report state selects latest as_of_time; synthetic fixture uses datetime.now().astimezone() (host local UTC on CI), while application timestamps use configured market timezone. SQLite drops timezone information. A preexisting market-time artifact may sort ahead of freshly written UTC fixture; returned skipped/duplicate then lacks gate fields. Review timestamp normalization and fixture isolation, not just dictionary defaults or weaker assertions.

CI evidence artifacts:workspace11296946319,audit11296827168. Original logs read through authenticated GitHub App; no secrets or raw logs committed. Fix remotely and return exact SHA. Deployment pending.
