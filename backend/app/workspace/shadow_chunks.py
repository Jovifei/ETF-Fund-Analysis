"""Chunked delivery for local-display-v2 bundles larger than one 16 MiB request.

Contract (07 §7.1/§7.4): every request stays <=16 MiB on the wire *and* <=16 MiB
decoded; the reassembled canonical bundle stays within the 64 MiB sync domain.
Each chunk request is HMAC-signed over ``meta || '\\n' || wire`` so the index,
total and digests cannot be altered.  Nothing becomes visible until ``commit``:
the receiver reassembles, checks the whole-body SHA-256 (``upload_id``) and then
hands the bytes to the existing atomic v1/v2 publish path, so receipts keep the
existing v1/v2 shape.  Staging is bounded, single-active and garbage collected.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import time
from io import BytesIO
from pathlib import Path

CHUNK_MAX_WIRE_BYTES = 16 * 1024 * 1024
CHUNK_MAX_DECODED_BYTES = 16 * 1024 * 1024
MAX_TOTAL_DECODED_BYTES = 64 * 1024 * 1024
MAX_CHUNKS = 4
STAGING_TTL_SECONDS = 900
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class ChunkRejected(ValueError):
    """Deterministic rejection (bad identity/size/order); never retried blindly."""


class ChunkBusy(RuntimeError):
    """Another upload is staging; caller should retry the same bundle later."""


def chunk_meta(upload_id: str, index: int, total: int, chunk_sha256: str) -> bytes:
    return f"chunk-v1:{upload_id}:{index}:{total}:{chunk_sha256}".encode("ascii")


def commit_body(upload_id: str, total: int) -> bytes:
    return json.dumps({"upload_id": upload_id, "total": total}, separators=(",", ":"), sort_keys=True).encode("ascii")


def split_canonical(body: bytes, *, chunk_size: int = CHUNK_MAX_DECODED_BYTES) -> list[bytes]:
    if chunk_size <= 0 or chunk_size > CHUNK_MAX_DECODED_BYTES:
        raise ValueError("invalid chunk size")
    if len(body) > MAX_TOTAL_DECODED_BYTES:
        raise ValueError("bundle exceeds 64 MiB sync domain")
    parts = [body[i : i + chunk_size] for i in range(0, len(body), chunk_size)] or [b""]
    if len(parts) > MAX_CHUNKS:
        raise ValueError("too many chunks")
    return parts


def _validate_ids(upload_id: str, index: int, total: int) -> None:
    if not isinstance(upload_id, str) or not _HEX64.fullmatch(upload_id):
        raise ChunkRejected("invalid upload id")
    if type(total) is not int or not 1 <= total <= MAX_CHUNKS:
        raise ChunkRejected("invalid chunk total")
    if type(index) is not int or not 0 <= index < total:
        raise ChunkRejected("invalid chunk index")


class ChunkStaging:
    def __init__(self, root: str | Path, *, now=time.time):
        self.root = Path(root) / "chunks"
        self.now = now

    def _prepare(self) -> None:
        if self.root.is_symlink() or (self.root.parent.exists() and self.root.parent.is_symlink()):
            raise ChunkRejected("unsafe staging root")
        self.root.mkdir(parents=True, exist_ok=True)

    def gc(self) -> None:
        self._prepare()
        cutoff = self.now() - STAGING_TTL_SECONDS
        for entry in self.root.iterdir():
            if entry.is_symlink():
                continue
            if entry.is_dir() and _HEX64.fullmatch(entry.name) and entry.stat().st_mtime < cutoff:
                shutil.rmtree(entry, ignore_errors=True)

    def staged_bytes(self) -> int:
        total = 0
        for entry in self.root.glob("*/*.part"):
            total += entry.stat().st_size
        return total

    def put(self, upload_id: str, index: int, total: int, chunk_sha256: str, wire: bytes) -> dict:
        _validate_ids(upload_id, index, total)
        if not isinstance(chunk_sha256, str) or not _HEX64.fullmatch(chunk_sha256):
            raise ChunkRejected("invalid chunk digest")
        if len(wire) > CHUNK_MAX_WIRE_BYTES:
            raise ChunkRejected("chunk wire too large")
        try:
            with gzip.GzipFile(fileobj=BytesIO(wire)) as stream:
                decoded = stream.read(CHUNK_MAX_DECODED_BYTES + 1)
        except Exception:
            raise ChunkRejected("invalid gzip chunk") from None
        if len(decoded) > CHUNK_MAX_DECODED_BYTES:
            raise ChunkRejected("chunk decoded too large")
        if hashlib.sha256(decoded).hexdigest() != chunk_sha256:
            raise ChunkRejected("chunk digest mismatch")
        self.gc()
        active = [p for p in self.root.iterdir() if p.is_dir() and not p.is_symlink() and p.name != upload_id]
        if active:
            raise ChunkBusy("another upload is staging")
        if self.staged_bytes() + len(decoded) > MAX_TOTAL_DECODED_BYTES:
            raise ChunkRejected("staging budget exhausted")
        directory = self.root / upload_id
        directory.mkdir(exist_ok=True)
        meta_path = directory / "total"
        if meta_path.exists():
            if meta_path.read_text() != str(total):
                raise ChunkRejected("chunk total changed")
        else:
            meta_path.write_text(str(total))
        target = directory / f"{index}.part"
        tmp = directory / f".{index}.{os.getpid()}.tmp"
        with open(tmp, "wb") as handle:
            handle.write(decoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
        return {"upload_id": upload_id, "index": index, "status": "staged"}

    def assemble(self, upload_id: str, total: int) -> bytes:
        _validate_ids(upload_id, 0, total)
        directory = self.root / upload_id
        if not directory.is_dir() or directory.is_symlink():
            raise ChunkRejected("unknown upload")
        try:
            if (directory / "total").read_text() != str(total):
                raise ChunkRejected("chunk total mismatch")
            buffer = bytearray()
            for index in range(total):
                part = directory / f"{index}.part"
                if not part.is_file() or part.is_symlink():
                    raise ChunkRejected("missing chunk")
                buffer.extend(part.read_bytes())
                if len(buffer) > MAX_TOTAL_DECODED_BYTES:
                    raise ChunkRejected("assembled bundle too large")
            if hashlib.sha256(bytes(buffer)).hexdigest() != upload_id:
                raise ChunkRejected("assembled digest mismatch")
            return bytes(buffer)
        finally:
            # One commit attempt per staging: success publishes, failure needs a clean re-send.
            shutil.rmtree(directory, ignore_errors=True)
