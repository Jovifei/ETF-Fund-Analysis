"""Bounded public ETF/industry/concept observation; no database or credentials.

Exit 0 means the observation report was written, NOT provider qualification.
Inspect each capability's status/count. No task, signal or model is invoked.
"""
from __future__ import annotations
import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    from app.core.config import Settings
    from app.providers.akshare import AKShareProvider
    from app.providers.catalog import catalog_records
    report = {'observed_at': datetime.now(UTC).isoformat(), 'database_written': False,
              'credentials_used': False, 'models_called': False, 'actionable': False,
              'scope': 'single_runner_public_observation_not_qualification', 'capabilities': {}}
    provider = None
    try:
        settings = Settings(_env_file=None, market_provider='akshare', tushare_token='',
                            akshare_timeout_seconds=8, allow_mock_fallback=False)
        provider = AKShareProvider(settings)
        calls = {'catalog': lambda: catalog_records(provider),
                 'industry': provider.fetch_sector_snapshots,
                 'concept': provider.fetch_concept_snapshots}
        for name, call in calls.items():
            started = time.monotonic()
            try:
                rows = call()
                item = {'status': 'available' if rows else 'empty', 'count': len(rows or [])}
                if name == 'catalog':
                    item['coverage'] = getattr(rows, 'coverage', {})
                else:
                    item['source_dates'] = sorted({str(row.trade_date) for row in rows})
                report['capabilities'][name] = item
            except Exception as exc:
                report['capabilities'][name] = {'status': 'unavailable', 'count': 0, 'failure_class': type(exc).__name__}
            report['capabilities'][name]['elapsed_seconds'] = round(time.monotonic()-started, 3)
    except Exception as exc:
        report['initialization'] = {'status': 'unavailable', 'failure_class': type(exc).__name__}
    finally:
        if provider is not None:
            try:
                provider.close()
            except Exception as exc:
                report['cleanup_failure_class'] = type(exc).__name__
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
