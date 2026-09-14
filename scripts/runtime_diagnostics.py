"""Read a safe Docker state projection on the deployment host. Never change containers.

A 137 exit is not, by itself, an OOM diagnosis. This report intentionally excludes
container environments, command lines, mounts, raw logs and provider credentials.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import re
import subprocess

CONTAINER = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$')
FIELDS = ('name', 'exit_code', 'oom_killed', 'restart_count', 'running',
          'memory_limit_bytes', 'started_at', 'finished_at', 'restart_policy')
FORMAT = ('{"name":{{json .Name}},"exit_code":{{.State.ExitCode}},'
          '"oom_killed":{{.State.OOMKilled}},"restart_count":{{.RestartCount}},'
          '"running":{{.State.Running}},"memory_limit_bytes":{{.HostConfig.Memory}},'
          '"started_at":{{json .State.StartedAt}},"finished_at":{{json .State.FinishedAt}},'
          '"restart_policy":{{json .HostConfig.RestartPolicy.Name}}}')


def inspect_containers(names: list[str]) -> dict:
    if not 1 <= len(names) <= 8 or any(not isinstance(n, str) or not CONTAINER.fullmatch(n) for n in names):
        raise ValueError('select_1_to_8_explicit_container_names')
    items = []
    for name in names:
        try:
            result = subprocess.run(['docker', 'inspect', '--type', 'container', '--format', FORMAT, name],
                                    capture_output=True, text=True, timeout=10, check=False)
            if result.returncode or len(result.stdout) > 16384:
                raise ValueError('inspect_unavailable')
            value = json.loads(result.stdout)
            if not isinstance(value, dict) or any(k not in value for k in FIELDS):
                raise ValueError('invalid_state_projection')
            items.append({**{k: value[k] for k in FIELDS}, 'status': 'observed'})
        except (OSError, ValueError, subprocess.SubprocessError):
            items.append({'name': name, 'status': 'unavailable'})
    return {'as_of': datetime.now(timezone.utc).isoformat(), 'containers': items,
            'root_cause': 'not_determined', 'writes_performed': False,
            'note': 'Correlate exit times with host OOM/Docker lifecycle evidence and scheduler stage logs; 137 alone is insufficient.'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container', action='append', required=True)
    args = parser.parse_args()
    try:
        result = inspect_containers(args.container)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False))
    return 0 if all(x['status'] == 'observed' for x in result['containers']) else 2


if __name__ == '__main__':
    raise SystemExit(main())
