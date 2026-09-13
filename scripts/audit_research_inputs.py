"""Export a read-only history audit from a private DB configuration, no SDK calls.

Use a backed-up local/staging database first. No URL or credentials are printed.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.services.history_audit import audit_history


def read_only_audit(settings, codes):
    url = make_url(settings.database_url)
    if url.get_backend_name() == "sqlite":
        database = Path(url.database or "")
        if not database.is_file() or any(p.is_symlink() for p in (database, *database.parents)):
            raise ValueError("existing_regular_audit_database_required")
    engine = create_engine(url, echo=False)
    try:
        if engine.dialect.name == "sqlite":
            @event.listens_for(engine, "connect")
            def query_only(connection, _record):
                connection.execute("PRAGMA query_only=ON")
        elif engine.dialect.name != "postgresql":
            raise ValueError("unsupported_audit_database")
        with Session(engine, autoflush=False) as db:
            if engine.dialect.name == "postgresql":
                db.execute(text("SET TRANSACTION READ ONLY"))
            return audit_history(db, settings, codes)
    finally:
        engine.dispose()


def summarize_audit(report: dict) -> dict:
    """Count history and indicator gaps separately, never as certification.

    A current, structurally readable history can still have an absent or
    outdated indicator. The headline must include that case without counting
    an instrument twice when both categories are blocked.
    """
    items = report["items"]
    return {
        "audit_written": True,
        "instruments": len(items),
        "history_blocked": sum(bool(item.get("blockers")) for item in items),
        "indicator_blocked": sum(bool(item.get("indicator_blockers")) for item in items),
        "blocked": sum(bool(item.get("blockers") or item.get("indicator_blockers")) for item in items),
        "qualification_granted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codes", nargs="+", required=True, help="Explicit codes, e.g. 510300.SH 588200.SH")
    parser.add_argument("--output", type=Path, required=True, help="New private JSON receipt; never overwrites")
    parser.add_argument("--fail-on-blockers", action="store_true",
        help="Write the receipt, then exit 3 for any history or indicator blocker (not a qualification grant)")
    args = parser.parse_args()
    try:
        report = read_only_audit(get_settings(), args.codes)
        summary = summarize_audit(report)
        output = args.output.absolute()
        if any(p.is_symlink() for p in (output, *output.parents)):
            raise ValueError("audit_output_symlink_rejected")
        output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        print(json.dumps(summary))
        # Code 2 denotes an audit/IO failure. Code 3 denotes a successfully
        # written audit that found blockers. Default mode remains compatible.
        return 3 if args.fail_on_blockers and summary["blocked"] else 0
    except Exception as exc:
        # Do not print SQLAlchemy/OS exception strings: they can contain URLs,
        # paths, passwords or rows. The type is sufficient for private diagnosis.
        print(json.dumps({"audit_written": False, "failure_class": type(exc).__name__}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
