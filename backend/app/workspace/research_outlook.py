"""Bounded price-only research. Cache validity is not data/strategy qualification."""
from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
import math

import pandas as pd
from sqlalchemy import func, select

from app.core.config import get_settings
from app.models import DailyBar, Instrument
from app.providers.data_contract import price_history_issue
from app.services.forecast_service import similarity_forecast
from app.services.settlement import settled_session
from app.utils.feature_store import build_feature_frame
from app.workspace.models import WorkspacePreference
from app.workspace.protocol import content_hash

VERSION = 'price-similarity-research-v106-1-5-20'
FEATURES = ('return_5d', 'return_20d', 'ma_gap_5_20', 'macd_norm', 'kdj_j', 'rsi14', 'atr_pct')
HORIZONS = (1, 5, 20)
PREFIX = 'v104:outlook:'  # Keep storage identity; old versions are visibly invalidated.
MAX_BARS = 2000


def config_hash(settings):
    return content_hash({'indicator': settings.load_strategy()['indicator'], 'model': VERSION,
                         'features': FEATURES, 'horizons': HORIZONS, 'neighbors': 60,
                         'minimum_neighbors': 25, 'maximum_confidence': 40, 'max_bars': MAX_BARS})


def ended_rows(rows, settings, at=None):
    target = settled_session(settings, at).isoformat()
    unique = {}
    for row in rows:
        day = date.fromisoformat(row['date']).isoformat()
        if day > target:
            continue
        if day in unique:
            raise ValueError('duplicate_historical_date')
        prices = [row[k] for k in ('open', 'high', 'low', 'close')]
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in prices):
            raise ValueError('invalid_historical_ohlc')
        unique[day] = dict(row)
    result = [unique[k] for k in sorted(unique)]
    if not result:
        return result
    mocks = {'mock' in str(r.get('source', '')).lower() for r in result}
    if len({r.get('adjust', 'none') for r in result}) > 1 or len(mocks) > 1:
        raise ValueError('mixed_historical_basis_or_mock')
    issue = price_history_issue([SimpleNamespace(trade_date=date.fromisoformat(r['date']),
        adjust=r.get('adjust', 'none'), **{k: r[k] for k in ('open','high','low','close')}) for r in result])
    if issue:
        raise ValueError(issue)
    return result


def compute(rows, settings, *, at=None):
    rows = ended_rows(rows, settings, at)
    metadata = {'model_version': VERSION, 'config_hash': config_hash(settings),
                'input_hash': content_hash(rows), 'source_as_of': rows[-1]['date'] if rows else None,
                'source_bar_count': len(rows), 'feature_names': list(FEATURES),
                'created_at': datetime.now(UTC).isoformat(), 'actionable': False,
                'not_strategy_output': True,
                'qualification': 'mock' if settings.market_provider == 'mock' or any('mock' in str(r.get('source','')).lower() for r in rows) else 'not_qualified'}
    if len(rows) < 250:
        return {**metadata, 'status': 'unavailable', 'reason': 'history_below_250_ended_bars', 'forecasts': {}}
    raw = pd.DataFrame(rows).rename(columns={'date': 'trade_date'})
    # Unknown inputs remain unknown. Price features do not need invented volume.
    raw['volume'] = float('nan')
    raw['amount'] = float('nan')
    rich = build_feature_frame(raw, settings.load_strategy()['indicator']).frame
    results = {}
    for horizon in HORIZONS:
        value = similarity_forecast(rich, horizon=horizon, neighbors=60, minimum_neighbors=25,
                                    maximum_confidence=40, feature_columns=FEATURES)
        results[str(horizon)] = {k: getattr(value, k) for k in ('p_up','expected_return','q10','q50','q90','sample_count','confidence')}
        results[str(horizon)].update(horizon=horizon, model_version=VERSION,
            calibration_status='not_calibrated', probability_label='historical_frequency',
            as_of_date=rows[-1]['date'], actionable=False, diagnostics=value.diagnostics,
            **{k: v for k, v in value.corridor.items() if k.startswith('terminal_price')},
            explanation='历史价格相似样本研究；量能、新闻和执行成本未纳入。重叠样本不是独立样本，未经样本外校准。')
    usable = any(v['expected_return'] is not None for v in results.values())
    return {**metadata, 'status': 'research' if usable else 'unavailable',
            'reason': None if usable else 'insufficient_valid_neighbors', 'forecasts': results if usable else {}}


