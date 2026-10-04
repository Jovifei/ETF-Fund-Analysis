# Price-basis stage reception — 2026-10-04

Received fixed remote7d439b3891db276cb1423ac403213323df6421e7 from codex/post-release-indicator-audit-20261004. No local business/test edits.

- Concentrated price-basis/corporate-action/backtest/crosscheck/credibility/global-walk-forward/maturity/OBV/input-validity/cross-surface subset:54total,53passed,1failed,0skipped/errors,45.752s. compileall passed.
- Failure: backend/tests/test_price_basis_research_execution_contract.py:124, test_factor_panel_uses_evidence_bound_split_research_basis calls `_panel(db_session,[inst.id])`; production signature is `_panel(self, db, *, instrument_ids: set[int] | None = None)`, so Python raises TypeError before exercising official-split enrichment. Correct the test to use the keyword-only public contract,retain all basis/metadata assertions,and verify what happens after that path executes.
- Exact fullCI37193984579 failed Unit and integration tests (job111411946009); workspace37193984618 and platform37193984584 SUCCESS. Do not label whole stage PASS before corrected commit and actual acceptance.
- Production remains frozen accepted efc0898/imagee01a951d/schemaf0; no new audit deployment,provider activation,raw DB edits or data/PIT/calibration qualification.

Evidence: E:/Claude_allow/Download/etf-remote-85-price-basis.xml. Await remote whole-stage repair/real GitHub commit and next plan/execution;local will receive fixed source and return evidence only.
