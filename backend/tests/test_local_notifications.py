"""Persistent notification semantics; all transports here are synthetic."""
from datetime import datetime, timedelta, timezone
import pytest

AT = datetime(2026, 10, 26, 10, tzinfo=timezone.utc)
BINDING = {"session": "2026-10-26", "slot": "14:30", "kind": "normal", "generation": 7,
           "bundle_id": "a"*64, "recipient_id": "b"*64}


def enqueue(queue, **changes):
    args = dict(subject="ETF研究摘要", body="数据为研究用途。", binding=BINDING, now=AT)
    args.update(changes)
    return queue.enqueue(**args)


def test_identical_slot_is_idempotent_and_changed_content_cannot_overwrite(tmp_path):
    from app.workspace.local_notifications import NotificationQueue
    q = NotificationQueue(tmp_path)
    first = enqueue(q)
    assert enqueue(q) == first
    with pytest.raises(ValueError, match="immutable"):
        enqueue(q, body="不同结果")
    assert len(q.summary()) == 1
    assert "body" not in q.summary()[0]


def test_disabled_transport_never_claims_or_sends(tmp_path):
    from app.workspace.local_notifications import NotificationQueue
    q = NotificationQueue(tmp_path); enqueue(q)
    def forbidden(message): pytest.fail("disabled must not send")
    assert q.send_one(forbidden, recipient_id="b"*64, now=AT, enabled=False)["state"] == "DISABLED"
    assert q.summary()[0]["state"] == "READY"


def test_smtp_acceptance_is_distinct_from_inbox_delivery_and_survives_restart(tmp_path):
    from app.workspace.local_notifications import NotificationQueue
    q = NotificationQueue(tmp_path); first = enqueue(q); seen=[]
    result=q.send_one(lambda message: seen.append(message.notification_id), recipient_id="b"*64, now=AT, enabled=True)
    assert result["state"] == "ACCEPTED" and seen == [first]
    q=NotificationQueue(tmp_path)
    assert q.send_one(lambda m: pytest.fail("must not resend"), recipient_id="b"*64, now=AT, enabled=True)["state"] == "IDLE"
    assert q.summary()[0]["state"] == "ACCEPTED"


def test_unknown_send_outcome_never_blindly_retries(tmp_path):
    from app.workspace.local_notifications import NotificationQueue
    q=NotificationQueue(tmp_path);enqueue(q)
    def broken(message): raise TimeoutError("private SMTP password should not enter logs")
    result=q.send_one(broken, recipient_id="b"*64, now=AT, enabled=True)
    assert result["state"] == "AMBIGUOUS"
    assert "private SMTP" not in str(q.summary())
    assert q.send_one(lambda m: pytest.fail("unknown outcome must not resend"), recipient_id="b"*64, now=AT+timedelta(hours=1), enabled=True)["state"] == "IDLE"


def test_definite_transient_rejection_has_bounded_backoff(tmp_path):
    from app.workspace.local_notifications import NotificationQueue, DeliveryRejected
    q=NotificationQueue(tmp_path);enqueue(q)
    def rejected(message): raise DeliveryRejected(retryable=True)
    assert q.send_one(rejected, recipient_id="b"*64, now=AT, enabled=True)["state"] == "FAILED"
    assert q.send_one(rejected, recipient_id="b"*64, now=AT, enabled=True)["state"] == "IDLE"
    q.send_one(rejected, recipient_id="b"*64, now=AT+timedelta(minutes=2), enabled=True)
    q.send_one(rejected, recipient_id="b"*64, now=AT+timedelta(minutes=6), enabled=True)
    assert q.summary()[0]["attempts"] == 3
    assert q.send_one(rejected, recipient_id="b"*64, now=AT+timedelta(hours=1), enabled=True)["state"] == "IDLE"


def test_crashed_claim_is_ambiguous_and_is_not_released_for_resend(tmp_path):
    from app.workspace.local_notifications import NotificationQueue
    q=NotificationQueue(tmp_path);enqueue(q)
    def crash(message): raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        q.send_one(crash, recipient_id="b"*64, now=AT, enabled=True)
    q=NotificationQueue(tmp_path)
    assert q.summary()[0]["state"] == "AMBIGUOUS"


def test_changed_recipient_cannot_consume_an_old_pending_message(tmp_path):
    from app.workspace.local_notifications import NotificationQueue
    q=NotificationQueue(tmp_path);enqueue(q)
    assert q.send_one(lambda m: pytest.fail("recipient binding"), recipient_id="c"*64, now=AT, enabled=True)["state"] == "IDLE"


