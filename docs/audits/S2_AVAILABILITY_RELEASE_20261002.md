# S2 availability production release — 2026-10-02

Status: DEPLOYED_PENDING_AUTHENTICATED_LIVE_ACCEPTANCE.

- Source code: abae131770713465c6d65d29c1513fc88b8dc40d. Latest code/E2E/full-regression receipts independently reviewed by remote ChatGPT as release candidate.
- Switch UTC: 2026-10-02T11:38:19Z (Shanghai 19:38:19).
- Server Docker configuration ID: sha256:38c2c13c109798cf780cbee7637d78f243c31c80a1d8efcca7974fd1d5a22dbd.
- Archive SHA256: 5d30573ec43df101702ccba4649e4403a3c5ed501f2f37d1ac9f3244535bdf43; independent server checksum matched; revision label matched full source SHA.
- API and worker healthy; scheduler running; all three use candidate configuration ID.
- Schema remains f0e1d2c3b4a5. No migration file, strategy/model version, qualification or Chan-enable change. Existing API entrypoint runs its normal Alembic head check on startup; no schema delta observed.
- Existing Compose inputs preserved; candidate override changes three image IDs only. No manual refresh/recompute or database write issued.
- New backup /opt/china-fund-decision/release-s2-abae131/backup-verified.sql.gz; gzip test and >100KB size guard passed. SHA256 e5bf687aefc345b403f8a6ab442223a6dc4945a6d9589cd0b1ff0d56603f8f19. First quoting-failed backup is invalid and not acceptance evidence. No new restore rehearsal claimed for this schema-unchanged stage.
- Exact previous image b07f9ca23150db6567170d3a041afb0abf65d571fbd45ce44266585ee62366b5 retained, rollback.yml prepared against same Compose baseline and same schema; actual recovery switch NOT_RUN because no rollback trigger.
- Loopback live health, static root and anonymous private detail401 PASS. Authenticated detail response/UI and physical phone NOT_RUN; no existing authenticated website browser tab available, no credential access/bypass attempted.
- Full backend pytest exit0, 1432 collected incl conditional skips; frontend73; narrow390x844 E2E1; typecheck/build/compileall/Node syntax PASS.
- Server free disk about1.2GiB (97% used) after preserving backup/old image; no retention deletion performed.

Remaining: normal authenticated live detail GET verifies nine modules/version/actionable=false; true phone acceptance; remote final release review. WU0/WU2 and real-data UNKNOWN remain independent.
