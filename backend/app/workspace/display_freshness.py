"""Read-time labels only. Never alter persisted evidence or signal eligibility."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def local_time(value, timezone='Asia/Shanghai'):
    zone = ZoneInfo(timezone) if isinstance(timezone, str) else timezone
    if value is None:
        return None
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else value
        if not isinstance(result, datetime):
            return None
        return result.replace(tzinfo=zone) if result.tzinfo is None else result.astimezone(zone)
    except (ValueError, TypeError, OverflowError):
        return None


def context_display(observation, *, now=None, context_kind='index', timezone='Asia/Shanghai', max_age_minutes=60):
    zone = ZoneInfo(timezone) if isinstance(timezone, str) else timezone
    now = local_time(now, zone) if now is not None else datetime.now(zone)
    if now is None:
        raise ValueError('invalid assessment time')
    obs = observation or {}
    source = local_time(obs.get('source_timestamp'), zone)
    fetched = local_time(obs.get('fetched_at'), zone)
    stored = str(obs.get('freshness') or 'unknown')
    date_only = bool(source and context_kind == 'index' and source.time().replace(tzinfo=None) == datetime.min.time())
    age = (now-source).total_seconds() if source else None
    state, note = 'unavailable', '尚无可核实的数据时间；抓取时间不能替代源时间。'
    if obs.get('is_mock'):
        state, note = 'mock', '演示数据，不是市场行情。'
    elif source is not None and source > now + timedelta(minutes=5):
        state, note = 'unverified', '源时间在未来，请核对时区与上游字段。'
    elif source is not None and obs.get('verification_status') != 'verified':
        state, note = 'unverified', '源记录未验证；有数值不等于实时或可操作。'
    elif source is not None and stored in {'degraded', 'unavailable', 'unknown'}:
        state, note = stored, '保留原始退化或未知状态，不因刚抓取就升级资格。'
    elif source is not None and date_only:
        state, note = 'historical', '日期粒度的指数观察，不是午夜实时报价；是否最新收盘需核对交易日。'
    elif source is not None and (stored == 'stale' or age > max_age_minutes * 60):
        state, note = 'stale', '源时间已超过展示窗口或上游标为过期；仍保留历史值。'
    elif source is not None:
        state, note = 'recent_observation', '源观察在展示窗口内；不代表已取得实时或交易资格。'
    return {'status': state, 'stored_freshness': stored, 'checked_at': now.isoformat(),
            'source_time': source.isoformat() if source else None,
            'fetched_at': fetched.isoformat() if fetched else None,
            'date_label': source.date().isoformat() if source else None,
            'precision': 'date_assumed' if date_only else 'timestamp' if source else 'unknown',
            'age_minutes': round(age/60, 1) if age is not None and age >= 0 else None,
            'note': note, 'actionable': False}
