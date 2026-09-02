# CLI and report-list consistency remediation

## Scope and boundary

- Goal: preserve auth-disabled legacy CLI holdings while keeping auth-enabled CLI ownership strict, and make report listing enforce the same artifact-root containment as report download.
- Allowed files: `backend/app/cli.py`, `backend/app/api/router.py`, the focused multi-user tests, and this task ledger/plan.
- Prohibited: credentials or `.env` access, database migrations or production database writes, strategy changes, commit, push, deploy, or unrelated dirty-file edits.
- Evidence status after this work: local regression coverage only; it cannot establish production readiness or provider qualification.

## Plan

1. **RED — CLI compatibility and owner scope.** Add tests that invoke `holding-set` and `holding-delete` through Typer with auth disabled and no username, asserting a `NULL` owner; assert auth-enabled invocations require an explicit active username and act only on that owner. Run the focused test and retain the expected failure caused by the currently-required option.
2. **GREEN — CLI mode selection.** Read `Settings.auth_enabled` at command execution. In disabled mode use `user_id=None`; in enabled mode reject omitted, missing, or disabled usernames and use the resolved owner ID. Re-run the focused CLI test.
3. **RED — report-list root containment.** Extend the report ownership regression with an owned external `.json` artifact plus an owned in-root artifact and a foreign-owner artifact. Assert the list exposes only the valid in-root artifact and does not disclose external path/name. Run it and retain the expected failure from the current list implementation.
4. **GREEN — consistent report listing.** Inject `Settings` into `GET /api/reports`; for each candidate resolve strictly, require it to be a regular `.html`/`.json` file under `settings.reports_dir.resolve()`, then apply the existing owner filter and post-filter limit. Re-run the focused report test.
5. **Review.** Run the two focused test modules, then sequential full pytest with `E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe`; run compileall, Node syntax, and diff checks. Record literal exit codes in `tasks/todo.md`. On any test failure outside these expected RED stages, stop and re-plan; rollback is a narrow reversal of only the files above (no git reset/clean).
