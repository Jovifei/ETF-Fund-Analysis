#!/usr/bin/env python3
"""Authenticated, persistent LOOPBACK workspace; no demo, token copying or model calls.

Use an external private env file and a NEW external data directory. PostgreSQL
and production HTTPS use compose.workspace.yml, not this SQLite local runner.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {"MARKET_PROVIDER", "TUSHARE_TOKEN", "TUSHARE_TIMEOUT_SECONDS", "AKSHARE_TIMEOUT_SECONDS",
    "NEWS_RSS_URLS", "NEWS_RSS_TIMEOUT_SECONDS", "MINUTE_BARS_ENABLED", "FTSHARE_ENABLED",
    "FTSHARE_QUALIFICATION", "WORKSPACE_BRIDGE_ENABLED", "WORKSPACE_DAILY_REVIEW_ENABLED"}


def prepare(config: Path, data: Path):
    if config.is_symlink() or data.is_symlink():
        raise ValueError("Private paths must not be symbolic links")
    config, data = config.resolve(), data.resolve()
    if config.is_relative_to(ROOT) or data.is_relative_to(ROOT):
        raise ValueError("Private config and data must be OUTSIDE the source repository")
    if not config.is_file() or config.stat().st_size > 32768:
        raise ValueError("Missing or oversized private config")
    if os.name != "nt" and config.stat().st_mode & 0o077:
        raise ValueError("Private config requires mode 0600")
    if (ROOT / '.env').exists() or (ROOT / 'deploy/.env.production').exists():
        raise ValueError("Use a clean source directory without legacy production dotenv files")
    from dotenv import dotenv_values
    values = dotenv_values(config, interpolate=False)
    if set(values) - ALLOWED:
        raise ValueError("Unsupported private configuration keys; use workspace.live.env.example")
    if values.get('MARKET_PROVIDER', 'public_composite') not in {'public_composite','composite','akshare','tushare'}:
        raise ValueError("Local LIVE mode requires an explicit real provider; mock is not allowed")
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != 'nt' and data.stat().st_mode & 0o077:
        raise ValueError("Private data directory requires mode 0700")
    env = dict(os.environ)
    env.update({key: value or '' for key, value in values.items()})
    env.update(PYTHONPATH=str(ROOT/'backend'), APP_ENV='development', AUTH_ENABLED='true',
        AUTH_COOKIE_SECURE='false', AUTO_CREATE_SCHEMA='false', ALLOW_MOCK_FALLBACK='false',
        REGISTRATION_ENABLED='false', LLM_ENABLED='false', ANALYSIS_ENABLED='false', OCR_MODE='disabled',
        DATABASE_URL=f"sqlite:///{(data/'workspace.sqlite3').as_posix()}", REPORTS_DIR=str(data/'reports'),
        BACKUP_DIR=str(data/'backups'), WORKSPACE_UI_ENABLED='true', TZ='Asia/Shanghai')
    # This launcher is configured by the explicit file, not by an unrelated
    # shell/demo session. Missing flags always remain closed.
    env['MARKET_PROVIDER'] = values.get('MARKET_PROVIDER') or 'public_composite'
    for key, default in {'TUSHARE_TOKEN':'', 'NEWS_RSS_URLS':'', 'MINUTE_BARS_ENABLED':'false',
                         'FTSHARE_ENABLED':'false', 'FTSHARE_QUALIFICATION':'unverified',
                         'WORKSPACE_BRIDGE_ENABLED':'false', 'WORKSPACE_DAILY_REVIEW_ENABLED':'false'}.items():
        env[key] = values.get(key) or default
    # Model credentials/old machine tokens have no role in this launcher.
    for key in ('PRIVATE_ACCESS_TOKEN','OPENAI_API_KEY','ANTHROPIC_API_KEY','DEEPSEEK_API_KEY'):
        env[key]=''
    return env, data


def stop_owned(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    else:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name != 'nt': os.killpg(process.pid, signal.SIGKILL)
        else: process.kill()
        process.wait(timeout=5)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init','serve','bootstrap-admin'])
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8082)
    args=parser.parse_args()
    if not 1024 <= args.port <= 65535: parser.error('port must be 1024..65535')
    try: env,data=prepare(args.config,args.data_dir)
    except (ValueError,OSError): parser.error('Private setup rejected; check external paths, permissions and example keys. No values printed.')
    database=data/'workspace.sqlite3'
    if args.command=='init':
        if database.exists(): parser.error('Existing database: back up and migrate explicitly; init never overwrites it.')
        subprocess.run([sys.executable,'-m','alembic','upgrade','head'],env=env,cwd=ROOT,check=True)
        print('Database initialized. Next run bootstrap-admin (interactive password), then serve.')
        return 0
    if not database.is_file(): parser.error('Run init first. serve never silently creates a new database.')
    if args.command=='bootstrap-admin':
        return subprocess.run([sys.executable,'-m','app.cli','auth-bootstrap-admin'],env=env,cwd=ROOT).returncode
    if not (ROOT/'backend/app/workspace_dist/index.html').is_file(): parser.error('Build the frontend before serving.')
    # Schema check is read-only; no automatic migrations on serve.
    check="from app.db.session import session_scope; from sqlalchemy import text\nwith session_scope() as db:\n assert db.scalar(text('SELECT version_num FROM alembic_version')) == 'd40609090002', 'migration required'"
    subprocess.run([sys.executable,'-c',check],env=env,cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    children=[]
    try:
        for command in ([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(args.port)],
                        [sys.executable,'-m','app.workspace.worker']):
            children.append(subprocess.Popen(command,env=env,cwd=ROOT,start_new_session=os.name!='nt'))
        print(f'Persistent LIVE workspace: http://127.0.0.1:{args.port} . Login, then queue price updates in Settings. No scheduled fetch/model enabled by this command.')
        while all(p.poll() is None for p in children): time.sleep(0.5)
        return next((p.returncode for p in children if p.poll() is not None),1) or 1
    except KeyboardInterrupt:
        return 0
    finally:
        for child in reversed(children): stop_owned(child)


if __name__=='__main__':
    raise SystemExit(main())
