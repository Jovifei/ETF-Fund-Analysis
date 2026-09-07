"""Only enroll the explicitly configured ETF/LOF research pool, without network."""
import re
from sqlalchemy import select
from app.models import Instrument


def seed_configured_universe(db, settings):
    items = settings.load_watchlist().get("instruments", [])
    if len(items) > 200:
        raise ValueError("configured universe exceeds 200")
    count = 0
    for item in items:
        code = str(item.get("ts_code", "")).upper()
        if item.get("kind", "ETF") not in {"ETF", "LOF"} or not re.fullmatch(r"\d{6}\.(SH|SZ)", code):
            raise ValueError("configured instrument is not a supported ETF/LOF identity")
        if not item.get("enabled", True):
            continue
        row = db.scalar(select(Instrument).where(Instrument.ts_code == code))
        if row is None:
            row = Instrument(ts_code=code, symbol=code[:6], name=item["name"], exchange=code[-2:],
                kind=item.get("kind", "ETF"), theme_l1=item.get("theme_l1"), theme_l2=item.get("theme_l2"),
                benchmark=item.get("benchmark"), enabled=True,
                metadata_json={"catalog_source": "explicit_user_configuration", "catalog_verified": False})
            db.add(row)
        else:
            row.enabled = True
        count += 1
    if not count:
        raise ValueError("configured research universe is empty")
    db.flush()
    return count
