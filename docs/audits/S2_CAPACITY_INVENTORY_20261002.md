# ETF capacity read-only inventory — 2026-10-02

Only directory sizes in /opt/china-fund-decision queried. No retention deletion.
- Application directory total7.4G; backups4.9G.
- New S2 release directory694M includes current verified backup and candidate archive.
- Several historical release archives occupy355–377M each; these are candidates for a retention review, not approved deletion targets.
- Current production sourceabae131, rollback imageb07f9ca2 and verified backup must remain recoverable.
- Server previously observed1.2GiB free/97%used. Docker system df query still running; no guessed reclaimable amount.

Next: identify used versus unreferenced artifacts and establish recoverable retention plan. Do not run docker system prune, remove volumes, or delete backups as part of F0.
