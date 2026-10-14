"""Independent shadow bundles. No canonical routes, providers or database writes."""
from __future__ import annotations
import hashlib
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4

CONTRACT='shadow-display-v1'
PARTS={'board','charts','market'}
FORBIDDEN={'holdings','accounts','cookie','cookies','token','password','authorization','user_id','account_id'}
def canonical(value):
    try:return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')
    except (ValueError,TypeError,RecursionError) as exc:raise ValueError('invalid JSON') from exc
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def timestamp(value):
    try: parsed=datetime.fromisoformat(value)
    except (ValueError,TypeError):raise ValueError('invalid timestamp') from None
    if parsed.tzinfo is None:raise ValueError('timezone required')
    return parsed.astimezone(timezone.utc)
def public_only(value):
    if isinstance(value,dict):
        required_flags={'actionable':False,'research_only':True,'qualified':False,'qualification':'UNKNOWN','calibration_status':'not_calibrated'}
        for key,expected in required_flags.items():
            if key in value and (type(value[key]) is not type(expected) or value[key]!=expected):raise ValueError('unsafe nested safety flag')
        if any(str(key).lower() in FORBIDDEN for key in value):raise ValueError('private fields prohibited')
        for item in value.values():public_only(item)
    elif isinstance(value,list):
        for item in value:public_only(item)
def make_bundle(board,charts,market,*,sequence,generated_at,expires_at,code_sha,config_hash):
    blobs={'board':board,'charts':charts,'market':market}
    manifest=dict(supported_intervals=['1d'],producer_id='local-research',permission_scope='WRITE_ONLY_SHADOW',source_snapshot_time=generated_at.isoformat(),contract=CONTRACT,sequence=sequence,generated_at=generated_at.isoformat(),expires_at=expires_at.isoformat(),code_sha=code_sha,config_hash=config_hash,parts={key:digest(value) for key,value in blobs.items()},research_only=True,actionable=False)
    return {'manifest':manifest,'blobs':blobs}

