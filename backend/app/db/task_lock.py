"""A pipeline lease held to outer transaction end, including across processes.

PostgreSQL remains the recommended multi-writer deployment. SQLite file locks
coordinate our pipeline writers; WAL/busy_timeout handle short API/heartbeat
writes. They are not a distributed lock and must live on the same local disk.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path
from sqlalchemy import event


class PipelineLockBusy(RuntimeError):
    pass


class PipelineFileLock:
    def __init__(self, path: Path):
        self.path = path
        self.fd = None

    def acquire(self):
        if self.path.is_symlink():
            raise PipelineLockBusy('unsafe_pipeline_lock_path')
        flags = os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0)
        fd = os.open(self.path, flags, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise PipelineLockBusy('unsafe_pipeline_lock_file')
            if os.name == 'nt':
                import msvcrt
                if os.fstat(fd).st_size == 0:
                    os.write(fd, b'0')
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, PipelineLockBusy):
            os.close(fd)
            raise PipelineLockBusy('pipeline_writer_busy') from None
        self.fd = fd
        return self

    def release(self):
        if self.fd is not None:
            fd, self.fd = self.fd, None
            if os.name == 'nt':
                import msvcrt
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def sqlite_pipeline_lease(db):
    """Acquire once for a Session; release only after outer commit/rollback."""
    database = db.get_bind().url.database
    if not database or database == ':memory:':
        return False
    if db.info.get('pipeline_file_lease'):
        return True
    lock = PipelineFileLock(Path(str(Path(database).resolve()) + '.pipeline.lock')).acquire()
    db.info['pipeline_file_lease'] = lock
    if not db.info.get('pipeline_file_listener'):
        def ended(session, transaction):
            if transaction.parent is None:
                lease = session.info.pop('pipeline_file_lease', None)
                if lease:
                    lease.release()
        event.listen(db, 'after_transaction_end', ended)
        db.info['pipeline_file_listener'] = True
    return True
