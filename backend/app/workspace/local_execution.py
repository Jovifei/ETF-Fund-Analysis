"""Bind local execution configuration without persisting private path/content."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from app.workspace.shadow_bundle import digest


def execution_identity(config_bytes: bytes, *, database: Path, profile: str, provider: str,
                       private_research: bool, closed_session_research: bool, sync_url: str) -> dict:
    if not isinstance(config_bytes, bytes) or profile not in {'live', 'mock'}:
        raise ValueError('explicit execution configuration required')
    if type(private_research) is not bool or type(closed_session_research) is not bool:
        raise ValueError('explicit execution scope required')
    path = Path(database)
    if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()) or not path.is_file():
        raise ValueError('owned local database identity required')
    stat = path.stat()
    file_hash = hashlib.sha256(config_bytes).hexdigest()
    contract = {'version': 'local-execution-identity-v1', 'config_file_hash': file_hash,
                'database_identity': [os.path.normcase(str(path.resolve())), stat.st_dev, stat.st_ino],
                'profile': profile, 'provider': provider, 'private_research': private_research,
                'closed_session_research': closed_session_research, 'sync_url': sync_url}
    return {'execution_hash': digest(contract), 'config_file_hash': file_hash}
