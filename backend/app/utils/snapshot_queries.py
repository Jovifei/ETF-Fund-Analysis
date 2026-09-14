"""SQL-side latest-row projection, not all-history ORM hydration."""
from sqlalchemy import func, select
from app.models import Instrument


def latest_enabled(db, model, *ordering, partitions=None, where=()):
    partition = list(partitions) if partitions is not None else [model.instrument_id]
    ranked = (select(model.id, func.row_number().over(
        partition_by=partition, order_by=[*ordering, model.id.desc()]).label('rn'))
        .join(Instrument, model.instrument_id == Instrument.id)
        .where(Instrument.enabled.is_(True), *where).subquery())
    return db.scalars(select(model).join(ranked, model.id == ranked.c.id)
                      .where(ranked.c.rn == 1)).all()
