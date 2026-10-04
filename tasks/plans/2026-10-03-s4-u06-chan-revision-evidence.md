# S4-U06 saved Chan revision evidence

Base: `8c62d70f4ecccc1c9819be36cad09a1f7da6a826`. Scope follows
PROJECT_MASTER_ROADMAP S4-U06 and R4C implementation plan M4. It is a bounded
display of already verified observations, not complete M4 or production acceptance.

The verified Chan read already returns observation identity, cutoff and
NEW/CHANGED/UNCHANGED/ABSENT transitions with revision IDs and reappearance.
The chart projection drops the transition evidence, so the current UI cannot
explain changes. Preserve a small allowlisted optional `revision_evidence`
block in that existing projection and add a collapsed evidence card.

Frozen boundaries:
- Existing persisted JSON, read model v110, Chan engine/dialect, chart version,
  geometry, prices, input settlement, qualification and actionable are unchanged.
- No new endpoint, GET, query, Provider, engine call, recomputation, schema,
  snapshot write/rebuild, real-data request, deployment or runtime activation.
- Missing optional fields in older responses stay unknown. Missing revision
  identity cannot support a labelled revision change. Unknown codes/fields
  cannot become arbitrary UI instructions or a successful state.
- ABSENT means not observed in this observation, not invalidated. Reappearance
  comes only from the strict stored flag on a NEW transition. No inferred history.
- Engine confirmation stays unknown. Cutoff is explicitly the stored UTC
  input cutoff; it is not a confirmation, publication or observation timestamp.
  Latest persisted revision remains distinct from historical PIT.
- Card appears only with the selected, drawable persisted Chan layer. A blocked
  or price-mismatched layer cannot borrow the card or identities from fallback.
- Native details/summary starts closed, has visible keyboard focus and at least
  44px touch height. Show at most five entries initially, with an explicit
  expand/collapse control; no sorting by invented recency or live alert wall.
- Evidence and expansion state reset on instrument/period/observation changes;
  long IDs wrap on narrow screens. Text uses Vue interpolation only.

Red-first verification: all five transition presentations, unknown/missing IDs,
malformed fields, legacy response, empty transitions, blocked/fallback/mismatched
states, unchanged input and exact old geometry projection. Cover keyboard
disclosure, mobile width, response replacement and visible card screenshots in
real Chromium CI. Run actual Vue typecheck/tests/build, focused/full backend,
required static checks and independent review before the existing-branch push.
Bind final evidence to exact tree/commit and all hosted CI outcomes.

Consolidate the completed WU2 v110 publication/CI receipt with this batch's
legitimate documentation changes. Do not use those test counts as qualification.