class ShadowStore:
    def __init__(self,root,*,code_sha,config_hash,max_bytes=64*1024*1024,max_generations=20):
        self.root=Path(root);self.code_sha=code_sha;self.config_hash=config_hash
        self.max_bytes=max_bytes;self.max_generations=max_generations
    def validate(self,bundle,now):
        canonical(bundle);public_only(bundle)
        if not isinstance(bundle,dict):raise ValueError('invalid envelope')
        if set(bundle)!={'manifest','blobs'}:raise ValueError('invalid envelope')
        m=bundle['manifest'];blobs=bundle['blobs']
        if not isinstance(m,dict) or not isinstance(blobs,dict) or not isinstance(m.get('parts'),dict):raise ValueError('invalid manifest')
        expected={'supported_intervals','producer_id','permission_scope','source_snapshot_time','contract','sequence','generated_at','expires_at','code_sha','config_hash','parts','research_only','actionable'}
        if set(m)!=expected or m['contract']!=CONTRACT:raise ValueError('contract mismatch')
        if m['code_sha']!=self.code_sha or m['config_hash']!=self.config_hash:raise ValueError('runtime identity mismatch')
        if not re.fullmatch('[a-f0-9]{40}',m['code_sha']) or not re.fullmatch('[a-f0-9]{64}',m['config_hash']):raise ValueError('invalid identity')
        if type(m['sequence']) is not int or m['sequence']<1:raise ValueError('invalid sequence')
        generated=timestamp(m['generated_at']);expires=timestamp(m['expires_at'])
        if m['supported_intervals']!=['1d']:raise ValueError('unsupported interval contract')
        if m['producer_id']!='local-research' or m['permission_scope']!='WRITE_ONLY_SHADOW' or timestamp(m['source_snapshot_time'])!=generated:raise ValueError('producer source contract')
        if generated>now or expires<=now or expires<=generated or (expires-generated).total_seconds()>7200:raise ValueError('invalid freshness')
        if m['research_only'] is not True or m['actionable'] is not False:raise ValueError('shadow safety contract')
        if set(m['parts'])!=PARTS or set(blobs)!=PARTS:raise ValueError('incomplete bundle')
        for key in PARTS:
            if not isinstance(blobs[key],dict) or digest(blobs[key])!=m['parts'][key]:raise ValueError('blob integrity')
        rows=blobs['board'].get('rows')
        if not isinstance(rows,list):raise ValueError('board rows required')
        allowed_rows={'ts_code','name','kind','grade','grade_reason','freshness','data_status','price','price_basis','theme_l1','theme_l2','research_only','actionable'}
        if any(not isinstance(row,dict) or not set(row)<=allowed_rows for row in rows):raise ValueError('nonpublic row fields')
        if set(blobs['board'])-{'rows','snapshot_id','generated_at','contains_mock','actionable'}:raise ValueError('nonpublic board fields')
        if blobs['board'].get('generated_at') and timestamp(blobs['board']['generated_at'])!=generated:raise ValueError('board source time mismatch')
        codes=[row.get('ts_code') for row in rows if isinstance(row,dict)]
        if len(codes)!=len(rows) or len(set(codes))!=len(codes) or any(not isinstance(code,str) or not re.fullmatch(r'[0-9]{6}\.(SH|SZ|BJ)',code) for code in codes):raise ValueError('invalid board universe')
        if set(blobs['charts'])!=set(codes):raise ValueError('chart universe mismatch')
        from app.workspace.shadow_projection import validate_public_chart
        for code,chart in blobs['charts'].items():
            validate_public_chart(chart,code=code,generated_at=generated)
            shanghai_date = (generated.astimezone(timezone(timedelta(hours=8))) if generated.tzinfo else generated).date().isoformat()
            for bar in chart.get('bars',[])+chart.get('research_bars',[]):
                if not isinstance(bar.get('date'),str) or bar['date'][:10]>shanghai_date:raise ValueError('chart from future')
        if set(blobs['market'])!={'references'} or any(not isinstance(ref,dict) or set(ref)-{'id','source','source_timestamp','reason'} for ref in blobs['market'].get('references',[])):raise ValueError('nonpublic market fields')
        if any(ref.get('source_timestamp') and timestamp(ref['source_timestamp'])>generated for ref in blobs['market'].get('references',[])):raise ValueError('market from future')
        if not isinstance(blobs['market'].get('references'),list):raise ValueError('market references required')
        return m
    def _atomic(self,path,data):
        temp=path.with_name('.pending-'+uuid4().hex)
        try:
            with temp.open('xb') as handle:handle.write(data);handle.flush();os.fsync(handle.fileno())
            os.replace(temp,path)
        finally:temp.unlink(missing_ok=True)
    def publish(self,bundle,*,now=None):
        now=now or datetime.now(timezone.utc);m=self.validate(bundle,now)
        self.root.mkdir(parents=True,exist_ok=True)
        if self.root.is_symlink():raise ValueError('symlink store')
        lock=self.root/'publish.lock'
        try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        except FileExistsError:raise ValueError('publisher busy') from None
        try:
            os.close(fd)
            for directory in ('blobs','manifests'):
                path=self.root/directory
                if path.is_symlink():raise ValueError('symlink directory')
                path.mkdir(exist_ok=True)
            previous=None
            if (self.root/'latest.json').exists():
                previous=json.loads((self.root/'latest.json').read_bytes())
                old=json.loads((self.root/'manifests'/previous['bundle_id']).read_bytes())
                if m['sequence']<=old['sequence'] or timestamp(m['generated_at'])<timestamp(old['generated_at']):raise ValueError('replay or out-of-order')
            bundle_id=digest(m);manifest_data=canonical(m)
            writes={self.root/'blobs'/m['parts'][key]:canonical(bundle['blobs'][key]) for key in PARTS}
            writes[self.root/'manifests'/bundle_id]=manifest_data
            for path,data in writes.items():
                if path.exists() and path.read_bytes()!=data:raise ValueError('content collision')
            # Reserve a conservative complete generation, including shared blobs.
            needed=sum(len(data) for data in writes.values())+1024
            self._gc(required_bytes=needed)
            files=[p for p in self.root.rglob('*') if p.is_file()]
            needed=sum(len(data) for path,data in writes.items() if not path.exists())+1024
            if sum(p.stat().st_size for p in files)+needed>self.max_bytes:raise ValueError('store capacity exceeded')
            # Reclaim only hash-named, unreachable generations; active pointers stay intact.
            self._gc()
            for path,data in writes.items():
                if not path.exists():self._atomic(path,data)
            if previous:self._atomic(self.root/'previous.json',canonical(previous))
            pointer={'bundle_id':bundle_id}
            self._atomic(self.root/'latest.json',canonical(pointer))
            self._gc()
            return pointer
        finally:lock.unlink(missing_ok=True)
    def _gc(self,required_bytes=0):
        protected=set()
        for name in ('latest.json','previous.json'):
            path=self.root/name
            if path.exists():protected.add(json.loads(path.read_bytes())['bundle_id'])
        manifests=sorted((self.root/'manifests').iterdir(),key=lambda p:p.stat().st_mtime_ns,reverse=True)
        keep=set(protected)
        for path in manifests:
            if len(keep)<self.max_generations:keep.add(path.name)
        for path in manifests:
            if re.fullmatch('[a-f0-9]{64}',path.name) and path.name not in keep and not path.is_symlink():path.unlink()
        self._gc_blobs()
        for path in reversed(manifests):
            used=sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file())
            if used+required_bytes<=self.max_bytes:break
            if (path.name not in protected and path.exists() and not path.is_symlink()
                    and re.fullmatch('[a-f0-9]{64}',path.name)):
                path.unlink()
                self._gc_blobs()
    def _gc_blobs(self):
        referenced=set()
        for path in (self.root/'manifests').iterdir():
            if re.fullmatch('[a-f0-9]{64}',path.name):referenced.update(json.loads(path.read_bytes())['parts'].values())
        for path in (self.root/'blobs').iterdir():
            if re.fullmatch('[a-f0-9]{64}',path.name) and path.name not in referenced and not path.is_symlink():path.unlink()
    def read(self,*,now=None,bundle_id=None):
        now=now or datetime.now(timezone.utc)
        if bundle_id is None:bundle_id=json.loads((self.root/'latest.json').read_bytes())['bundle_id']
        if not isinstance(bundle_id,str) or not re.fullmatch('[a-f0-9]{64}',bundle_id):raise ValueError('invalid bundle id')
        m=json.loads((self.root/'manifests'/bundle_id).read_bytes())
        if digest(m)!=bundle_id:raise ValueError('manifest integrity')
        blobs={}
        for key,value in m['parts'].items():
            if key not in PARTS or not isinstance(value,str) or not re.fullmatch('[a-f0-9]{64}',value):raise ValueError('invalid blob reference')
            blobs[key]=json.loads((self.root/'blobs'/value).read_bytes())
        self.validate({'manifest':m,'blobs':blobs},now)
        return {**m,**blobs,'bundle_id':bundle_id,'shadow':True}
