"""One non-stealable writer lock and disk budget for the complete sync domain."""
from contextlib import contextmanager
from pathlib import Path
from threading import get_ident

from app.workspace.local_schedule import LocalRunLock


class SyncDomain:
    def __init__(self, root, *, roots=(), max_bytes=64 * 1024 * 1024):
        self.root = Path(root)
        self.roots = tuple({Path(p).absolute() for p in (root, *roots)})
        if type(max_bytes) is not int or max_bytes <= 0:
            raise ValueError("invalid sync domain budget")
        self.max_bytes = max_bytes
        self.depth = 0
        self.held_bytes = 0
        self.owner = None

    @contextmanager
    def locked(self):
        if self.depth and self.owner == get_ident():
            self.depth += 1
            try:
                yield self
            finally:
                self.depth -= 1
            return
        if self.root.is_symlink():
            raise ValueError("unsafe sync domain root")
        lock = LocalRunLock(self.root / ".sync.lock")
        import time
        for attempt in range(21):
            if lock.acquire(reclaim_stale=False):
                break
            if attempt == 20:
                raise ValueError("sync domain writer busy")
            time.sleep(0.05)
        self.depth = 1
        self.owner = get_ident()
        try:
            yield self
        finally:
            self.depth = 0
            self.owner = None
            lock.release()

    def used_bytes(self):
        files = set()
        for root in self.roots:
            if root.is_symlink():
                raise ValueError("unsafe sync domain path")
            for path in root.rglob("*"):
                if path.is_symlink():
                    raise ValueError("unsafe sync domain path")
                if path.is_file():
                    files.add(path.absolute())
        return sum(path.stat().st_size for path in files)

    def reserve(self, extra):
        if type(extra) is not int or extra < 0 or self.used_bytes() + self.held_bytes + extra > self.max_bytes:
            raise ValueError("sync domain capacity exceeded")

    @contextmanager
    def hold(self, size):
        self.reserve(size)
        self.held_bytes += size
        try:
            yield
        finally:
            self.held_bytes -= size
