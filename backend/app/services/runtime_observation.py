"""Small, credential-free stage observations. Logging never commits the task DB."""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import re
import sys


def stage_sample(stage: str, state: str, *, elapsed_seconds: float = 0) -> dict:
    sample = {'stage': re.sub(r'[^a-zA-Z0-9_-]', '', stage)[:64],
              'state': state if state in {'started', 'succeeded', 'partial', 'failed', 'stopped'} else 'unknown',
              'at': datetime.now(timezone.utc).isoformat(), 'pid': os.getpid(),
              'elapsed_seconds': round(max(0.0, elapsed_seconds), 3), 'rss_bytes': None,
              'peak_rss_bytes': None, 'cgroup_memory_bytes': None}
    try:
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        sample['peak_rss_bytes'] = int(peak * (1 if sys.platform == 'darwin' else 1024))
    except (ImportError, OSError, ValueError):
        pass
    try:
        for line in Path('/proc/self/status').read_text(encoding='ascii').splitlines():
            if line.startswith('VmRSS:'):
                sample['rss_bytes'] = int(line.split()[1]) * 1024
                break
    except (OSError, ValueError, IndexError):
        pass
    try:
        sample['cgroup_memory_bytes'] = int(Path('/sys/fs/cgroup/memory.current').read_text(encoding='ascii').strip())
    except (OSError, ValueError):
        pass
    return sample