def input_rows(db, instrument_id):
    bases = db.scalars(select(DailyBar.adjust).where(DailyBar.instrument_id == instrument_id).distinct()).all()
    adjust = 'none' if 'none' in bases else bases[0] if len(bases) == 1 else None
    if adjust is None:
        return []
    # Price-only lineage deliberately contains only the actual consumed columns.
    selected = db.execute(select(DailyBar.trade_date, DailyBar.open, DailyBar.high, DailyBar.low,
        DailyBar.close, DailyBar.source, DailyBar.adjust).where(DailyBar.instrument_id == instrument_id,
        DailyBar.adjust == adjust).order_by(DailyBar.trade_date.desc()).limit(MAX_BARS)).all()
    return [dict(date=r.trade_date.isoformat(), open=r.open, high=r.high, low=r.low, close=r.close,
                 source=r.source, adjust=r.adjust) for r in reversed(selected)]


def refresh(db, settings, codes):
    query = select(Instrument).where(Instrument.kind.in_(('ETF', 'LOF')))
    query = query.where(Instrument.ts_code.in_(codes)) if codes else query.where(Instrument.enabled.is_(True))
    requested = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    instruments = db.scalars(query.order_by(Instrument.ts_code).limit(30)).all()
    failures, saved, unavailable = [], 0, 0
    for inst in instruments:
        try:
            with db.begin_nested():
                result = compute(input_rows(db, inst.id), settings)
                key = PREFIX + inst.ts_code
                cache = db.get(WorkspacePreference, key)
                if cache is None:
                    cache = WorkspacePreference(owner_scope=key, user_id=None)
                    db.add(cache)
                cache.settings_json = {**result, 'ts_code': inst.ts_code}
                db.flush()
                saved += 1
                unavailable += result['status'] != 'research'
        except Exception as exc:
            allowed = {'unexplained_price_discontinuity', 'unknown_price_basis', 'invalid_ohlc',
                       'duplicate_historical_date', 'mixed_historical_basis_or_mock', 'invalid_historical_ohlc'}
            reason = str(exc) if isinstance(exc, ValueError) and str(exc) in allowed else type(exc).__name__
            failures.append({'ts_code': inst.ts_code, 'reason': reason})
    complete = bool(requested and saved == requested and not failures and not unavailable)
    return {'status': 'succeeded' if complete else 'partial' if saved else 'failed',
            'instruments': saved, 'requested': requested, 'selected': len(instruments),
            'unavailable': unavailable, 'coverage_complete': complete, 'failures': failures, 'actionable': False}


def read(db, codes, settings=None):
    settings = settings or get_settings()
    if not codes:
        return {}
    if len(codes) > 200:
        raise ValueError('outlook_read_limit')
    ids = dict(db.execute(select(Instrument.ts_code, Instrument.id).where(Instrument.ts_code.in_(codes))).all())
    caches = db.scalars(select(WorkspacePreference).where(WorkspacePreference.owner_scope.in_([PREFIX+c for c in codes])))
    result = {}
    for cache in caches:
        value = dict(cache.settings_json or {})
        code = value.get('ts_code')
        if code not in ids:
            continue
        reason = None
        if value.get('model_version') != VERSION or value.get('config_hash') != config_hash(settings):
            reason = 'research_version_or_config_changed'
        else:
            try:
                rows = ended_rows(input_rows(db, ids[code]), settings)
                if content_hash(rows) != value.get('input_hash'):
                    reason = 'research_inputs_changed'
            except (ValueError, TypeError, KeyError):
                reason = 'research_history_blocked'
        forecasts = {} if reason else {k: {**v, 'cache_note': '冻结于 '+str(value.get('source_as_of'))+'；仅为历史价格研究'} for k,v in value.get('forecasts', {}).items()}
        result[code] = {**value, 'forecasts': forecasts, 'cache_status': 'invalidated' if reason else 'input_matched',
                        'cache_reason': reason, 'actionable': False}
    return result
