#!/usr/bin/env python3
"""Owner-local SMTP setup and independent notification dispatcher (no collection)."""
from __future__ import annotations
import argparse
from datetime import datetime,timedelta,timezone
from getpass import getpass
import json
from pathlib import Path
import re
import sqlite3
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from app.workspace.local_notifications import (NotificationQueue,SMTPConfig,SMTPTransport,
    save_smtp_config,load_smtp_config,set_smtp_enabled,private_directory)
from app.workspace.local_digest import build_digest,build_status_digest
from app.workspace.local_schedule import LocalRunLock
from app.workspace.local_atomic import write_json_atomic
from app.workspace.shadow_client import _unique_object

TZ=ZoneInfo("Asia/Shanghai")
MAIL_SLOTS=("11:40","14:30","14:45","18:00")


def owned_root(root):
    root=Path(root).absolute()
    if not (root/".local-live").is_file() or root.is_symlink() or (hasattr(root,"is_junction") and root.is_junction()):
        raise ValueError("owned local-live root required")
    return root


def configure(root,*,ask=input,secret=getpass,enabled=False,owner_confirmed=False,overwrite=False):
    root=owned_root(root)
    if enabled and not owner_confirmed:
        raise ValueError("confirm old mail owner switchover before activation")
    mailbox=ask("SMTP登录邮箱（仅在本机输入）：").strip()
    host=ask("SMTP服务器（例如 smtp.qq.com / smtp.163.com）：").strip()
    port=int(ask("TLS端口（465 或 587）：").strip())
    mode=ask("TLS模式（ssl / starttls）：").strip()
    recipient=ask("收件邮箱（回车使用登录邮箱）：").strip() or mailbox
    password=secret("邮箱授权码（隐藏输入；不会写入仓库）：")
    config=SMTPConfig(host=host,port=port,mode=mode,username=mailbox,password=password,sender=mailbox,recipient=recipient)
    path=save_smtp_config(root,config,enabled=enabled,owner_confirmed=owner_confirmed,overwrite=overwrite)
    return {"state":"CONFIGURED","enabled":enabled,"owner_confirmed":owner_confirmed,"config_file":str(path)}


def read_delivery(root,session,slot,code_sha,config_hash):
    path=root/"state"/"schedule.sqlite3"
    if not path.is_file() or path.is_symlink():
        return None
    c=sqlite3.connect(path.as_uri()+"?mode=ro",uri=True)
    c.row_factory=sqlite3.Row
    try:
        c.execute("PRAGMA query_only=ON")
        row=c.execute("SELECT * FROM attempts WHERE slot_id=? AND status='DELIVERED' AND code_sha=? AND config_hash=? ORDER BY sequence DESC LIMIT 1",
                      (f"{session} {slot}",code_sha,config_hash)).fetchone()
    finally:
        c.close()
    if row is None or not isinstance(row["bundle_file"],str) or not re.fullmatch(r"bundle_[1-9][0-9]*\.json",row["bundle_file"]):
        return None
    bundle_path=root/"outbox"/row["bundle_file"]
    receipt_path=bundle_path.with_suffix(".receipt.json")
    for item in (bundle_path.parent,bundle_path,receipt_path):
        if item.is_symlink() or (hasattr(item,"is_junction") and item.is_junction()):
            raise ValueError("owned immutable mail input required")
    if not bundle_path.is_file() or bundle_path.stat().st_size>64*1024*1024 or not receipt_path.is_file() or receipt_path.stat().st_size>4096:
        return None
    bundle=json.loads(bundle_path.read_text(encoding="utf-8"),object_pairs_hook=_unique_object)
    receipt=json.loads(receipt_path.read_text(encoding="utf-8"),object_pairs_hook=_unique_object)
    if json.loads(row["receipt"],object_pairs_hook=_unique_object)!=receipt:
        raise ValueError("ledger and file receipt differ")
    return bundle,receipt


