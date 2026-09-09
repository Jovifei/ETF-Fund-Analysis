"""Admin-only size measurement. No data transfer or user paths in public JSON."""
import shutil
from pathlib import Path
from sqlalchemy import func, select, text
from app.models import DailyBar, Instrument

def status(db, settings):
    dialect=db.get_bind().dialect.name
    size=None
    try:
        if dialect=="postgresql":
            with db.begin_nested():
                size=int(db.scalar(text("SELECT pg_database_size(current_database())")))
        elif dialect=="sqlite":
            size=int(db.scalar(text("PRAGMA page_count")))*int(db.scalar(text("PRAGMA page_size")))
    except Exception:
        pass
    disk=shutil.disk_usage(settings.reports_dir.parent if settings.reports_dir.parent.exists() else Path.cwd())
    rows=db.scalar(select(func.count()).select_from(DailyBar)) or 0
    count=db.scalar(select(func.count()).select_from(Instrument)) or 0
    return {"database_bytes":size,"database_backend":dialect,"daily_bar_rows":rows,
        "catalog_rows":count,"application_disk_free_bytes":disk.free,"application_disk_total_bytes":disk.total,
        "disk_scope":"application_reports_filesystem_not_remote_database_host",
        "local_drive_visible":False,"provider_called":False,
        "note":"这是运行本 API 的主机/容器；不能据此读取用户电脑 E 盘。数据库可能位于其他主机。历史只读归档可下载到 E 盘，不迁移在线数据库。"}

def prepare_plan(db, *, limit=10, minimum_scale=0, include_unknown=True):
    # Catalog reads are cheap; rank by observed size/turnover, never fabricate AUM.
    known=dict(db.execute(select(DailyBar.instrument_id,func.count()).group_by(DailyBar.instrument_id)).all())
    items=list(db.scalars(select(Instrument).where(Instrument.kind=="ETF").limit(10000)))
    from app.workspace.chart import number
    def key(item):
        meta=item.metadata_json or {}
        return (number(meta.get("market_cap_cny")) or 0, number(meta.get("turnover_cny")) or 0)
    eligible=[]
    for item in items:
        meta=item.metadata_json or {};scale=number(meta.get("market_cap_cny"))
        if known.get(item.id,0)>=250: continue
        if minimum_scale and (scale is None and not include_unknown or scale is not None and scale<minimum_scale): continue
        eligible.append(item)
    eligible.sort(key=lambda x:(-key(x)[0],-key(x)[1],x.ts_code))
    selected=eligible[:limit]
    return {"items":[{"ts_code":x.ts_code,"name":x.name,"market_cap_cny":(x.metadata_json or {}).get("market_cap_cny"),"bars":known.get(x.id,0)} for x in selected],
        "codes":[x.ts_code for x in selected],"eligible_count":len(eligible),"writes":False,
        "note":"按已知市场市值/成交额优先，未知规模排后；市值不是基金净资产。确认后才加入最多30只到研究池并下载历史，不自动收藏，不计算整个目录。"}
