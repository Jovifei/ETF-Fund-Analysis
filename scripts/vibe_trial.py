#!/usr/bin/env python3
"""Opt-in isolated Vibe preparation/verification; never logs in or calls a model.

Example (after reviewing the upstream revision and installation commands):
  python scripts/vibe_trial.py doctor --root E:\\AI_Tools\\Other\\Vibe-Research
  python scripts/vibe_trial.py install --root ... --allow-network-install
  python scripts/vibe_trial.py verify --root ...
"""
from __future__ import annotations
import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

PIN = '09e8404a33ba0d05e036e01207be4701c61d692c'
UPSTREAM = 'https://github.com/simonlin1212/Vibe-Research.git'
MARKER = '.etf-isolated-vibe.json'


def validate_root(root: Path) -> Path:
    root = root.expanduser().absolute()
    home, project = Path.home().resolve(), Path(__file__).resolve().parents[1]
    if root == Path(root.anchor) or root == home or root in project.parents or root == project or project in root.parents:
        raise ValueError('Use a dedicated directory outside the application and home root')
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError('Symbolic directories are not allowed')
    return root


def environment(root: Path) -> dict[str,str]:
    # No global Codex config, model credentials, proxy passwords or DB variables.
    env = {key:os.environ[key] for key in ('PATH','SystemRoot','WINDIR','COMSPEC','PATHEXT','TEMP','TMP','LANG') if key in os.environ}
    runtime = root/'trial-runtime'
    env.update(HOME=str(runtime/'home'),USERPROFILE=str(runtime/'home'),CODEX_HOME=str(runtime/'codex-home'),
               VRA_CODEX_HOME=str(runtime/'codex-home'),VRA_DATA_ROOT=str(runtime/'data'),
               PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONNOUSERSITE='1',
               GIT_CONFIG_NOSYSTEM='1',GIT_TERMINAL_PROMPT='0',PIP_CONFIG_FILE=os.devnull,
               NPM_CONFIG_USERCONFIG=str(runtime/'empty.npmrc'))
    return env


def run(command: list[str], root: Path, log: Path, timeout: int) -> int:
    with log.open('wb') as output:
        proc = subprocess.Popen(command,cwd=root,env=environment(root),stdout=output,stderr=subprocess.STDOUT,
            start_new_session=os.name!='nt',creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0)
        try: return proc.wait(timeout=max(1,timeout))
        except subprocess.TimeoutExpired:
            if os.name=='nt': subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
            else: os.killpg(proc.pid,signal.SIGKILL)
            proc.wait(timeout=15)
            return 124


def doctor(root: Path) -> dict:
    node = shutil.which('node')
    node_version = None
    if node:
        try: node_version=subprocess.run([node,'--version'],capture_output=True,text=True,timeout=10).stdout.strip()
        except (OSError,subprocess.SubprocessError): pass
    numbers = tuple(int(v) for v in re.findall(r'\d+',node_version or '')[:3])
    return {'root_exists':root.is_dir(),'managed_trial':(root/MARKER).is_file(),
            'upstream_commit':PIN,'node_version':node_version,'node_compatible':numbers >= (22,18,0),
            'python_version':'.'.join(map(str,sys.version_info[:3])),
            'python_compatible':sys.version_info >= (3,11),
            'git_installed':bool(shutil.which('git')),'npm_installed':bool(shutil.which('npm')),
            'real_model_status':'not_verified_requires_user_official_login',
            'model_called':False,'production_database_connected':False}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['doctor','install','verify'])
    parser.add_argument('--root',required=True,type=Path)
    parser.add_argument('--allow-network-install',action='store_true')
    parser.add_argument('--max-minutes',type=int,default=30)
    args=parser.parse_args()
    root=validate_root(args.root)
    if args.command=='doctor': print(json.dumps(doctor(root),ensure_ascii=False,indent=2));return 0
    if not 1 <= args.max_minutes <= 60: parser.error('max-minutes must be 1..60')
    state=doctor(root)
    if not state['node_compatible'] or not state['python_compatible']:
        parser.error('Requires Node >=22.18 and Python >=3.11 (3.12 recommended)')
    if args.command=='install' and not args.allow_network_install:
        parser.error('Installation needs explicit --allow-network-install; doctor never installs')
    if root.exists() and not (root/MARKER).is_file():
        parser.error('Refusing to write an existing unmanaged directory')
    if args.command=='verify' and not root.is_dir(): parser.error('Install to a dedicated directory first')
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    runtime=root/'trial-runtime';logs=runtime/'logs'
    for d in [runtime,logs,runtime/'home',runtime/'codex-home',runtime/'data']:
        d.mkdir(parents=True,exist_ok=True,mode=0o700)
    (runtime/'empty.npmrc').touch(exist_ok=True)
    (root/MARKER).write_text(json.dumps({'upstream':UPSTREAM,'commit':PIN,'model_called':False}),encoding='utf-8')
    git=shutil.which('git');npm=shutil.which('npm');node=shutil.which('node')
    if not git or not npm: parser.error('git and npm are required')
    deadline=time.monotonic()+args.max_minutes*60
    records=[]
    python=root/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    commands=[]
    if args.command=='install':
        commands=[('git-init',[git,'init']),('git-fetch',[git,'fetch','--depth=1',UPSTREAM,PIN]),
                  ('git-checkout',[git,'checkout','--detach',PIN]),
                  ('virtualenv',[sys.executable,'-m','venv',str(root/'.venv')]),
                  ('orchestrator-install',[npm,'ci','--ignore-scripts','--prefix','orchestrator']),
                  ('desktop-install',[npm,'ci','--ignore-scripts','--prefix','desktop']),
                  ('python-install',[str(python),'-m','pip','install','pytest','-r','.agents/skills/data-access/scripts/requirements.txt'])]
    else:
        pin_log=logs/'commit.log'
        code=run([git,'rev-parse','HEAD'],root,pin_log,10)
        if code or pin_log.read_text().strip()!=PIN:
            parser.error('Upstream commit does not match reviewed pin')
        commands=[('orchestrator-tests',[npm,'test','--prefix','orchestrator']),
                  ('typecheck',[npm,'run','typecheck','--prefix','orchestrator']),
                  ('desktop-tests',[npm,'test','--prefix','desktop']),
                  ('desktop-build',[npm,'run','build','--prefix','desktop']),
                  ('calculation-tests',[str(python),'-m','pytest','calc/tests','-q'])]
    failed=False
    for label,command in commands:
        remaining=int(deadline-time.monotonic())
        if remaining<=0: failed=True;records.append({'check':label,'status':'budget_exhausted'});break
        log=logs/(label+'.log');start=time.monotonic()
        code=run(command,root,log,min(remaining,900))
        records.append({'check':label,'exit_code':code,'elapsed_seconds':round(time.monotonic()-start,3),
                        'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()})
        failed |= bool(code)
        if code and args.command=='install': break
    report={'schema_version':'etf-vibe-trial-v1','upstream_commit':PIN,'operation':args.command,
            'generated_at':datetime.now(UTC).isoformat(),'checks':records,'status':'failed' if failed else 'passed',
            'model_called':False,'real_model_status':'not_verified_requires_user_official_login',
            'qualification':'not_qualified','production_database_connected':False}
    (runtime/'trial-manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 1 if failed else 0


if __name__=='__main__':
    try: raise SystemExit(main())
    except (ValueError,OSError) as exc:
        print(f'Trial stopped ({type(exc).__name__}); no model has been called.',file=sys.stderr);raise SystemExit(2)
