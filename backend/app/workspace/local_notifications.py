"""Small owner-local mail outbox. SMTP acceptance is not inbox delivery."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from email.message import EmailMessage
from email.utils import format_datetime
import json
from pathlib import Path
import os
import base64
import re
import smtplib
import sqlite3
import ssl

from app.workspace.local_schedule import LocalRunLock
from app.workspace.protocol import safe_text
from app.workspace.shadow_bundle import digest

HASH = re.compile(r"[0-9a-f]{64}")
KINDS = {"normal", "late", "status", "eod"}
MAX_ATTEMPTS = 3
MAX_ITEMS = 1024


def _time(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware notification time required")
    return value.astimezone(timezone.utc)


def private_directory(path: Path):
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise ValueError("owned notification path required")
    created = not path.exists()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "nt":
        from app.workspace.windows_acl import descriptor
        acl = descriptor(path, created=created, directory=True)
        allowed = {acl["current"], "S-1-5-18", "S-1-5-32-544"}
        if acl["owner"] not in allowed or not acl["protected"] or any(
            r["allow"] and r["rights"] and r["sid"] not in allowed for r in acl["rules"]):
            raise ValueError("private notification directory permissions required")
    elif path.stat().st_mode & 0o077:
        raise ValueError("private notification directory permissions required")


class DeliveryRejected(Exception):
    def __init__(self, *, retryable=False):
        super().__init__("smtp_rejected")
        self.retryable = retryable


class DeliveryUncertain(Exception):
    pass


@dataclass(frozen=True)
class Notification:
    notification_id: str
    subject: str
    body: str = field(repr=False)
    binding: dict = field(repr=False)
    created_at: datetime


@dataclass(frozen=True)
class SMTPConfig:
    host: str
    port: int
    username: str = field(repr=False)
    password: str = field(repr=False)
    sender: str = field(repr=False)
    recipient: str = field(repr=False)
    mode: str = "ssl"
    timeout_seconds: int = 30

    def __post_init__(self):
        if (not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", self.host)
                or self.mode not in {"ssl", "starttls"}
                or type(self.port) is not int or self.port not in {465, 587}
                or type(self.timeout_seconds) is not int or not 1 <= self.timeout_seconds <= 60):
            raise ValueError("explicit TLS SMTP configuration required")
        for value in (self.username, self.sender, self.recipient):
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+", value):
                raise ValueError("one valid configured mailbox required")
        if not isinstance(self.password, str) or not self.password or len(self.password) > 4096:
            raise ValueError("SMTP credential required")

    @property
    def recipient_id(self):
        return digest({"recipient": self.recipient.casefold(), "sender": self.sender.casefold()})


class SMTPTransport:
    def __init__(self, config: SMTPConfig):
        self.config = config

    def __call__(self, message: Notification):
        c = self.config
        mail = EmailMessage()
        mail["Subject"], mail["From"], mail["To"] = message.subject, c.sender, c.recipient
        mail["Message-ID"] = f"<{message.notification_id}@{c.sender.rsplit('@', 1)[1]}>"
        mail["Date"] = format_datetime(_time(message.created_at))
        mail.set_content(message.body)
        smtp, data_started = None, False
        try:
            context = ssl.create_default_context()
            if c.mode == "ssl":
                smtp = smtplib.SMTP_SSL(c.host, c.port, timeout=c.timeout_seconds, context=context)
            else:
                smtp = smtplib.SMTP(c.host, c.port, timeout=c.timeout_seconds)
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
            smtp.login(c.username, c.password)
            data_started = True
            refused = smtp.send_message(mail, from_addr=c.sender, to_addrs=[c.recipient])
            if refused:
                raise DeliveryRejected()
        except DeliveryRejected:
            raise
        except smtplib.SMTPRecipientsRefused as exc:
            raise DeliveryRejected(retryable=all(400 <= v[0] < 500 for v in exc.recipients.values())) from None
        except smtplib.SMTPResponseException as exc:
            raise DeliveryRejected(retryable=400 <= exc.smtp_code < 500) from None
        except Exception:
            if data_started:
                raise DeliveryUncertain("smtp_outcome_unknown") from None
            raise DeliveryRejected(retryable=True) from None
        finally:
            if smtp is not None:
                try:
                    smtp.close()
                except Exception:
                    pass


class NotificationQueue:
    def __init__(self, root: Path):
        self.directory = Path(root) / "state" / "notifications"
        private_directory(self.directory)
        self.path = self.directory / "outbox.sqlite3"
        if self.path.is_symlink() or (hasattr(self.path, "is_junction") and self.path.is_junction()):
            raise ValueError("owned notification database required")
        self.lock_path = self.directory / ".send.lock"
        with self._transaction() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY, event_key TEXT UNIQUE NOT NULL, payload_hash TEXT NOT NULL,
                subject TEXT NOT NULL, body TEXT NOT NULL, binding TEXT NOT NULL,
                state TEXT NOT NULL, created_at TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                retry_at TEXT, retryable INTEGER NOT NULL DEFAULT 0, reason TEXT)""")
            columns={r[1] for r in db.execute("PRAGMA table_info(messages)")}
            for name in ("last_attempt_at","accepted_at"):
                if name not in columns:
                    db.execute(f"ALTER TABLE messages ADD COLUMN {name} TEXT")
        lock = LocalRunLock(self.lock_path)
        if lock.acquire():
            try:
                with self._transaction() as db:
                    db.execute("UPDATE messages SET state='AMBIGUOUS',reason='interrupted_send',retryable=0 WHERE state='SENDING'")
            finally:
                lock.release()

    @contextmanager
    def _transaction(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def enqueue(self, *, subject, body, binding, now):
        now = _time(now)
        keys = {"session", "slot", "kind", "generation", "bundle_id", "recipient_id"}
        optional = {"ai_input_hash", "ai_result_hash", "ai_status", "consumer_state", "data_as_of", "expires_at",
                    "ai_model", "ai_provider", "ai_prompt_version", "ai_schema_version"}
        if not isinstance(binding, dict) or not keys <= set(binding) or set(binding)-keys-optional:
            raise ValueError("exact notification binding required")
        session=date.fromisoformat(binding["session"])
        if session>now.astimezone(ZoneInfo("Asia/Shanghai")).date():
            raise ValueError("notification session is in the future")
        if binding.get("expires_at") is not None:
            expiry=datetime.fromisoformat(binding["expires_at"])
            if _time(expiry)<=now:
                raise ValueError("notification material already expired")
        if (not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", binding["slot"])
                or binding["kind"] not in KINDS or not HASH.fullmatch(str(binding["recipient_id"]))):
            raise ValueError("valid notification identity required")
        if binding["kind"] != "status" or binding["generation"] is not None:
            if type(binding["generation"]) is not int or binding["generation"] <= 0 or not HASH.fullmatch(str(binding["bundle_id"])):
                raise ValueError("approved generation binding required")
        if (not isinstance(subject, str) or not 1 <= len(subject) <= 200 or any(x in subject for x in "\r\n")
                or not isinstance(body, str) or not 1 <= len(body) <= 64000):
            raise ValueError("bounded safe mail content required")
        safe_text(subject); safe_text(body)
        event_key = digest({k:binding[k] for k in ("session", "slot", "kind", "recipient_id")})
        payload_hash = digest({"subject":subject,"body":body,"binding":binding})
        with self._transaction() as db:
            old = db.execute("SELECT id,payload_hash FROM messages WHERE event_key=?", (event_key,)).fetchone()
            if old:
                if old["payload_hash"] != payload_hash:
                    raise ValueError("immutable notification already queued")
                return old["id"]
            if db.execute("SELECT COUNT(*) FROM messages").fetchone()[0] >= MAX_ITEMS:
                # Auto-prune terminal messages older than 30 days
                cutoff = (now - timedelta(days=30)).isoformat()
                db.execute("DELETE FROM messages WHERE (state='ACCEPTED' OR (state='FAILED' AND retryable=0) OR state='AMBIGUOUS') AND created_at < ?", (cutoff,))
                if db.execute("SELECT COUNT(*) FROM messages").fetchone()[0] >= MAX_ITEMS:
                    # Still full? Prune oldest ACCEPTED messages to free up capacity
                    db.execute("DELETE FROM messages WHERE id IN (SELECT id FROM messages WHERE state='ACCEPTED' ORDER BY created_at ASC LIMIT 100)")
                if db.execute("SELECT COUNT(*) FROM messages").fetchone()[0] >= MAX_ITEMS:
                    raise ValueError("notification capacity reached")
            db.execute("INSERT INTO messages(id,event_key,payload_hash,subject,body,binding,state,created_at) VALUES (?,?,?,?,?,?,'READY',?)",
                       (event_key,event_key,payload_hash,subject,body,json.dumps(binding,sort_keys=True),now.isoformat()))
        return event_key

    def event_id(self, binding):
        event_key = digest({k:binding[k] for k in ("session", "slot", "kind", "recipient_id")})
        with self._transaction() as db:
            row=db.execute("SELECT id FROM messages WHERE event_key=?",(event_key,)).fetchone()
            return row["id"] if row else None

    def send_one(self, transport, *, recipient_id, now, enabled=False):
        now = _time(now)
        if enabled is not True:
            return {"state":"DISABLED"}
        lock = LocalRunLock(self.lock_path)
        if not lock.acquire():
            return {"state":"BUSY"}
        try:
            with self._transaction() as db:
                rows = db.execute("SELECT * FROM messages WHERE attempts<? AND (state='READY' OR (state='FAILED' AND retryable=1 AND retry_at<=?)) ORDER BY created_at,id", (MAX_ATTEMPTS,now.isoformat())).fetchall()
                row = next((r for r in rows if json.loads(r["binding"])["recipient_id"] == recipient_id), None)
                if row is None:
                    return {"state":"IDLE"}
                binding=json.loads(row["binding"])
                expired=(binding["session"]<now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
                    or binding.get("expires_at") is not None and now>=_time(datetime.fromisoformat(binding["expires_at"])))
                if expired:
                    db.execute("UPDATE messages SET state='FAILED',retryable=0,reason='notification_expired' WHERE id=?",(row["id"],))
                    return {"state":"FAILED","notification_id":row["id"],"reason":"notification_expired"}
                actual=digest({"subject":row["subject"],"body":row["body"],"binding":binding})
                if actual!=row["payload_hash"]:
                    db.execute("UPDATE messages SET state='FAILED',retryable=0,reason='payload_integrity_failed' WHERE id=?",(row["id"],))
                    return {"state":"FAILED","notification_id":row["id"],"reason":"payload_integrity_failed"}
                db.execute("UPDATE messages SET state='SENDING',attempts=attempts+1,reason=NULL,last_attempt_at=? WHERE id=?", (now.isoformat(),row["id"]))
            message = Notification(row["id"],row["subject"],row["body"],json.loads(row["binding"]),now)
            state, retryable, reason = "ACCEPTED", False, None
            try:
                transport(message)
            except DeliveryRejected as exc:
                state,retryable,reason = "FAILED",exc.retryable,"smtp_rejected"
            except Exception:
                state,reason = "AMBIGUOUS","smtp_outcome_unknown"
            with self._transaction() as db:
                db.execute("UPDATE messages SET state=?,retryable=?,reason=?,retry_at=?,accepted_at=? WHERE id=?",
                    (state,int(retryable),reason,(now+timedelta(seconds=60*(row["attempts"]+1))).isoformat(),
                     now.isoformat() if state=="ACCEPTED" else None,row["id"]))
            return {"state":state,"notification_id":row["id"],"reason":reason}
        finally:
            lock.release()

    def summary(self):
        with self._transaction() as db:
            return [dict(r) for r in db.execute("SELECT id AS notification_id,state,created_at,last_attempt_at,accepted_at,attempts,retry_at,reason FROM messages ORDER BY created_at,id")]


def _config_path(root):
    root=Path(root).absolute()
    # Private runtime routing/credentials must never be placed in a Git checkout.
    if any((p/".git").exists() for p in (root,*root.parents)):
        raise ValueError("SMTP configuration must be outside the repository")
    folder=root/"config"/"notifications"
    private_directory(folder)
    path=folder/"smtp.json"
    if path.is_symlink() or (hasattr(path,"is_junction") and path.is_junction()):
        raise ValueError("owned SMTP config required")
    return path


def save_smtp_config(root, config: SMTPConfig, *, enabled=False, owner_confirmed=False, overwrite=False):
    if type(enabled) is not bool or type(owner_confirmed) is not bool or enabled and not owner_confirmed:
        raise ValueError("explicit single-owner activation required")
    if os.name!="nt":
        raise ValueError("CurrentUser DPAPI SMTP setup requires Windows")
    from app.workspace.ai_secrets import _dpapi
    from app.workspace.windows_acl import descriptor
    path=_config_path(root)
    if path.exists() and not overwrite:
        raise ValueError("SMTP configuration already exists; preserve it")
    value={"version":"etf-smtp-dpapi-v1","host":config.host,"port":config.port,
           "username":config.username,"sender":config.sender,"recipient":config.recipient,"mode":config.mode,
           "password_dpapi":base64.b64encode(_dpapi(config.password.encode())).decode(),
           "enabled":enabled,"owner_confirmed":owner_confirmed}
    if path.exists():
        path.unlink()
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,"w",encoding="utf-8") as handle:
        descriptor(path,created=True,directory=False)
        json.dump(value,handle,ensure_ascii=False)
        handle.flush();os.fsync(handle.fileno())
    return path


