# R4B Final Acceptance — local candidate

- **Date:** 2026-09-28
- **Status:** `ACCEPTED_LOCAL`
- **Scope:** R2–R4B application and evidence contracts accepted locally after independent remote review.
- **Production:** unchanged; this candidate is not deployed.
- **Real-data qualification:** `UNKNOWN`.
- **Canonical action / actionable:** unchanged / `false`.

## Authoritative application identity

| Item | Identity |
|---|---|
| Application SHA | `43bfbf6929a70f520c216b759edbaa433e920e91` |
| Application tree | `12d217af3edbe34c67bc36e75b4395ab4917b001` |
| Parent | `1960bb9f11f9f5d7e706ebd137ad9618754943b2` |
| Branch | `codex/r4b-c2c1` |
| Candidate migration head | `g8b9c0d1e2f3` |
| Final JUnit SHA-256 | `E5E683C9A0D3F9AD8546E214D5E24B3E3B0A0239029519C286C6EF894D61ACAA` |
| PostgreSQL evidence SHA-256 | `FE411447A7499E79C615D5213C4BC49A122942ABD00EA933F50E45E9F361E711` |
| Final receipt SHA-256 before this document is committed | `4BE4EA1919EBA70C492558A07227ECADE4E3A816654E6846ED7199CBFD86EB07` |

The receipt hash above identifies the execution receipt released before this documentation-only commit. The document commit has its own Git identity.

## Application chain

| Stage | Commit | Tree | Parent | Role |
|---|---|---|---|---|
| C1 | `5feff1ec83f1ef39d2dbd461ef76f54d589daac5` | `60d901006da0ddf2682cf7d03bed4737fb0210ba` | `3069ab72d9bccd27f0fadeb3996ed445f6ce5446` | application/schema capacity |
| C2A | `c74ab858d7573b1a6a995d3e6ea8a2c0e10c450b` | `dc5e3381d4fafca9437db9f434d2e7a515284945` | `5feff1e` | replay/window lifecycle |
| C2B | `9587ba7acc0bb6014a6897cb11ffbb7c6b2e8d4b` | `35391dafad99185955f5f2f6cee9033dcbbaf32f` | `c74ab85` | rejected intermediate |
| C2B.1 | `553d8add1348236452d549e6df5d287c5f96b2db` | `570806bb9c40737926118893e560283a4cac9596` | `9587ba7` | basis/input identity |
| C2C | `2208a7d6f38c69f7109b8248197e0d7db0014b20` | `5ca22d3c686ea68568cc2d7a02505a37f1b7fd38` | `553d8ad` | append-only revisions |
| C2C.1 | `87396cac2620f64c196be049fc5ad645484bb3e7` | `b27001cbd80688f570a8d15005eb488bc1f956c7` | `2208a7d` | current/backing binding |
| C2C.1 tests | `c4dba4ea39f9e231f1d93425253a6134a39b143a` | `3d8d652d67e6e11b9a8def61754825a05335bafb` | `87396ca` | acceptance regressions |
| C2C.2 | `88cfb5bf23f44af9dba187efda7e2f84f0410698` | `c9a9d6edc7d94a63b34b6e60a1f6327fc8864edd` | `c4dba4e` | revision self-integrity |
| Migration-head contract | `1960bb9f11f9f5d7e706ebd137ad9618754943b2` | `6022f66c0e3146c6f941cdafdf967821cc29b6b9` | `88cfb5b` | final regression contract |
| Final cleanup | `43bfbf6929a70f520c216b759edbaa433e920e91` | `12d217af3edbe34c67bc36e75b4395ab4917b001` | `1960bb9` | lint/UTC cleanup |

The rejected intermediate C2B and earlier C2C findings remain in history for traceability. They are not deleted or rewritten.

## Acceptance matrix

| Gate | Result | Evidence |
|---|---|---|
| C1 schema/method-version compatibility | `PASS` | independent remote review |
| C2A default-120 replay/lifecycle | `PASS` | prefix, rollover and expiry regressions |
| C2B economic basis/input identity | `PASS` | independent remote review |
| C2C append-only same-day revisions | `PASS` | SQLite migration and service tests |
| C2C current to immutable backing | `PASS` | missing backing fails closed |
| C2C immutable evidence self-integrity | `PASS` | payload and metadata identity tamper regressions |
| Identical recomputation | `PASS` | exactly one revision |
| Failed publication atomicity | `PASS` | previous current remains valid |
| SQLite migration/schema parity | `PASS` | candidate migration head |
| PostgreSQL migration/roundtrip | `PASS` | isolated PostgreSQL 16; see `postgres-gate-43bfbf6.txt` |
| Final full backend regression | `PASS` | 1279 tests, 0 failures, 0 errors, 15 skips |
| Compileall / Node / relevant Ruff / secret scan / diff check | `PASS` | final candidate |
| Canonical action | `UNCHANGED` | no strategy/action changes |
| Real-data qualification | `UNKNOWN` | no real-provider qualification performed |
| Production | `UNCHANGED` | no deployment or production DB/provider action |

## PostgreSQL evidence

A fresh local PostgreSQL 16 container was used only for this gate and removed afterward. The run upgraded a fresh database to the single head `g8b9c0d1e2f3`, passed `alembic current` and `alembic check`, verified the revision table constraints/indexes/foreign key/column lengths, and passed the complete A→A→B, tamper and failed-publication service roundtrip. No production or personal database was used.

## Release boundary

This is a local engineering acceptance. The deployed production identity remains SHA `0dbd3fee58a3f5e080aacbcd8eae8d5964aec54f`, tree `f8607b3de8decde6065ccc559c5c26b0262b8e6b`, and Alembic head `e609200001`. The candidate migration head `g8b9c0d1e2f3` is not a production migration claim.

## Next stage

C2D documentation reconciliation is the next authorized stage. R4C remains closed until C2D binds this accepted candidate, updates the current handoff/receipts, and receives independent review.
