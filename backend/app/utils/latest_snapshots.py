"""最新快照的高效查询助手（替代「全量加载后 Python 取最新」的线性劣化模式）。

所有 helper 每次只发 1-2 条 SQL：
* 先按分组键取 max(排序键)，再回表取对应行；
* 同组多行（同日多次生成）在 Python 内按 generated_at 二次去重，行数有界。
"""
from __future__ import annotations

from typing import Iterable

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models import ForecastSnapshot, SignalSnapshot


def latest_forecast_map(
    db: Session, instrument_ids: Iterable[int] | None = None
) -> dict[int, dict[int, ForecastSnapshot]]:
    """每个 (instrument, horizon) 的最新 ForecastSnapshot。"""
    grouped = (
        select(
            ForecastSnapshot.instrument_id.label("instrument_id"),
            ForecastSnapshot.horizon.label("horizon"),
            func.max(ForecastSnapshot.as_of_date).label("max_date"),
        )
        .group_by(ForecastSnapshot.instrument_id, ForecastSnapshot.horizon)
    )
    if instrument_ids is not None:
        ids = list(instrument_ids)
        if not ids:
            return {}
        grouped = grouped.where(ForecastSnapshot.instrument_id.in_(ids))
    subquery = grouped.subquery()
    rows = db.scalars(
        select(ForecastSnapshot).join(
            subquery,
            and_(
                ForecastSnapshot.instrument_id == subquery.c.instrument_id,
                ForecastSnapshot.horizon == subquery.c.horizon,
                ForecastSnapshot.as_of_date == subquery.c.max_date,
            ),
        )
    ).all()
    result: dict[int, dict[int, ForecastSnapshot]] = {}
    for row in rows:
        bucket = result.setdefault(row.instrument_id, {})
        existing = bucket.get(int(row.horizon))
        if existing is None or (row.generated_at or "") >= (existing.generated_at or ""):
            bucket[int(row.horizon)] = row
    return result


def latest_signal_map(
    db: Session, instrument_ids: Iterable[int] | None = None
) -> dict[int, SignalSnapshot]:
    """每个 instrument 的最新 SignalSnapshot（替代 as_of_time 升序全表扫描）。"""
    grouped = select(
        SignalSnapshot.instrument_id.label("instrument_id"),
        func.max(SignalSnapshot.as_of_time).label("max_time"),
    ).group_by(SignalSnapshot.instrument_id)
    if instrument_ids is not None:
        ids = list(instrument_ids)
        if not ids:
            return {}
        grouped = grouped.where(SignalSnapshot.instrument_id.in_(ids))
    subquery = grouped.subquery()
    rows = db.scalars(
        select(SignalSnapshot).join(
            subquery,
            and_(
                SignalSnapshot.instrument_id == subquery.c.instrument_id,
                SignalSnapshot.as_of_time == subquery.c.max_time,
            ),
        )
    ).all()
    result: dict[int, SignalSnapshot] = {}
    for row in rows:
        existing = result.get(row.instrument_id)
        if existing is None or row.id > existing.id:
            result[row.instrument_id] = row
    return result
