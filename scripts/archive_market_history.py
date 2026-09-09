"""Read-only market history export to a private offline archive. No credentials or holdings.

This is NOT an import/qualification path. Copy only finalized output files between
machines; never sync the live database. No provider or AI is called by this CLI.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from datetime import UTC, datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from sqlalchemy import select
from app.models import DailyBar, Instrument
from app.workspace.models import WorkspacePreference
from app.workspace.protocol import canonical_bytes


def export(db, destination: Path, codes: list[str], limit: int = 1500) -> dict:
    if not 1 <= len(codes) <= 100 or len(set(codes)) != len(codes):
        raise ValueError('select 1..100 distinct ETF/LOF codes')
    if any(not re.fullmatch(r'\d{6}\.(SH|SZ|BJ)', code) for code in codes) or not 30 <= limit <= 5000:
        raise ValueError('invalid codes or limit')
    destination = destination.absolute()
    if any(part.is_symlink() for part in (destination, *destination.parents)):
        raise ValueError('symlinks not allowed for archive output')
    # A new directory is an explicit publication boundary; no overwrite.
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    path=destination/'market-history.jsonl.gz'
    count=0; coverage=[]
    try:
        with gzip.open(path,'wb') as stream:
            for code in codes:
                inst=db.scalar(select(Instrument).where(Instrument.ts_code==code, Instrument.kind.in_(('ETF','LOF'))))
                bars=list(db.scalars(select(DailyBar).where(DailyBar.instrument_id==inst.id).order_by(DailyBar.trade_date.desc(),DailyBar.id.desc()).limit(limit))) if inst else []
                for bar in reversed(bars):
                    value={'kind':'etf_bar','ts_code':code,'date':bar.trade_date.isoformat(),
                       'open':bar.open,'high':bar.high,'low':bar.low,'close':bar.close,'volume':bar.volume,
                       'amount':bar.amount,'adjust':bar.adjust,'source':bar.source,'actionable':False}
                    stream.write(canonical_bytes(value)+b'\n'); count+=1
                coverage.append({'ts_code':code,'rows':len(bars),'source_as_of':bars[0].trade_date.isoformat() if bars else None})
            for cache in db.scalars(select(WorkspacePreference).where(WorkspacePreference.owner_scope.startswith('system:index-history:'))):
                stream.write(canonical_bytes({'kind':'index_cache','cache':cache.settings_json,'actionable':False})+b'\n')
        os.chmod(path,0o600)
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        manifest={'schema_version':'market-history-archive-v1','created_at':datetime.now(UTC).isoformat(),
             'file':path.name,'sha256':digest,'etf_rows':count,'coverage':coverage,
             'includes_holdings':False,'includes_credentials':False,'provider_called':False,
             'actionable':False,'purpose':'offline_backup_not_trusted_import'}
        target=destination/'manifest.json'
        target.write_bytes(canonical_bytes(manifest)+b'\n');os.chmod(target,0o600)
        return manifest
    except Exception:
        # Deliberately leave an incomplete directory without a manifest.
        # Callers must never treat that as a finished archive.
        raise


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--codes',nargs='+',required=True)
    parser.add_argument('--limit',type=int,default=1500)
    args=parser.parse_args()
    from app.db.session import SessionLocal
    with SessionLocal() as db:
        manifest=export(db,args.output,args.codes,args.limit)
        db.rollback()
    print(json.dumps({'rows':manifest['etf_rows'],'sha256':manifest['sha256'],'provider_called':False}))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
