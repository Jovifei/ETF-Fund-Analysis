from app.workspace.local_execution import execution_identity


def identity(db, raw=b'{"universe":["510300.SH"]}', **changes):
    values = dict(database=db, profile='live', provider='public_composite', private_research=True,
                  closed_session_research=True, sync_url='https://etf.joviluma.com/api/shadow/sync')
    values.update(changes)
    return execution_identity(raw, **values)


def test_runtime_permissions_flags_and_database_identity_are_bound(tmp_path):
    db = tmp_path / 'research.sqlite3'
    db.touch()
    baseline = identity(db)
    assert identity(db) == baseline
    assert identity(db, b'{"provider_admission":{"status":"REVOKED"}}') != baseline
    assert identity(db, private_research=False) != baseline
    assert identity(db, closed_session_research=False) != baseline
    assert identity(db, provider='akshare') != baseline
    replacement = tmp_path / 'other.sqlite3'
    replacement.touch()
    assert identity(replacement) != baseline
    assert 'path' not in str(baseline) and str(tmp_path) not in str(baseline)
