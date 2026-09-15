"""Read filesystem capacity only; never prune, scan file contents, or touch a DB.

Run on the deployment HOST, not an unrelated container/CI runner. Exit 0 means
capacity passed this check, 3 means blocked, and 2 means the check failed.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import shutil

GIB = 1024 ** 3


def inspect_storage(paths, *, warn_percent=85.0, block_percent=90.0, min_free_gib=2.0):
    if (not all(math.isfinite(v) for v in (warn_percent, block_percent, min_free_gib))
            or not 0 < warn_percent <= block_percent <= 100 or min_free_gib < 0):
        raise ValueError('invalid_storage_thresholds')
    items = []
    for given in paths:
        path = Path(given)
        try:
            path = path.resolve(strict=True)
            if not path.is_dir():
                raise ValueError('directory_required')
            usage = shutil.disk_usage(path)
            if usage.total <= 0 or not 0 <= usage.free <= usage.total:
                raise ValueError('invalid_capacity')
            # Available-to-user bytes include reserved-space constraints.
            percent = (usage.total - usage.free) / usage.total * 100
            reasons = []
            if percent >= block_percent:
                reasons.append('disk_utilization_limit')
            if usage.free < min_free_gib * GIB:
                reasons.append('free_space_below_reserve')
            inode_percent = None
            if hasattr(os, 'statvfs'):
                fs = os.statvfs(path)
                if fs.f_files > 0:
                    inode_percent = (fs.f_files - fs.f_favail) / fs.f_files * 100
                    if inode_percent >= block_percent:
                        reasons.append('inode_utilization_limit')
            warning = percent >= warn_percent or (inode_percent is not None and inode_percent >= warn_percent)
            items.append({'path': str(path), 'total_bytes': usage.total, 'available_bytes': usage.free,
                          'unavailable_percent': round(percent, 2),
                          'inode_unavailable_percent': round(inode_percent, 2) if inode_percent is not None else None,
                          'state': 'blocked' if reasons else 'warning' if warning else 'ok', 'reasons': reasons})
        except (OSError, ValueError) as exc:
            items.append({'path': str(path), 'state': 'unknown', 'reasons': ['capacity_not_verified'],
                          'error_class': type(exc).__name__})
    unknown = not items or any(i['state'] == 'unknown' for i in items)
    blocked = any(i['state'] == 'blocked' for i in items)
    return {'schema': 'storage-preflight-v1', 'observed_at': datetime.now(timezone.utc).isoformat(),
            'scope': 'executing_host_and_explicit_paths', 'writes_performed': False,
            'deletion_performed': False, 'deployment_approved': False,
            'thresholds': {'warn_percent': warn_percent, 'block_percent': block_percent, 'min_free_gib': min_free_gib},
            'items': items, 'capacity_ready': not unknown and not blocked,
            'exit_code': 2 if unknown else 3 if blocked else 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--path', action='append', required=True, help='Existing host directory; repeat for DB/Docker/backup mounts')
    parser.add_argument('--warn-percent', type=float, default=85)
    parser.add_argument('--block-percent', type=float, default=90)
    parser.add_argument('--min-free-gib', type=float, default=2)
    args = parser.parse_args()
    try:
        result = inspect_storage(args.path, warn_percent=args.warn_percent,
                                 block_percent=args.block_percent, min_free_gib=args.min_free_gib)
    except ValueError:
        print(json.dumps({'capacity_ready': False, 'reason': 'invalid_storage_thresholds'}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
