# Password-account authentication plan

## Goal and boundary

Replace browser use of `PRIVATE_ACCESS_TOKEN` with one server-configured account
(username plus optional email alias) and an Argon2id password hash.  Keep the
legacy Bearer token strictly as an optional API/CLI credential.  This change is
stateless: it adds no database migration and does not touch provider, market,
strategy, or portfolio logic.

## Preconditions and prohibitions

- Worktree: `E:\Claude_allow\Download\ETF-Fund-Analysis-worktrees\password-auth-login` at `3f124ae`.
- Do not read `.env` files or output real credentials.
- Do not push or deploy.  A single scoped commit is authorized by the task.
- Production must require a complete account configuration or a non-placeholder
  legacy token; session/password secrets must never be logged or returned.

## Checkable implementation and evidence

- [x] RED: add focused API/config/static tests for account login, invalid and
  throttled credentials, cookie attributes, session expiry, CSRF, logout,
  legacy Bearer compatibility, and disabled auth.
  - Expected initial result: imports/routes/config required by the test do not exist.
- [x] GREEN: add `pwdlib[argon2]`, security helpers, account config validation,
  signed expiring session cookie, CSRF cookie/header checks, and throttling.
  - Files: `pyproject.toml`, `backend/app/core/config.py`,
    `backend/app/core/security.py`, `backend/app/api/router.py`, schemas/tests.
  - Failure behaviour: invalid/missing cookie, CSRF, and credentials return
    generic 401/403 responses; invalid production config fails closed.
- [x] GREEN: replace browser token persistence with account login/me/logout,
  same-origin credentials and CSRF headers; keep static demos auth-disabled.
  - Files: `backend/app/static/index.html`, `app.js`, `app.css` and static test.
- [x] GREEN: add a hidden-prompt password-hash helper and update non-secret
  configuration/documentation templates, including the no-OTP boundary.
- [x] Verify focused tests then `pytest -q`, `python -m compileall -q backend/app`,
  `node --check backend/app/static/app.js`, `git diff --check`, and a scoped
  secret-pattern review.  Commit only the resulting authentication paths.

## Rollback

The whole change is one commit on the isolated branch.  Reverting that commit
restores the existing legacy-token-only browser behavior; no persisted session
or database state needs migration or cleanup.
