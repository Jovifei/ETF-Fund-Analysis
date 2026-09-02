# Multi-user account and portfolio isolation plan

## Goal

Extend the account-password prototype into a bounded multi-user system for
approximately ten private users. Market data remains shared; identities,
sessions, holdings, OCR imports, and user preferences are isolated by user.
The legacy Bearer token is optional CLI/API compatibility only and is not a
browser identity.

## Decisions

- Closed enrollment: an admin creates and disables accounts; no public signup.
- One `admin` role and one `member` role. Admin-only account management and
  password reset; members can only read shared research and edit their own
  portfolio/imports.
- Username is required; verified email/SMTP/OTP is out of scope for this pass.
  An optional email is a same-account login alias only.
- Existing Argon2id password hashing, signed session cookies, CSRF protection,
  and login throttling remain. Sessions become database-backed and revocable.
- Existing shared market tables stay global. Existing single-account holdings
  are migrated to the bootstrap admin account; no private values are copied to
  logs or reports.

## Tasks

- [x] Add `AuthUser`, `AuthSession`, and optional auth audit model with bounded
  fields, unique username/email, role/status checks, expiry/revocation indexes.
- [x] Add Alembic migration from the current head. Add `user_id` to holdings,
  remove global instrument uniqueness, add `(user_id, instrument_id)` unique;
  add owner to holding-import sessions and user-scoped runtime settings where
  needed. Provide a deterministic bootstrap-admin migration path without
  reading plaintext passwords.
- [x] Add current-user dependency that accepts database session cookies and
  legacy Bearer only when explicitly configured; hash session identifiers at
  rest, enforce expiry/revocation, rotate on login/logout, and preserve CSRF.
- [x] Add admin CLI/API for create/list/disable/reset-password and a safe first
  admin bootstrap using hidden prompts/Argon2id; no public self-registration.
- [x] Thread `user_id` through HoldingService, OCR import service/routes,
  holdings routes, private reports/settings and any portfolio-derived output;
  prove cross-user reads/updates/deletes return no data.
- [x] Keep shared market/decision board/news/indicator reads global while
  preventing user-owned data from entering shared snapshots or logs.
- [x] Update browser login/me/logout to display account identity and support
  admin user management without localStorage credentials.
- [x] Add tests for migration parity, two users with same ETF, session revoke/
  expiry, CSRF, admin/member authorization, OCR ownership, and legacy Bearer.
- [x] Run full pytest, compileall, Node checks, Alembic upgrade/downgrade/check,
  secret scan, and an isolated two-user API/browser smoke. Review before any
  commit, push, or ECS deployment.

## Final implementation evidence (2026-09-02)

- Database-backed account sessions, admin/member lifecycle, CSRF/revocation,
  user ownership, OCR HTTP transactions, private report artifacts, SSE session
  revalidation, shared-signal isolation, and production fail-closed settings
  are implemented in `codex/multi-user-auth`.
- Project venv full `pytest -q` exited 0 with 3 platform skips; focused suites,
  compileall, Node checks, and diff checks exited 0. Independent specification
  and code-quality reviews are approved.
- This is local/isolated evidence only. Real PostgreSQL migration and restore,
  ECS deployment, provider qualification, and production smoke remain pending.

## Non-goals

- No public registration, email delivery, OTP, social login, broker access,
  automatic trading, or changes to indicator/strategy formulas.
- No real credential read; user passwords and provider tokens stay server-side.

## Task 1 evidence (2026-09-01)

- Added `auth_bootstrap_guard`, `auth_users`, and `auth_sessions` only. Passwords, opaque session IDs,
  CSRF nonces, user agents, and IP addresses are never stored in plaintext.
- Migration `0a9b1c2d3e4f` descends from `f7a8b9c0d1e2`, seeds the singleton
  bootstrap guard, and leaves holdings,
  import sessions, and runtime settings unchanged for Task 2.
- The service supports Argon2id verification, session creation/lookup,
  expiration, per-session revoke, and revoke-all. The signed-cookie prototype
  remains untouched as the compatibility bridge until the current-user route
  migration lands.
- Focused GREEN: `test_multi_user_auth.py`, `test_password_auth.py`, and
  `test_migration_schema_parity.py` passed (45 tests, one explicit PostgreSQL
  integration skip) after a SQLite
  upgrade/downgrade/re-upgrade/check cycle. Full regression remains pending.
- The first-admin path takes a PostgreSQL `FOR UPDATE` lock, with a SQLite
  singleton-row update to acquire its write lock before the account check.
  A two-session/thread regression test proves exactly one first admin wins.
- ORM and auth service now reject non-parseable Argon2id PHC values before
  persistence using a non-computational exact PHC structural check (version,
  ordered bounded parameters, strict base64, and non-empty bounded salt/digest).
  Actual login remains one pwdlib Argon2 verify. The migration prefix check
  remains defense in depth. The
  optional PostgreSQL test runs only when `TEST_POSTGRES_URL`, `APP_ENV=test`,
  and `ALLOW_DESTRUCTIVE_TEST_DATABASE=1` are all explicit, and the database
  name ends in `_test`, `_scratch`, or `_ci` (or the matching short name).
  It upgrades with `ALEMBIC_DATABASE_URL`; otherwise it reports a named skip
  without opening dotenv configuration or deleting any auth rows.