def dispatch(root,*,now,code_sha,config_hash,dry_run=False,recipient_id=None,slots=MAIL_SLOTS,
             calendar_verified=None,analyzer=None,consumer=None):
    root=owned_root(root)
    if (now.tzinfo is None or not re.fullmatch(r"[a-f0-9]{40}",code_sha)
            or not re.fullmatch(r"[a-f0-9]{64}",config_hash)):
        raise ValueError("fixed notification source identity required")
    local=now.astimezone(TZ);session=local.date().isoformat()
    if calendar_verified is None:
        from app.services.trading_calendar_service import TradingCalendarService
        decision=TradingCalendarService().decision(local.date())
        if not decision.verified:
            return {"state":"CALENDAR_UNKNOWN","queued":0,"notices":[]}
        calendar_verified=decision.is_trade_day
    if calendar_verified is not True:
        return {"state":"NON_TRADING_SESSION","queued":0,"notices":[]}
    config,policy=None,{"enabled":False,"owner_confirmed":False}
    if not dry_run:
        try:
            config,policy=load_smtp_config(root)
            recipient_id=config.recipient_id
        except ValueError:
            return {"state":"CONFIG_REQUIRED","queued":0,"notices":[]}
    recipient_id=recipient_id or "0"*64
    queue_root=root/"preview" if dry_run else root
    queue=NotificationQueue(queue_root)
    lock=LocalRunLock(queue.directory/".dispatch.lock")
    if not lock.acquire():
        return {"state":"BUSY","queued":0,"notices":[]}
    queued,notices=0,[]
    try:
        for slot in slots:
            planned=datetime.fromisoformat(session+"T"+slot).replace(tzinfo=TZ)
            if local<planned:
                continue
            base_binding={"session":session,"slot":slot,"kind":"eod" if slot=="18:00" else "normal","recipient_id":recipient_id}
            if queue.event_id(base_binding):
                continue
            source_slot="17:40" if slot=="18:00" else slot
            failure_reason="data_not_ready"
            try:
                material=read_delivery(root,session,source_slot,code_sha,config_hash)
            except (ValueError,TypeError,KeyError,OSError,RecursionError,sqlite3.Error):
                material=None
                failure_reason="bundle_unqualified"
            result=None
            if material:
                kind=base_binding["kind"]
                if kind=="normal" and local>planned+timedelta(minutes=10):
                    kind="late"
                if queue.event_id({**base_binding,"kind":kind}):
                    continue
                try:
                    result=build_digest(bundle=material[0],receipt=material[1],session=session,slot=slot,kind=kind,
                        recipient_id=recipient_id,now=now,expected_code_sha=code_sha,expected_config_hash=config_hash,
                        analyzer=analyzer,consumer=consumer)
                except (ValueError,TypeError,KeyError,RecursionError):
                    failure_reason="bundle_unqualified"
            if result is None:
                deadline=planned if slot=="18:00" else planned+timedelta(minutes=10)
                if local<deadline or queue.event_id({**base_binding,"kind":"status"}):
                    continue
                result=build_status_digest(session=session,slot=slot,recipient_id=recipient_id,now=now,reason=failure_reason)
            identifier=queue.enqueue(subject=result.subject,body=result.body,binding=result.binding,now=now)
            if dry_run:
                folder=queue.directory/"previews"
                private_directory(folder)
                write_json_atomic(folder/f"{identifier}.json",{"subject":result.subject,"body":result.body,"binding":result.binding})
            queued+=1
            notices.append({"notification_id":identifier,"slot":slot,"kind":result.binding["kind"],"ai_status":result.binding["ai_status"]})
        deliveries=[]
        if not dry_run and config is not None:
            for _ in range(4):
                item=queue.send_one(SMTPTransport(config),recipient_id=recipient_id,now=now,
                                    enabled=policy["enabled"] and policy["owner_confirmed"])
                deliveries.append(item)
                if item["state"] in {"DISABLED","IDLE","BUSY"}:
                    break
        summary={"state":"PREVIEW" if dry_run else "DISPATCHED","session":session,"queued":queued,
                 "notices":notices,"deliveries":deliveries,"smtp_enabled":policy["enabled"],
                 "at":now.astimezone(timezone.utc).isoformat()}
        write_json_atomic(queue.directory/"last_status.json",summary)
        return summary
    finally:
        lock.release()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=("configure","status","dispatch","preview","enable","disable"))
    parser.add_argument("--root",required=True)
    parser.add_argument("--code-sha")
    parser.add_argument("--config-hash")
    parser.add_argument("--enable",action="store_true")
    parser.add_argument("--overwrite",action="store_true")
    parser.add_argument("--confirm-owner-switchover",action="store_true")
    args=parser.parse_args(argv)
    try:
        if args.command=="configure":
            if not sys.stdin.isatty():
                raise ValueError("owner interactive console required for hidden credential input")
            result=configure(args.root,enabled=args.enable,owner_confirmed=args.confirm_owner_switchover,overwrite=args.overwrite)
        elif args.command=="status":
            try:
                _,policy=load_smtp_config(owned_root(args.root))
                result={"state":"CONFIGURED",**policy}
            except ValueError:
                result={"state":"CONFIG_REQUIRED"}
        elif args.command=="enable":
            result=set_smtp_enabled(owned_root(args.root),enabled=True,owner_confirmed=args.confirm_owner_switchover)
        elif args.command=="disable":
            result=set_smtp_enabled(owned_root(args.root),enabled=False,owner_confirmed=False)
        else:
            from app.core.config import Settings
            from app.services.analysis_service import AnalysisService
            from app.utils.hashing import stable_hash
            settings = Settings(_env_file=None)
            sha = args.code_sha
            if not sha:
                import subprocess
                try:
                    repo_dir = str(Path(__file__).resolve().parents[1])
                    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_dir, text=True).strip()
                except Exception as exc:
                    sha = "0" * 40
            chash = args.config_hash
            if not chash:
                try:
                    chash = stable_hash(settings.load_strategy())
                except Exception as exc:
                    chash = "0" * 64
            with AnalysisService(settings) as service:
                result=dispatch(args.root,now=datetime.now(timezone.utc),code_sha=sha,
                    config_hash=chash,dry_run=args.command=="preview",analyzer=service.analyze)
        print(json.dumps(result,ensure_ascii=False))
        return 1 if result["state"] in {"CONFIG_REQUIRED","CALENDAR_UNKNOWN"} else 0
    except Exception as exc:
        print(json.dumps({"state":"NOTIFICATION_FAILED","reason":"configuration_or_input_invalid","detail":str(exc)}))
        return 1

if __name__=="__main__":
    raise SystemExit(main())
