# Integration v4 final retry

This marker intentionally retriggers the all-features integration workflow after the one-shot workflow fixed the last source-level ShellCheck warning in `scripts/qualify_postgres.sh`.

The previous automated push used `GITHUB_TOKEN`, which GitHub intentionally does not use to recursively trigger workflows. This repository commit provides the final user-originated trigger. The marker contains no secrets or environment data.