def set_smtp_enabled(root, *, enabled: bool, owner_confirmed: bool):
    """Update enabled flag of an existing SMTP config without re-entering password."""
    if type(enabled) is not bool or type(owner_confirmed) is not bool or (enabled and not owner_confirmed):
        raise ValueError("explicit single-owner activation required")
    path = _config_path(root)
    if not path.is_file():
        raise ValueError("SMTP configuration not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["enabled"] = enabled
    data["owner_confirmed"] = owner_confirmed
    from app.workspace.windows_acl import descriptor
    temp_path = path.with_suffix(".tmp")
    if temp_path.exists():
        temp_path.unlink()
    fd = os.open(temp_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        descriptor(temp_path, created=True, directory=False)
        json.dump(data, handle, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)
    return {"state": "UPDATED", "enabled": enabled, "owner_confirmed": owner_confirmed, "config_file": str(path)}


def load_smtp_config(root):
    path=_config_path(root)
    if os.name!="nt" or not path.is_file() or path.stat().st_size>16384:
        raise ValueError("private SMTP configuration unavailable")
    from app.workspace.windows_acl import descriptor
    from app.workspace.ai_secrets import _dpapi
    acl=descriptor(path,created=False,directory=False)
    allowed={acl["current"],"S-1-5-18","S-1-5-32-544"}
    if acl["owner"] not in allowed or not acl["protected"] or any(
        r["allow"] and r["rights"] and r["sid"] not in allowed for r in acl["rules"]):
        raise ValueError("private SMTP file permissions required")
    try:
        from app.workspace.shadow_client import _unique_object
        value=json.loads(path.read_text(encoding="utf-8"),object_pairs_hook=_unique_object)
        if (set(value)!={"version","host","port","username","sender","recipient","mode","password_dpapi","enabled","owner_confirmed"}
                or value["version"]!="etf-smtp-dpapi-v1"
                or type(value["enabled"]) is not bool or type(value["owner_confirmed"]) is not bool
                or value["enabled"] and not value["owner_confirmed"]):
            raise ValueError()
        config=SMTPConfig(host=value["host"],port=value["port"],username=value["username"],
            password=_dpapi(base64.b64decode(value["password_dpapi"],validate=True),decrypt=True).decode(),
            sender=value["sender"],recipient=value["recipient"],mode=value["mode"])
        return config,{"enabled":value["enabled"],"owner_confirmed":value["owner_confirmed"]}
    except Exception:
        raise ValueError("SMTP configuration invalid or unavailable for this Windows user") from None
