"""Offline SHADOW export/publish/compare. Inputs are public local projections only.
No provider fetch, database sync, credentials, or canonical route mutations.
"""
import argparse,json,sys
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.workspace.shadow_bundle import ShadowStore,make_bundle,digest

def main():
    p=argparse.ArgumentParser();p.add_argument('operation',choices=['export','publish','compare']);p.add_argument('--board');p.add_argument('--charts');p.add_argument('--market');p.add_argument('--bundle',required=True);p.add_argument('--store');p.add_argument('--code-sha',required=True);p.add_argument('--config-hash',required=True);p.add_argument('--sequence',type=int);p.add_argument('--generated-at');p.add_argument('--expires-at');a=p.parse_args()
    store=ShadowStore(a.store or '.',code_sha=a.code_sha,config_hash=a.config_hash)
    if a.operation=='export':
        read=lambda path:json.loads(Path(path).read_text(encoding='utf-8'))
        value=make_bundle(read(a.board),read(a.charts),read(a.market),sequence=a.sequence,generated_at=datetime.fromisoformat(a.generated_at),expires_at=datetime.fromisoformat(a.expires_at),code_sha=a.code_sha,config_hash=a.config_hash)
        store.validate(value,datetime.now(timezone.utc));Path(a.bundle).write_bytes(__import__('app.workspace.shadow_bundle',fromlist=['canonical']).canonical(value));print('public shadow bundle exported')
    else:
        value=json.loads(Path(a.bundle).read_bytes())
        if a.operation=='publish':print(json.dumps(store.publish(value)))
        else:
            actual=store.read();expected=digest(value['manifest'])
            match=actual['bundle_id']==expected and all(digest(actual[key])==value['manifest']['parts'][key] for key in ['board','charts','market'])
            print(json.dumps({'same_manifest':match,'bundle_id':actual['bundle_id'],'board_chart_market_same_generation':match}))
            if not match:raise SystemExit(1)
if __name__=='__main__':main()
