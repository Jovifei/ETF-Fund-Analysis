"""Synthetic compatibility/security regressions; no external services or live data."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import gzip
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.workspace.local_display_contract import verify_bundle_integrity
from app.workspace.local_display_read import LocalDisplayStore, LocalDisplayReader
from app.workspace.shadow_bundle import canonical, digest
from app.workspace.shadow_client import upload_bundle
from test_shadow_bundle import NOW, bundle


@pytest.fixture(autouse=True)
def publish_at_fixture_time(monkeypatch):
    """Historical safety fixtures are admitted at their explicit receiver cutoff."""
    native = LocalDisplayStore.publish
    monkeypatch.setattr(LocalDisplayStore, "publish", lambda self, value, *, now=None:
                        native(self, value, now=NOW if now is None else now))

def v2(sequence=1):
    bar={"date":"2026-10-11","open":1.0,"high":1.1,"low":0.9,"close":1.0,"indicators":{}}
    parts={"overview":{"rows":[{"ts_code":"510300.SH","actionable":False}]},
           "details":{"510300.SH":{"instrument":{"ts_code":"510300.SH"},"actionable":False}},
           "charts":{"510300.SH":{"ts_code":"510300.SH","as_of":NOW.isoformat(),"source_as_of":"2026-10-11",
                                 "bars":[bar],"research_bars":[deepcopy(bar)],"actionable":False}},
           "sectors":{"sectors":[]}}
    return {"manifest":{"contract_version":"local-display-v2","code_sha":"a"*40,"config_hash":"b"*64,
                        "sequence":sequence,"generated_at":NOW.isoformat(),
                        "expires_at":(NOW+timedelta(hours=1)).isoformat(),"actionable":False,
                        "data_origin":"local_research","universe":["510300.SH"],
                        "parts_hashes":{k:digest(v) for k,v in parts.items()}},"parts":parts}

def rehash(value):
    value["manifest"]["parts_hashes"]={k:digest(v) for k,v in value["parts"].items()}

class Response:
    def __init__(self, value, status=200):
        self.status=status
        self.body=canonical(value)
    def __enter__(self): return self
    def __exit__(self,*args): return None
    def read(self,size): return self.body[:size]

def receipt(value):
    identity=digest(value["manifest"])
    if value["manifest"].get("contract")=="shadow-display-v1":
        return {"bundle_id":identity}
    return {"bundle_id":identity,"manifest_hash":identity,"sequence":value["manifest"]["sequence"],
            "status":"accepted","received_at":NOW.isoformat()}

def configure_sender(monkeypatch):
    monkeypatch.setenv("SHADOW_PRODUCER_TOKEN","x"*32)
    monkeypatch.setenv("SHADOW_SIGNING_KEY_ID","synthetic")
    monkeypatch.setenv("SHADOW_SIGNING_SECRET","s"*32)

@pytest.mark.parametrize("version",["v1","v2"])
@pytest.mark.parametrize("compress",[False,True])
def test_valid_receipt_and_compression_matrix(monkeypatch,version,compress):
    configure_sender(monkeypatch)
    value=bundle() if version=="v1" else v2()
    expected=receipt(value)
    def transport(request,**kwargs):
        raw=gzip.decompress(request.data) if compress else request.data
        assert raw==canonical(value)
        assert (request.get_header("Content-encoding")=="gzip")==compress
        return Response(expected)
    assert upload_bundle("https://receiver.example/api/shadow/sync",value,opener=transport,compress=compress)==expected

@pytest.mark.parametrize("version",["v1","v2"])
@pytest.mark.parametrize("compress",[False,True])
@pytest.mark.parametrize("mutation",["http-status","wrong-id","missing-id","extra-field","wrong-type"])
def test_bad_receipt_matrix(monkeypatch,version,compress,mutation):
    configure_sender(monkeypatch)
    value=bundle() if version=="v1" else v2()
    result=receipt(value);status=200
    if mutation=="http-status":status=201
    elif mutation=="wrong-id":result["bundle_id"]="0"*64
    elif mutation=="missing-id":result.pop("bundle_id")
    elif mutation=="extra-field":result["unexpected"]="synthetic"
    elif mutation=="wrong-type":result["bundle_id"]={"unexpected":1}
    with pytest.raises(ValueError):
        upload_bundle("https://receiver.example/api/shadow/sync",value,
                      opener=lambda *args,**kwargs:Response(result,status),compress=compress)

@pytest.mark.parametrize("mutation",["manifest-hash","sequence","sequence-bool","status","timestamp"])
def test_bad_v2_receipt_fields(monkeypatch,mutation):
    configure_sender(monkeypatch);value=v2();result=receipt(value)
    if mutation=="manifest-hash":result["manifest_hash"]="0"*64
    elif mutation=="sequence":result["sequence"]=2
    elif mutation=="sequence-bool":result["sequence"]=True
    elif mutation=="status":result["status"]="failed"
    elif mutation=="timestamp":result["received_at"]="invalid"
    with pytest.raises(ValueError):
        upload_bundle("https://receiver.example/api/shadow/sync",value,opener=lambda *args,**kwargs:Response(result))

@pytest.mark.parametrize("mutation",["code","bad-as-of","future-as-of","bad-date","future-date","duplicate-date",
                                     "source-date","close-object","open-bool","study-object","level-bool"])
def test_v2_chart_rules_survive_recomputed_hashes(mutation):
    value=v2();chart=value["parts"]["charts"]["510300.SH"]
    if mutation=="code":chart["ts_code"]="510301.SH"
    elif mutation=="bad-as-of":chart["as_of"]="invalid"
    elif mutation=="future-as-of":chart["as_of"]=(NOW+timedelta(minutes=1)).isoformat()
    elif mutation=="source-date":chart["source_as_of"]="2026-10-10"
    elif mutation=="study-object":chart["studies"]={"current_price":{"unexpected":1}}
    elif mutation=="level-bool":chart["studies"]={"levels":[{"price":True}]}
    else:
        for series in ("bars","research_bars"):
            if mutation=="bad-date":chart[series][0]["date"]="invalid"
            elif mutation=="future-date":chart[series][0]["date"]="2026-10-12"
            elif mutation=="duplicate-date":chart[series].append(deepcopy(chart[series][0]))
            elif mutation=="close-object":chart[series][0]["close"]={"unexpected":1}
            elif mutation=="open-bool":chart[series][0]["open"]=True
    rehash(value)
    assert verify_bundle_integrity(value) is False

@pytest.mark.parametrize("mutation",["manifest","parts","rehashed-actionable"])
def test_cached_bundle_must_be_revalidated(tmp_path,mutation):
    store=LocalDisplayStore(tmp_path);value=v2();store.publish(value,now=NOW)
    path=next(tmp_path.glob("bundle_*.json"))
    altered=json.loads(path.read_text(encoding="utf-8"))
    if mutation=="manifest":altered["manifest"]["code_sha"]="c"*40
    else:altered["parts"]["details"]["510300.SH"]["actionable"]=True
    if mutation=="rehashed-actionable":
        rehash(altered);identity=digest(altered["manifest"])
        path.unlink();path=tmp_path/f"bundle_1_{identity[:16]}.json"
        pointer={"bundle_file":path.name,"bundle_id":identity,"sequence":1,
                 "generated_at":altered["manifest"]["generated_at"],"expires_at":altered["manifest"]["expires_at"]}
        (tmp_path/"latest.json").write_text(json.dumps(pointer),encoding="utf-8")
    path.write_text(json.dumps(altered),encoding="utf-8")
    assert store.load_bundle() is None
    assert LocalDisplayReader(store).read_instrument_detail("510300.SH") is None

def test_full_id_cannot_match_only_prefix(tmp_path):
    store=LocalDisplayStore(tmp_path);result=store.publish(v2(),now=NOW)
    wrong=result["bundle_id"][:16]+("0"*48 if result["bundle_id"][16:]!="0"*48 else "1"*48)
    assert store.load_bundle(wrong) is None
    assert store.load_bundle(result["bundle_id"]) is not None

def test_numeric_full_hash_is_not_a_sequence(tmp_path,monkeypatch):
    import app.workspace.local_display_read as module
    original=module.digest
    monkeypatch.setattr(module,"digest",lambda value:"1"*64 if isinstance(value,dict) and "contract_version" in value else original(value))
    store=LocalDisplayStore(tmp_path);store.publish(v2(),now=NOW)
    assert store.load_bundle("1"*64)["manifest"]["sequence"]==1

def test_numeric_short_alias_rejects_sequence_hash_ambiguity(tmp_path,monkeypatch):
    import app.workspace.local_display_read as module
    original=module.digest;prefix="1"*16
    def identities(value):
        if isinstance(value,dict) and "contract_version" in value:
            return prefix+"a"*48 if value["sequence"]==1 else "b"*64
        return original(value)
    monkeypatch.setattr(module,"digest",identities)
    store=LocalDisplayStore(tmp_path);store.publish(v2(1),now=NOW);store.publish(v2(int(prefix)),now=NOW)
    assert store.load_bundle(prefix) is None
    assert store.load_bundle(int(prefix))["manifest"]["sequence"]==int(prefix)

def test_short_alias_rejects_ambiguity(tmp_path,monkeypatch):
    import app.workspace.local_display_read as module
    original=module.digest
    def collision(value):
        if isinstance(value,dict) and "contract_version" in value:
            return "a"*16+str(value["sequence"])*48
        return original(value)
    monkeypatch.setattr(module,"digest",collision)
    store=LocalDisplayStore(tmp_path)
    first=store.publish(v2(1),now=NOW);second=store.publish(v2(2),now=NOW)
    assert store.load_bundle("a"*16) is None
    assert store.load_bundle(first["bundle_id"])["manifest"]["sequence"]==1
    assert store.load_bundle(second["bundle_id"])["manifest"]["sequence"]==2

def snapshot(root):
    return {p.name:p.read_bytes() for p in root.iterdir() if p.is_file()}

def test_budget_rejection_preserves_every_original_file(tmp_path):
    store=LocalDisplayStore(tmp_path);store.publish(v2(1),now=NOW);store.publish(v2(2),now=NOW)
    before=snapshot(tmp_path);usage=sum(p.stat().st_size for p in tmp_path.glob("bundle_*.json"))
    store.max_bytes=usage
    value=v2(3);value["parts"]["overview"]["description"]="x"*4096;rehash(value)
    with pytest.raises(ValueError,match="capacity|budget"):
        store.publish(value,now=NOW)
    assert snapshot(tmp_path)==before

def receiver_settings(tmp_path):
    return SimpleNamespace(shadow_sync_enabled=True,shadow_sync_root=str(tmp_path/"v1"),
        shadow_sync_code_sha="a"*40,shadow_sync_config_hash="b"*64,shadow_sync_producer_token=SecretStr("x"*32),
        shadow_sync_active_key_id="synthetic",shadow_sync_signing_secret=SecretStr("s"*32),
        shadow_sync_max_bytes=33554432,shadow_sync_max_generations=20,shadow_sync_max_request_bytes=65536,
        local_display_v2_store_root=str(tmp_path/"v2"),local_display_v2_max_bytes=50_000_000,
        local_display_v2_max_decompressed_bytes=65536)

@pytest.mark.parametrize("value",[[],{"manifest":None},{"manifest":[]}])
def test_invalid_envelope_is_rejected(tmp_path,monkeypatch,value):
    from app.workspace import shadow_api
    from app.workspace.shadow_auth import signed_headers
    monkeypatch.setattr(shadow_api,"get_settings",lambda:receiver_settings(tmp_path))
    body=canonical(value)
    headers={**signed_headers(body,"synthetic","s"*32),"Authorization":"Bearer "+"x"*32}
    app=FastAPI();app.include_router(shadow_api.router)
    assert TestClient(app,raise_server_exceptions=False).post("/api/shadow/sync",content=body,headers=headers).status_code==409

@pytest.mark.parametrize("version",["v1","v2"])
@pytest.mark.parametrize("compress",[False,True])
def test_real_route_delivery_matrix(tmp_path,monkeypatch,version,compress):
    from app.workspace import shadow_api
    from app.workspace.shadow_bundle import ShadowStore
    configure_sender(monkeypatch)
    settings=receiver_settings(tmp_path)
    monkeypatch.setattr(shadow_api,"get_settings",lambda:settings)
    original=ShadowStore.publish
    monkeypatch.setattr(ShadowStore,"publish",lambda self,value:original(self,value,now=NOW))
    app=FastAPI();app.include_router(shadow_api.router);client=TestClient(app)
    def transport(request,**kwargs):
        result=client.post("/api/shadow/sync",content=request.data,headers=dict(request.header_items()))
        return Response(result.json(),status=result.status_code)
    value=bundle() if version=="v1" else v2()
    result=upload_bundle("https://receiver.example/api/shadow/sync",value,opener=transport,compress=compress)
    assert result["bundle_id"]==digest(value["manifest"])
    if version=="v2":
        again=upload_bundle("https://receiver.example/api/shadow/sync",value,opener=transport,compress=compress)
        assert again["status"]=="already_accepted" and again["bundle_id"]==result["bundle_id"]

def test_gzip_limit_rejection_preserves_generation_files(tmp_path,monkeypatch):
    from app.workspace import shadow_api
    from app.workspace.shadow_auth import signed_headers
    store=LocalDisplayStore(tmp_path/"v2");store.publish(v2(1),now=NOW);store.publish(v2(2),now=NOW)
    before=snapshot(tmp_path/"v2")
    settings=receiver_settings(tmp_path);settings.local_display_v2_max_decompressed_bytes=10
    monkeypatch.setattr(shadow_api,"get_settings",lambda:settings)
    body=gzip.compress(canonical(v2(3)))
    headers={**signed_headers(body,"synthetic","s"*32),"Authorization":"Bearer "+"x"*32,"Content-Encoding":"gzip"}
    app=FastAPI();app.include_router(shadow_api.router)
    assert TestClient(app).post("/api/shadow/sync",content=body,headers=headers).status_code==413
    assert snapshot(tmp_path/"v2")==before
    assert store.load_bundle()["manifest"]["sequence"]==2

def test_full_current_previous_budget_rejects_peak_without_deleting_rollback(tmp_path):
    store=LocalDisplayStore(tmp_path);store.publish(v2(1),now=NOW);store.publish(v2(2),now=NOW)
    store.max_bytes=sum(p.stat().st_size for p in tmp_path.glob("bundle_*.json"))
    before=snapshot(tmp_path)
    with pytest.raises(ValueError,match="capacity"):
        store.publish(v2(3),now=NOW)
    assert snapshot(tmp_path)==before
    assert store.load_bundle()["manifest"]["sequence"]==2
    assert json.loads((tmp_path/"previous.json").read_text())["sequence"]==1

def test_concurrent_same_bundle_is_idempotent(tmp_path):
    value=v2()
    def publish(_):return LocalDisplayStore(tmp_path).publish(value,now=NOW)
    with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(publish,range(6)))
    assert sum(r["status"]=="accepted" for r in results)==1
    assert sum(r["status"]=="already_accepted" for r in results)==5
    assert len({r["bundle_id"] for r in results})==1
    assert len(list(tmp_path.glob("bundle_*.json")))==1

def test_receipt_sequence_does_not_equate_manifest_bool_to_integer(monkeypatch):
    configure_sender(monkeypatch);value=v2();value["manifest"]["sequence"]=True
    result=receipt(value);result["sequence"]=1
    with pytest.raises(ValueError):
        upload_bundle("https://receiver.example/api/shadow/sync",value,opener=lambda *args,**kwargs:Response(result))

def test_numeric_overflow_is_a_validation_error():
    from app.workspace.shadow_projection import numeric
    with pytest.raises(ValueError):
        numeric(10**1000)

@pytest.mark.parametrize("section",["manifest","envelope"])
def test_safety_scan_covers_entire_envelope(section):
    value=v2()
    if section=="manifest":value["manifest"]["password"]="synthetic"
    else:value["unexpected"]={"actionable":True}
    assert verify_bundle_integrity(value) is False

def test_pruning_never_deletes_unknown_user_files(tmp_path):
    import os
    # Cap generations at 5 so reclaim runs; unknown notes must still survive.
    store=LocalDisplayStore(tmp_path, max_generations=5)
    for sequence in range(1,6):store.publish(v2(sequence),now=NOW)
    note=tmp_path/"bundle_notes.json";note.write_text("synthetic retained note",encoding="utf-8")
    os.utime(note,(1,1))
    store.publish(v2(6),now=NOW)
    assert note.read_text(encoding="utf-8")=="synthetic retained note"
    assert len([p for p in tmp_path.glob("bundle_*.json") if store.FILE_RE.fullmatch(p.name)])<=5

@pytest.mark.parametrize("field",["code_sha","config_hash"])
def test_manifest_hex_fields_use_entire_string(field):
    from app.workspace.local_display_contract import validate_bundle_manifest
    value=v2();value["manifest"][field]+="\n"
    with pytest.raises(ValueError):
        validate_bundle_manifest(value["manifest"])

def test_short_source_sha_and_historical_reads_remain_compatible(tmp_path):
    value=v2();value["manifest"]["code_sha"]="abcdef1"
    store=LocalDisplayStore(tmp_path);store.publish(value,now=NOW)
    assert store.load_bundle() is not None
    assert LocalDisplayReader(store).read_overview()["is_stale"] is True

def test_invalid_cache_pointer_cannot_escape_store(tmp_path):
    store=LocalDisplayStore(tmp_path)
    (tmp_path/"latest.json").write_text(json.dumps({"bundle_file":"../outside.json"}))
    assert store.load_bundle() is None

@pytest.mark.parametrize("which",["target","previous"])
def test_publication_never_reads_symlink_paths(tmp_path,monkeypatch,which):
    store=LocalDisplayStore(tmp_path);store.publish(v2(1),now=NOW)
    value=v2(2)
    guarded=store.previous_link if which=="previous" else tmp_path/f"bundle_2_{digest(value['manifest'])[:16]}.json"
    guarded.write_text("synthetic foreign content",encoding="utf-8")
    native_symlink=Path.is_symlink;native_read=Path.read_bytes
    monkeypatch.setattr(Path,"is_symlink",lambda path:True if path==guarded else native_symlink(path))
    def forbid_read(path):
        if path==guarded:raise AssertionError("publication must not follow symlink")
        return native_read(path)
    monkeypatch.setattr(Path,"read_bytes",forbid_read)
    with pytest.raises(ValueError,match="symlink|unsafe"):
        store.publish(value,now=NOW)

def test_gzip_path_does_not_use_unbounded_decompress(tmp_path,monkeypatch):
    from app.workspace import shadow_api
    from app.workspace.shadow_auth import signed_headers
    settings=SimpleNamespace(shadow_sync_enabled=True,shadow_sync_root=str(tmp_path/"v1"),
        shadow_sync_code_sha="a"*40,shadow_sync_config_hash="b"*64,shadow_sync_producer_token=SecretStr("x"*32),
        shadow_sync_active_key_id="synthetic",shadow_sync_signing_secret=SecretStr("s"*32),
        shadow_sync_max_bytes=33554432,shadow_sync_max_generations=20,shadow_sync_max_request_bytes=65536,
        local_display_v2_store_root=str(tmp_path/"v2"),local_display_v2_max_decompressed_bytes=65536)
    monkeypatch.setattr(shadow_api,"get_settings",lambda:settings)
    body=gzip.compress(canonical(v2()))
    headers={**signed_headers(body,"synthetic","s"*32),"Authorization":"Bearer "+"x"*32,"Content-Encoding":"gzip"}
    monkeypatch.setattr(gzip,"decompress",lambda *args,**kwargs:(_ for _ in ()).throw(AssertionError("unbounded decompressor")))
    app=FastAPI();app.include_router(shadow_api.router)
    assert TestClient(app).post("/api/shadow/sync",content=body,headers=headers).status_code==200

def test_publisher_does_not_steal_aged_active_lock(tmp_path,monkeypatch):
    import os
    import time
    from app.workspace.local_schedule import LocalRunLock
    store=LocalDisplayStore(tmp_path);owner=LocalRunLock(store.lock_file)
    assert owner.acquire()
    old=time.time()-7201
    os.utime(store.lock_file,(old,old))
    attempts=[];native_unlink=Path.unlink
    def tracked_unlink(path,*args,**kwargs):
        if path==store.lock_file:attempts.append(path)
        return native_unlink(path,*args,**kwargs)
    monkeypatch.setattr(Path,"unlink",tracked_unlink)
    try:
        with pytest.raises(ValueError,match="lock"):
            store.publish(v2(),now=NOW)
        assert attempts==[], "must not try to delete an active publication lock"
    finally:
        owner.release()
    assert store.publish(v2(),now=NOW)["status"]=="accepted"

def test_failed_lock_owner_cannot_release_another_lock(tmp_path,monkeypatch):
    from app.workspace.local_schedule import LocalRunLock
    path=tmp_path/"lock"
    owner=LocalRunLock(path);other=LocalRunLock(path)
    assert owner.acquire()
    assert other.acquire() is False
    attempts=[];native_unlink=Path.unlink
    def tracked_unlink(target,*args,**kwargs):
        if target==path:attempts.append(target)
        return native_unlink(target,*args,**kwargs)
    monkeypatch.setattr(Path,"unlink",tracked_unlink)
    try:
        other.release()
        assert path.exists()
        assert attempts==[], "a failed acquirer must not attempt another owner's unlink"
    finally:
        owner.release()
    # OS-backed locks intentionally retain their inode after release.
    assert other.acquire() is True
    other.release()

def test_publication_failure_restores_files_and_both_pointers(tmp_path,monkeypatch):
    store=LocalDisplayStore(tmp_path);store.publish(v2(1),now=NOW);store.publish(v2(2),now=NOW)
    before=snapshot(tmp_path);original=store._atomic
    def fail_latest(path,data):
        if path==store.latest_link:raise OSError("synthetic interrupted pointer")
        return original(path,data)
    monkeypatch.setattr(store,"_atomic",fail_latest)
    with pytest.raises(OSError):
        store.publish(v2(3),now=NOW)
    assert snapshot(tmp_path)==before
    assert store.load_bundle()["manifest"]["sequence"]==2

def test_same_sequence_different_existing_bundle_is_rejected(tmp_path):
    store=LocalDisplayStore(tmp_path);store.publish(v2(1),now=NOW)
    value=v2(1);value["parts"]["overview"]["description"]="different";rehash(value)
    identity=digest(value["manifest"])
    (tmp_path/f"bundle_1_{identity[:16]}.json").write_bytes(canonical(value))
    before=snapshot(tmp_path)
    with pytest.raises(ValueError,match="sequence"):
        store.publish(value,now=NOW)
    assert snapshot(tmp_path)==before


def test_older_sequence_reack_restores_without_promoting(tmp_path):
    """Evicted older sequence can be re-acked; latest/previous stay put."""
    store = LocalDisplayStore(tmp_path, max_bytes=10_000_000, max_generations=20)
    first = store.publish(v2(1), now=NOW)
    store.publish(v2(2), now=NOW)
    store.publish(v2(3), now=NOW)
    # Simulate eviction of sequence 1
    for path in tmp_path.glob("bundle_1_*.json"):
        path.unlink()
    assert store.load_bundle(1) is None
    latest_before = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    previous_before = json.loads((tmp_path / "previous.json").read_text(encoding="utf-8"))
    again = store.publish(v2(1), now=NOW)
    assert again["status"] == "already_accepted"
    assert again["bundle_id"] == first["bundle_id"]
    assert again["sequence"] == 1
    assert store.load_bundle(1) is not None
    assert json.loads((tmp_path / "latest.json").read_text(encoding="utf-8")) == latest_before
    assert json.loads((tmp_path / "previous.json").read_text(encoding="utf-8")) == previous_before
    assert store.load_bundle()["manifest"]["sequence"] == 3


def test_older_sequence_same_file_is_already_accepted(tmp_path):
    store = LocalDisplayStore(tmp_path)
    store.publish(v2(1), now=NOW)
    store.publish(v2(2), now=NOW)
    again = store.publish(v2(1), now=NOW)
    assert again["status"] == "already_accepted"
    assert store.load_bundle()["manifest"]["sequence"] == 2


def test_retention_keeps_more_than_five_when_budget_allows(tmp_path):
    store = LocalDisplayStore(tmp_path, max_bytes=50_000_000, max_generations=20)
    for sequence in range(1, 13):
        store.publish(v2(sequence), now=NOW)
    files = sorted(tmp_path.glob("bundle_*.json"))
    assert len(files) >= 12
    assert store.load_bundle()["manifest"]["sequence"] == 12
    assert store.load_bundle(1) is not None


def test_historical_reack_via_api_skips_live_identity_gate(tmp_path, monkeypatch):
    """Older-sequence re-ack may carry a prior cutover code_sha."""
    from app.workspace import shadow_api
    from app.workspace.shadow_auth import signed_headers
    settings = receiver_settings(tmp_path)
    settings.local_display_v2_max_bytes = 50_000_000
    monkeypatch.setattr(shadow_api, "get_settings", lambda: settings)
    store = LocalDisplayStore(tmp_path / "v2")
    old = v2(1)
    old["manifest"]["code_sha"] = "c" * 40
    rehash(old)
    store.publish(old, now=NOW)
    store.publish(v2(2), now=NOW)
    store.publish(v2(3), now=NOW)  # previous=2, latest=3; seq1 is reclaimable cache only
    for path in (tmp_path / "v2").glob("bundle_1_*.json"):
        path.unlink()
    app = FastAPI(); app.include_router(shadow_api.router)
    body = canonical(old)
    headers = {**signed_headers(body, "synthetic", "s" * 32), "Authorization": "Bearer " + "x" * 32}
    result = TestClient(app).post("/api/shadow/sync", content=body, headers=headers)
    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload["status"] == "already_accepted"
    assert payload["bundle_id"] == digest(old["manifest"])
    assert payload["sequence"] == 1
    assert LocalDisplayStore(tmp_path / "v2").load_bundle()["manifest"]["sequence"] == 3
