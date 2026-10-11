"""Scheduled offline local computation/export with optional explicit HTTPS sync."""
import argparse,json,sys,subprocess
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.workspace.shadow_export import local_settings,compute_local,export_local
from app.workspace.shadow_schedule import due_slot
from app.workspace.shadow_bundle import canonical,ShadowStore
from app.workspace.shadow_client import upload_bundle

def checkout_identity(expected,*,root=None):
    root=Path(root or Path(__file__).resolve().parents[1])
    paths=['backend','config','scripts','frontend/src','frontend/package.json','frontend/package-lock.json']
    try:
        actual=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True,stderr=subprocess.DEVNULL).strip()
        dirty=subprocess.check_output(['git','-C',str(root),'status','--porcelain','--untracked-files=all','--',*paths],text=True,stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError,FileNotFoundError):
        raise ValueError('versioned application checkout required') from None
    if actual!=expected or dirty:raise ValueError('exact clean application checkout required')
    return actual

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--database',required=True);p.add_argument('--code-sha',required=True);p.add_argument('--slots',default='14:30,14:45,14:50,14:55,15:00,15:15');p.add_argument('--sync-url');p.add_argument('--force-offline',action='store_true');a=p.parse_args()
    checkout_identity(a.code_sha)
    settings=local_settings(a.root,a.database);now=datetime.now(timezone.utc);slot=due_slot(settings,now,tuple(a.slots.split(',')))
    if slot is None and not a.force_offline:print('NOT_RUN: outside verified market slot');return
    root=Path(a.root);receipt=root/'last-slot.json'
    if slot and receipt.exists() and json.loads(receipt.read_bytes()).get('slot')==slot:print('SKIPPED: slot already completed');return
    results=compute_local(settings)
    if any(item.get('display_ready') is not True for item in results):raise ValueError('local task failed')
    sequence=int(now.timestamp()*1000000);value=export_local(settings,sequence=sequence,code_sha=a.code_sha)
    store=ShadowStore(root/'receiver',code_sha=a.code_sha,config_hash=value['manifest']['config_hash']);published=store.publish(value)
    actual=store.read();assert actual['bundle_id']==published['bundle_id']
    root.joinpath('bundle.json').write_bytes(canonical(value))
    if a.sync_url:upload_bundle(a.sync_url,value)
    store._atomic(receipt,canonical({'slot':slot,'bundle_id':published['bundle_id']}))
    print(json.dumps({'shadow':True,'bundle_id':published['bundle_id'],'same_manifest':True,'remote_sync':bool(a.sync_url),'data_qualification':'UNKNOWN','local_tasks':[{'task':r['task_name'],'status':r['status']} for r in results]}))
if __name__=='__main__':main()
