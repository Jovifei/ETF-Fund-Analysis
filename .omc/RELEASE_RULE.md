# Release Rules
<!-- last-analyzed: 2026-09-24T02:16:15Z -->

## Version Sources

- `pyproject.toml`: `project.version` (`1.0.5`).
- `frontend/package.json`: `version` (`1.0.5`).
- Production `APP_VERSION` is externally configured (`1.0.8` per the current deployment receipt); it is not the source commit identity.
- A code-only repair deployment does not bump package versions or create a tag unless explicitly requested.

## Release Trigger

- `ci.yml` and `workspace-ci.yml` run on branch pushes and pull requests.
- There is no automatic production deployment workflow. Production is changed only through the manual, backup-first artifact procedure documented in `docs/PRODUCTION_DEPLOYMENT_RECEIPT_AU_20260923.md` and the private local operations guide.
- Existing repository tags include `v0.7.0`, `v1.0.0`, and `v1.0.1`; no tag is created for a routine hotfix deployment.

## Test Gate

- `ci.yml`: full `pytest -q`, Python compile, legacy JavaScript checks, secret scan, Alembic/Compose validation, production image build, and image smoke.
- `workspace-ci.yml`: workspace contracts, frontend `npm audit --audit-level=high`, typecheck, Vitest, production build, and ordinary/authenticated/responsive Playwright suites.
- `audit-platforms.yml`: dedicated PostgreSQL/Windows platform contracts where their required environments are available.
- Local isolated tests supplement CI; conditional platform skips are recorded, never represented as passing platform evidence.

## Registry / Distribution

- No container registry publish step is configured. Successful `ci.yml` uploads `production-image-<run_id>` containing the smoke-tested compressed Docker image, SHA-256 sidecar, and release inventory (7-day retention).
- Deployment must download the artifact, verify its digest and OCI revision/tree, then load the same immutable image on ECS. Do not compile on the production host.

## Release Notes Strategy

- No `CHANGELOG.md` convention or automated GitHub Release workflow is present.
- Record each production deployment, backup/restore rehearsal, image identity, and post-deploy checks in a dated `docs/PRODUCTION_DEPLOYMENT_RECEIPT_*.md`.

## CI Workflow Files

- `.github/workflows/ci.yml`
- `.github/workflows/workspace-ci.yml`
- `.github/workflows/audit-platforms.yml`
- `.github/workflows/postdeploy-ci.yml`

## First-Time Setup Gaps

- No semver release/tag automation and no direct image-registry publish; manual artifact-based production deployment is the supported path.
- Production deployment always requires an explicit user request, a verified database backup, and a restore rehearsal before the service switch.
