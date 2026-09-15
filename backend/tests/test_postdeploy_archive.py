"""Cold archives are untrusted research packets, not a live database sync."""
from datetime import datetime, timedelta, timezone
import copy
import gzip
import json

import pytest

NOW = datetime(2026, 9, 15, 2, 0, tzinfo=timezone.utc)
KEY = bytes(range(32))  # disposable fixture, never a deployed secret


def request():
    from app.workspace.archive_protocol import new_request
    return new_request('510300.SH', '2026-09-10', '2026-09-14', now=NOW)


def rows():
    return [dict(ts_code='510300.SH', date=day, open=1.0, high=1.2, low=.9, close=1.1,
                 volume=None, amount=None, source='akshare:sina:v101', adjust='none')
            for day in ('2026-09-10', '2026-09-11', '2026-09-14')]


def test_packet_roundtrip_preserves_unknown_units_not_promoted():
    from app.workspace.archive_protocol import pack, unpack
    req = request(); packet = pack(req, rows(), KEY, now=NOW)
    result = unpack(req, packet, KEY, now=NOW)
    assert result['rows'][0]['volume'] is None
    assert result['rows'][0]['source'] == 'akshare:sina:v101'
    assert result['transport'] == 'external_archive' and result['actionable'] is False
    assert result['qualification'] == 'not_asserted'
    assert result['coverage']['returned_rows'] == 3


def test_tampered_body_and_wrong_request_are_rejected():
    from app.workspace.archive_protocol import pack, unpack
    req = request(); packet = pack(req, rows(), KEY, now=NOW)
    other = request()
    with pytest.raises(ValueError): unpack(other, packet, KEY, now=NOW)
    changed = bytearray(packet); changed[-10] ^= 1
    with pytest.raises(ValueError): unpack(req, bytes(changed), KEY, now=NOW)
    with pytest.raises(ValueError): unpack(req, packet, b'x' * 32, now=NOW)


def test_expired_request_and_oversized_packets_fail_closed():
    from app.workspace.archive_protocol import pack, unpack, MAX_PACKET_BYTES
    req = request(); packet = pack(req, rows(), KEY, now=NOW)
    with pytest.raises(ValueError): unpack(req, packet, KEY, now=NOW + timedelta(hours=2))
    with pytest.raises(ValueError): unpack(req, b'x' * (MAX_PACKET_BYTES + 1), KEY, now=NOW)


@pytest.mark.parametrize('field,value', [('ts_code','512480.SH'), ('date','2026-09-15'),
    ('close',False), ('high',float('nan')), ('adjust','guessed'), ('volume',-1)])
def test_invalid_rows_rejected(field, value):
    from app.workspace.archive_protocol import pack
    values = rows(); values[0][field] = value
    with pytest.raises(ValueError): pack(request(), values, KEY, now=NOW)


def test_private_fields_and_duplicate_dates_rejected():
    from app.workspace.archive_protocol import pack
    values = rows(); values[0]['account'] = 'not-allowed'
    with pytest.raises(ValueError): pack(request(), values, KEY, now=NOW)
    values = rows(); values.append(values[0].copy())
    with pytest.raises(ValueError): pack(request(), values, KEY, now=NOW)


def test_empty_response_is_explicit_not_a_complete_history():
    from app.workspace.archive_protocol import pack, unpack
    req = request(); result = unpack(req, pack(req, [], KEY, now=NOW), KEY, now=NOW)
    assert result['status'] == 'unavailable' and not result['coverage']['complete']


def test_local_export_verifies_manifest_before_selection(tmp_path):
    from app.workspace.archive_store import read_export
    root = tmp_path / 'private'; root.mkdir(mode=0o700)
    archive = root / 'pack'; archive.mkdir(mode=0o700)
    raw = b''.join((json.dumps({'kind':'etf_bar', **row, 'actionable':False})+'\n').encode() for row in rows())
    path = archive / 'market-history.jsonl.gz'; path.write_bytes(gzip.compress(raw)); path.chmod(0o600)
    import hashlib
    manifest = {'schema_version':'market-history-archive-v1','file':path.name,
                'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    meta = archive / 'manifest.json'; meta.write_text(json.dumps(manifest)); meta.chmod(0o600)
    assert len(read_export(root, 'pack', request(), now=NOW)) == 3
    path.write_bytes(gzip.compress(b'bad'))
    with pytest.raises(ValueError): read_export(root, 'pack', request(), now=NOW)
    with pytest.raises(ValueError): read_export(root, '../pack', request(), now=NOW)


def test_symlink_archive_root_rejected(tmp_path):
    from app.workspace.archive_store import private_path
    root = tmp_path / 'private'; root.mkdir(mode=0o700)
    link = tmp_path / 'link'
    try: link.symlink_to(root, target_is_directory=True)
    except OSError: pytest.skip('symlink creation unavailable')
    with pytest.raises(ValueError): private_path(link, directory=True)


def test_optional_parquet_roundtrip_and_filters(tmp_path):
    pytest.importorskip('duckdb')
    from app.workspace.archive_parquet import write, read
    root = tmp_path / 'private'; root.mkdir(mode=0o700)
    req = request(); write(root, 'parquet-one', req, rows(), now=NOW)
    selected = {**req,'start':'2026-09-11'}
    result = read(root, 'parquet-one', selected, now=NOW)
    assert [row['date'] for row in result] == ['2026-09-11','2026-09-14']
    assert result[0]['amount'] is None
    with pytest.raises(FileExistsError): write(root, 'parquet-one', req, rows(), now=NOW)


def test_expansion_bomb_and_duplicate_json_keys():
    from app.workspace.archive_protocol import unpack, MAX_RAW_BYTES, decode
    with pytest.raises(ValueError): unpack(request(), gzip.compress(b' '*(MAX_RAW_BYTES+1)), KEY, now=NOW)
    with pytest.raises(ValueError): decode(b'{"request_id":1,"request_id":2}')
    with pytest.raises(ValueError): decode(b'{"value":NaN}')


def test_non_ascii_signature_is_rejected_as_a_protocol_error():
    from app.workspace.archive_protocol import pack, unpack
    req = request()
    envelope = json.loads(gzip.decompress(pack(req, rows(), KEY, now=NOW)))
    envelope['signature'] = '坏' * 64
    with pytest.raises(ValueError, match='archive_signature_mismatch'):
        unpack(req, gzip.compress(json.dumps(envelope).encode()), KEY, now=NOW)


@pytest.mark.parametrize('field,value', [('nonce', 12345678901234567890123456789012), ('request_id', 12345678901234567890123456789012)])
def test_request_ids_must_be_strings(field, value):
    from app.workspace.archive_protocol import validate_request
    req = request(); req[field] = value
    with pytest.raises(ValueError, match='invalid_archive_nonce'):
        validate_request(req, now=NOW)
