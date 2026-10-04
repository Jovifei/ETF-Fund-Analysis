# Snapshot compatibility/temporal stage reception — 2026-10-04

Received fixed remotefb0099621a2ade9b25d88cdef153c6c4b513f1f3. No local business/test source changes. compileall passed.

- Remote-requested13-file subset:107total,101passed,6failed,0skips/errors,132.333s.
- Four SignalCenter positives fail:take_profit fronts empty,sector ranking differs,held-instrument fronts empty,current front grade missing. These fixtures explicitly use datetime.now()+1/+2days,so new temporal gates reject their intended positives;remote must make coherent test references without removing future-negative/security checks.
- Non-flow independent golden test fails at decision_board_row. Preserve the full non-flow comparison and diagnose timing/identity versus actual unexpected differences;do not blindly replace or drop golden assertions.
- Additional local-only subset failure:cross_surface_consistency::test_kline_states_match_signal_grade_semantics has Kline empty string versus SignalGrade KDJ不足. Keep same-evidence surface consistency contract.
- ExactfullCI37210016931(job111459168880) failed7 cases:the same4SignalCenter +non-flowgolden +two DecisionBoard stale-qualified-snapshot cases. Workspace37210016955/platform37210016938SUCCESS.

## Extra stale-case diagnosis

Both original DecisionBoard cases were run separately and FAILED before any diagnostic alteration:price-only trailing tail and official-split stale research snapshot unexpectedly show 数据异常. Their IndicatorService call generates snapshots at current wall clock while DecisionBoard generated_at is explicitly historical2026-03-25/2025-08-06.

Diagnostic only (not a source fix,not original-suite PASS):a temporary plugin outside repo assigned synthetic IndicatorSnapshot.generated_at to its historical as_of_date16:16,then ran the unchanged original tests/assertions;both PASSED. Script:E:/Claude_allow/Download/diagnose_snapshot89_clock.py. This demonstrates coherent fixture-time repair can retain the original stale/non-anomaly assertions;never weaken future evidence rejection to force green.

Original subset JUnit:E:/Claude_allow/Download/etf-remote-89-snapshots.xml;original2-caseJUnit:etf-remote-89-stale-board.xml. All are synthetic test-only data,not private account inspection or production DB mutations.

StageCHANGES_REQUIRED. Remote owns whole-stage repair/version identity and fixed commit;local receives/tests/returns only. Production remains frozenefc0898/imagee01a951d. No audit deployment,provider/resource activation or qualification promotion;historical dataset/phone/PIT pending.
