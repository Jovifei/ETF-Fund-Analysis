"""Bounded signed, read-only cold-history packets. Never grant market qualification.

The offline verifier has no database, network, credential discovery or replay
ledger. Re-verifying the same packet is safe; a future online queue must bind the
request to its owner and atomically record consumption before any cache write.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
import gzip
import hashlib
import hmac
import io
import json
import math
import re
import zlib
from uuid import uuid4

VERSION = 'cold-history-packet-v1'
MAX_PACKET_BYTES = 4 * 1024 * 1024
MAX_RAW_BYTES = 32 * 1024 * 1024
CODE = re.compile(r'^[0-9]{6}\.(SH|SZ|BJ)$')
HEX = re.compile(r'^[a-f0-9]{32}$')
FIELDS = frozenset({'ts_code','date','open','high','low','close','volume','amount','source','adjust'})
REQUEST_FIELDS = frozenset({'schema_version','request_id','nonce','ts_code','start','end','adjust',
                           'max_rows','created_at','expires_at'})


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_json_key')
        result[key] = value
    return result


def decode(raw):
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite_json')))
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise ValueError('invalid_archive_json') from None


def timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError('invalid_archive_timestamp')
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('archive_timezone_required')
    return result.astimezone(timezone.utc)


def day(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        raise ValueError('invalid_archive_date')
    return date.fromisoformat(value)


def validate_request(value, *, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or not isinstance(value, dict) or set(value) != REQUEST_FIELDS:
        raise ValueError('invalid_archive_request')
    if value['schema_version'] != VERSION or (not isinstance(value['ts_code'], str) or not CODE.fullmatch(value['ts_code'])):
        raise ValueError('invalid_archive_identity')
    if any(not isinstance(value[k], str) or not HEX.fullmatch(value[k]) for k in ('request_id', 'nonce')):
        raise ValueError('invalid_archive_nonce')
    if value['adjust'] not in {'none','qfq','hfq'}:
        raise ValueError('invalid_archive_price_basis')
    first, last = day(value['start']), day(value['end'])
    if not 0 <= (last-first).days <= 7305:
        raise ValueError('archive_range_exceeded')
    if type(value['max_rows']) is not int or not 1 <= value['max_rows'] <= 5000:
        raise ValueError('archive_row_limit_invalid')
    created, expires = timestamp(value['created_at']), timestamp(value['expires_at'])
    if not 0 < (expires-created).total_seconds() <= 3600 or created > now + timedelta(seconds=30) or now >= expires:
        raise ValueError('archive_request_expired_or_future')
    return value


def new_request(code, first, last, *, now=None, max_rows=5000, adjust='none'):
    now = now or datetime.now(timezone.utc)
    value = dict(schema_version=VERSION, request_id=uuid4().hex, nonce=uuid4().hex,
                 ts_code=code, start=first, end=last, adjust=adjust, max_rows=max_rows,
                 created_at=now.isoformat(), expires_at=(now+timedelta(minutes=30)).isoformat())
    return validate_request(value, now=now)


def validate_rows(request, rows):
    if not isinstance(rows, list) or len(rows) > request['max_rows']:
        raise ValueError('archive_row_limit_exceeded')
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != FIELDS:
            raise ValueError('unexpected_archive_fields')
        if row['ts_code'] != request['ts_code'] or row['adjust'] != request['adjust']:
            raise ValueError('archive_row_identity_mismatch')
        current = day(row['date'])
        if not day(request['start']) <= current <= day(request['end']) or current in seen:
            raise ValueError('archive_date_out_of_range_or_duplicate')
        seen.add(current)
        source = row['source']
        if not isinstance(source, str) or not re.fullmatch(r'[A-Za-z0-9_:.-]{1,64}', source):
            raise ValueError('archive_source_invalid')
        values = [row[k] for k in ('open','high','low','close')]
        if not all(type(v) in (int,float) and math.isfinite(v) and v > 0 for v in values):
            raise ValueError('archive_price_invalid')
        o, h, l, c = values
        if not l <= min(o,c) <= max(o,c) <= h:
            raise ValueError('archive_ohlc_invalid')
        if any(v is not None and (type(v) not in (int,float) or not math.isfinite(v) or v < 0)
               for v in (row['volume'], row['amount'])):
            raise ValueError('archive_volume_invalid')
    return sorted(rows, key=lambda row:row['date'])


def _key(key):
    if not isinstance(key, bytes) or len(key) != 32:
        raise ValueError('independent_32_byte_archive_key_required')


def pack(request, rows, key, *, now=None):
    _key(key); validate_request(request, now=now)
    rows = validate_rows(request, rows)
    manifest = {'schema_version':VERSION, 'request_hash':hashlib.sha256(canonical(request)).hexdigest(),
                'row_count':len(rows), 'rows_sha256':hashlib.sha256(canonical(rows)).hexdigest()}
    body = {'manifest':manifest,'rows':rows}
    signature = hmac.new(key, canonical(body), hashlib.sha256).hexdigest()
    raw = canonical({**body,'signature':signature})
    if len(raw) > MAX_RAW_BYTES:
        raise ValueError('archive_uncompressed_limit_exceeded')
    packet = gzip.compress(raw, compresslevel=6, mtime=0)
    if len(packet) > MAX_PACKET_BYTES:
        raise ValueError('archive_packet_limit_exceeded')
    return packet


def unpack(request, packet, key, *, now=None):
    _key(key); validate_request(request, now=now)
    if not isinstance(packet, bytes) or len(packet) > MAX_PACKET_BYTES:
        raise ValueError('archive_packet_limit_exceeded')
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(packet)) as stream:
            raw = stream.read(MAX_RAW_BYTES + 1)
        if len(raw) > MAX_RAW_BYTES:
            raise ValueError('archive_uncompressed_limit_exceeded')
        envelope = decode(raw)
    except (OSError, EOFError, zlib.error):
        raise ValueError('archive_compression_invalid') from None
    if not isinstance(envelope, dict) or set(envelope) != {'manifest','rows','signature'}:
        raise ValueError('archive_envelope_invalid')
    body = {k:envelope[k] for k in ('manifest','rows')}
    expected = hmac.new(key, canonical(body), hashlib.sha256).hexdigest()
    if (not isinstance(envelope['signature'], str) or not re.fullmatch(r'[a-f0-9]{64}', envelope['signature'])
        or not hmac.compare_digest(envelope['signature'], expected)):
        raise ValueError('archive_signature_mismatch')
    rows = validate_rows(request, envelope['rows'])
    manifest = {'schema_version':VERSION,'request_hash':hashlib.sha256(canonical(request)).hexdigest(),
                'row_count':len(rows),'rows_sha256':hashlib.sha256(canonical(rows)).hexdigest()}
    if envelope['manifest'] != manifest:
        raise ValueError('archive_manifest_mismatch')
    return {'status':'research' if rows else 'unavailable','transport':'external_archive','rows':rows,
            'request_id':request['request_id'],'input_hash':manifest['rows_sha256'],
            'coverage':{'returned_rows':len(rows),'first':rows[0]['date'] if rows else None,
                        'last':rows[-1]['date'] if rows else None,'complete':False},
            'qualification':'not_asserted','research_only':True,'actionable':False,
            'note':'Verified bytes and key possession, not market units, continuity, freshness or complete trading-session coverage.'}
