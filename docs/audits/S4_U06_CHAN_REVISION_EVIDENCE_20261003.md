# S4-U06 saved Chan revision evidence

Baseline: `8c62d70f4ecccc1c9819be36cad09a1f7da6a826`, existing branch
`codex/remote-stage-s8f0-s2-20261002`. Scope is frozen in the
[bounded plan](../../tasks/plans/2026-10-03-s4-u06-chan-revision-evidence.md),
following the roadmap's S4-U06 and R4C M4 evidence-card requirement.

## Reproduced gap and result

The existing verified Chan read supplied transition/revision identities, but
the chart projection discarded them. Three new backend cases failed on the
missing optional block; the new Vue suite failed because the card did not exist.
Both red results are retained. Existing legacy projection cases already passed.

The chart now allowlists sequence, source cutoff, input identity and stored
transition fields into optional `revision_evidence`. It does not derive a
change from geometry. Older responses retain their original projection and the
UI says revision evidence was not provided; a verified empty list has a
different empty state. Invalid field types or unknown transition codes remain
unknown. Missing current/prior identities cannot produce a known change label.

The collapsed native details/summary card shows metadata and at most five
transition rows initially, with an explicit expand control. New, changed,
unchanged, absent and reappeared observations have distinct text. ABSENT means
not observed in this observation, not invalidation. Reappearance requires the
strict recorded flag on NEW. Source cutoff is shown in the read service's
normalized UTC convention and is not relabelled as confirmation or publication.
Engine confirmation remains unknown; latest saved evidence is not historical PIT.

The card is available only for the selected, drawable persisted layer. Corrupt,
missing, simplified or price-mismatched evidence cannot borrow its identity.
Instrument, interval or observation replacement resets disclosure state;
identities wrap, the summary and more button have 44px targets and visible
keyboard focus. Vue text interpolation is used, without alert/live regions.

## Unchanged boundaries

No stored observation, engine/dialect, geometry, price, settlement semantics,
qualification, strategy or actionable change. Exact old chart projection and
full overlay objects remain equivalent when metadata is added. chartAdapter.ts
is unchanged from the baseline. No new read-model or chart version, schema,
endpoint, request, query, Provider/engine call, read-path write or automatic
snapshot rebuild. The v110 flow/share change and immutable v109 compatibility
remain covered by their unchanged existing tests.

## Validation state

- Focused projection/chart/read tests: 47 passed, one existing PostgreSQL-only skip; the independently executed suite includes the chart route and passed 48 with the same one skip.
- Actual Vue typecheck, 139 tests / 21 files and production build: PASS.
- Scoped Ruff, Python compilation, browser JavaScript syntax and whitespace: PASS.
- Final frozen backend aggregate: PASS, 1588 collected / 1577 passed / 11 existing skips / 0 failures / 0 errors, 589.294 seconds; exit 0. All 12 runtime/test/fixture hashes remained unchanged. The 11 skip identities match exact 8c62d70 hosted CI.
- Independent complete 21-file source/test/documentation review: PASS; final JUnit, all predecessor test identities and all 11 existing skip identities were independently verified.
- Three new Chromium cases cover keyboard disclosure and period reset, a
  320px screen/layer hiding, and old-response unknown state, with screenshots.
  The current local attempt failed before any page assertion because Chromium
  ProcessSingleton socket creation returned EPERM. All three are NOT RUN as
  product/browser acceptance; no local screenshot or visual pass is claimed.
- Exact new-commit hosted CI and browser screenshots: PENDING PUBLICATION.

The first backend aggregate passed 1587 collected / 1576 passed / 11 existing
skips / zero failures/errors in 615.767 seconds. It preceded the added real
persisted unchanged-revision fixture case and remains preliminary evidence.
Independent review caught and removed an incorrect display-only equality check:
revision IDs are observation-bound, so UNCHANGED geometry can have distinct IDs.
A real synthetic publisher → verified read → projection fixture reproduces
that contract; two Vue failures were retained before the correction. The final
frozen candidate subsequently passed its complete rerun. Contradictory NEW/ABSENT null-side
shapes and invalid flags remain unknown without inferring geometry from IDs.

Independent checks also exercised 576 combinations with exact legacy projection
parity and six symbol×D/W/M namespaces with correctly bound IDs. Missing scope,
unsupported interval and tampered stored input hashes exposed no evidence.
These probes are separate reviewer checks, not included in pytest totals.

This bounded batch does not complete all M4/S4, deploy, refresh production or
establish real-data/units/PIT qualification. Predictions remain not calibrated
and actionable=false. WU2's completed predecessor CI is recorded separately
in its [receipt](WU2_FLOW_SHARE_READ_CONTRACT_20261003.md), not reused as this
candidate's hosted acceptance. Windows hub/root-doc sync and normal-user live
acceptance remain separate, unexecuted gates in this cloud work.

## Final local identities

Final JUnit SHA-256: `64ea3143a4a71301f505aa22dcdcae3a8b2b50b987e2109999eb5aba83cfd413`.
The earlier preliminary JUnit remains `da1fc2bce89291381faeca526f383910b3389096d3b04db2d9f8712a25a07890`.
Twenty evidence-card tests also passed in both Asia/Shanghai and America/New_York processes; cutoff labels remain explicit UTC.
Twenty-seven existing JavaScript tests and the staged committed-secret scan passed.

Frozen runtime SHA-256:

- backend/app/workspace/chan_chart_overlay.py: `05b67c03f51ae6eafd509d6c479bc645fc8b0037597a4a9cac15a2104ebf5b09`
- frontend/src/components/ChanEvidenceCard.vue: `47385c2ce391ccf7c7a201eec2883792a56fb251eab462a40ee63df97fded1f7`
- frontend/src/components/EtfChart.vue: `4869b5c4335bcc4e47294b776f9dd98627cbec58fb3678dca0eb41f6e9b60099`
- frontend/src/lib/types.ts: `94fb2ed852ff0b8b259cc98ca9b18ac68e49556fda7f1328571797a1000355b5`