@pytest.mark.parametrize("changes",[{"subject":"report\r\nBcc: attacker@example.invalid"},
    {"body":"password="+"x"*32},{"binding":{**BINDING,"kind":"unknown"}},
    {"binding":{**BINDING,"generation":True}},{"now":AT.replace(tzinfo=None)}])
def test_invalid_or_sensitive_content_is_rejected(tmp_path,changes):
    from app.workspace.local_notifications import NotificationQueue
    with pytest.raises(ValueError):enqueue(NotificationQueue(tmp_path),**changes)


def test_smtp_transport_requires_tls_and_uses_one_configured_recipient(monkeypatch):
    from app.workspace.local_notifications import SMTPConfig, SMTPTransport, Notification
    calls=[]
    class SMTP:
        def __init__(self,*args,**kwargs):calls.append(("connect",kwargs))
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def ehlo(self):calls.append("ehlo")
        def starttls(self,**kwargs):calls.append(("tls",kwargs));return (220,b"ok")
        def login(self,user,password):calls.append("login")
        def send_message(self,message,**kwargs):calls.append(("send",message,kwargs));return {}
    monkeypatch.setattr("smtplib.SMTP",SMTP)
    cfg=SMTPConfig(host="smtp.example.invalid",port=587,username="owner@example.invalid",
                   password="secret-not-for-logs",sender="owner@example.invalid",recipient="owner@example.invalid",mode="starttls")
    SMTPTransport(cfg)(Notification("a"*64,"ETF","研究",BINDING,AT))
    assert any(isinstance(x,tuple) and x[0]=="tls" for x in calls)
    sent=next(x for x in calls if isinstance(x,tuple) and x[0]=="send")
    assert sent[2]["to_addrs"]==["owner@example.invalid"]
    assert "secret-not-for-logs" not in repr(cfg)
    with pytest.raises(ValueError):
        SMTPConfig(host="smtp.example.invalid",port=25,username="a",password="b",sender="a",recipient="b",mode="plain")


def test_corrupt_queued_payload_is_not_sent(tmp_path):
    import sqlite3
    from app.workspace.local_notifications import NotificationQueue
    q=NotificationQueue(tmp_path);enqueue(q)
    with sqlite3.connect(q.path) as db:db.execute("UPDATE messages SET body='tampered body'")
    result=q.send_one(lambda m:pytest.fail("corrupt payload must not send"),recipient_id="b"*64,now=AT,enabled=True)
    assert result["state"]=="FAILED" and result["reason"]=="payload_integrity_failed"


def test_event_lookup_does_not_regenerate_queued_ai_text(tmp_path):
    from app.workspace.local_notifications import NotificationQueue
    q=NotificationQueue(tmp_path);first=enqueue(q)
    assert q.event_id(BINDING)==first
    assert q.event_id({**BINDING,"slot":"14:45"}) is None


def test_old_session_and_expired_packet_are_not_sent_as_a_current_notice(tmp_path):
    from app.workspace.local_notifications import NotificationQueue
    q=NotificationQueue(tmp_path)
    enqueue(q,binding={**BINDING,"expires_at":(AT+timedelta(minutes=1)).isoformat()})
    result=q.send_one(lambda m:pytest.fail("expired packet must not send"),recipient_id="b"*64,now=AT+timedelta(minutes=2),enabled=True)
    assert result["state"]=="FAILED" and result["reason"]=="notification_expired"


def test_old_status_notice_also_expires(tmp_path):
    from app.workspace.local_notifications import NotificationQueue
    q=NotificationQueue(tmp_path);enqueue(q,binding={**BINDING,"kind":"status","generation":None,"bundle_id":None})
    result=q.send_one(lambda m:pytest.fail("old status must not send"),recipient_id="b"*64,now=AT+timedelta(days=2),enabled=True)
    assert result["state"]=="FAILED" and result["reason"]=="notification_expired"


def test_actual_attempt_time_is_recorded_separately_from_body_creation(tmp_path):
    from app.workspace.local_notifications import NotificationQueue
    q=NotificationQueue(tmp_path);enqueue(q);seen=[]
    sent_at=AT+timedelta(minutes=2)
    q.send_one(lambda m:seen.append(m.created_at),recipient_id="b"*64,now=sent_at,enabled=True)
    assert seen==[sent_at]
    row=q.summary()[0]
    assert row["created_at"]==AT.isoformat()
    assert row["last_attempt_at"]==row["accepted_at"]==sent_at.isoformat()
