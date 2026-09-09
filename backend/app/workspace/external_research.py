"""Manual intake of native Vibe artifacts, separate from frozen snapshot jobs.

Hashes establish file integrity, not origin authenticity or factual correctness.
An imported report is a private, unverified candidate. This module has no network,
model, subprocess, indicator, portfolio-write, or signal-promotion capability.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models import Instrument
from app.workspace.config import workspace_settings
from app.workspace.jobs import WorkspaceError, lock_owner, owner_scope
from app.workspace.models import WorkspaceResearchJob
from app.workspace.protocol import Code, Hash, ResearchResult, StrictModel, canonical_bytes, content_hash, safe_text

ALLOWED_FILES = ('manifest.json', 'report.md', 'evidence.json', 'calculations.json', 'conflicts.json')
MAX_PACKET_BYTES = 1_000_000


def strict_json(text: str):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    def reject_constant(value):
        raise ValueError('non-finite JSON value')
    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=reject_constant)
        def depth(item, level=0):
            if level > 24:
                raise ValueError('JSON nesting exceeds bound')
            if isinstance(item, dict):
                for part in item.values(): depth(part, level+1)
            elif isinstance(item, list):
                for part in item: depth(part, level+1)
        depth(value)
        return value
    except (RecursionError, OverflowError) as exc:
        raise ValueError('invalid bounded JSON') from exc


class Artifact(StrictModel):
    # Exact original text bytes, including trailing newlines, are hash-bound.
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    name: Literal['manifest.json', 'report.md', 'evidence.json', 'calculations.json', 'conflicts.json']
    sha256: Hash
    text: str = Field(min_length=1, max_length=250_000)

    @model_validator(mode='after')
    def verified_bytes(self):
        safe_text(self.text)
        encoded = self.text.encode('utf-8')
        if len(encoded) > 350_000 or hashlib.sha256(encoded).hexdigest() != self.sha256:
            raise ValueError('artifact integrity or size mismatch')
        if self.name.endswith('.json'):
            parsed = strict_json(self.text)
            if not isinstance(parsed, (dict, list)):
                raise ValueError('artifact must be a JSON object or array')
        return self


class ExternalPacket(StrictModel):
    schema_version: Literal['etf-external-research-v1']
    producer: Literal['vibe'] = 'vibe'
    producer_version: str = Field(min_length=1, max_length=96)
    run_id: str = Field(pattern=r'^[a-zA-Z0-9_.-]{1,96}$')
    kind: Literal['etf', 'daily']
    ts_code: Code | None = None
    model: str = Field(min_length=1, max_length=96)
    upstream_status: Literal['complete', 'incomplete', 'stale']
    source_as_of: datetime
    artifacts: list[Artifact] = Field(min_length=2, max_length=5)

    @field_validator('producer_version', 'model')
    @classmethod
    def safe(cls, value):
        return safe_text(value)

    @model_validator(mode='after')
    def coherent(self):
        if (self.kind == 'etf') != (self.ts_code is not None):
            raise ValueError('ETF needs a code; daily research has no single target')
        if self.source_as_of.tzinfo is None or self.source_as_of > datetime.now(UTC)+timedelta(minutes=5):
            raise ValueError('evidence timestamp must be timezone-aware and not future')
        names = [a.name for a in self.artifacts]
        if len(names) != len(set(names)) or not {'manifest.json', 'report.md'}.issubset(names):
            raise ValueError('unique manifest and report are required')
        if len(canonical_bytes(self.model_dump(mode='json'))) > MAX_PACKET_BYTES:
            raise ValueError('external packet too large')
        # When the native manifest declares a terminal state, do not upgrade it
        # with a contradictory transport label. Other manifest versions remain
        # unverified instead of guessing their nested schema.
        manifest = strict_json(next(a.text for a in self.artifacts if a.name == 'manifest.json'))
        if isinstance(manifest, dict):
            state = manifest.get('status')
            if state in {'failed', 'error'} or (state in {'complete', 'incomplete', 'stale'} and state != self.upstream_status):
                raise ValueError('upstream status mismatch or failed upstream run')
        return self

    def digest(self):
        return content_hash(self.model_dump(mode='json'))


class ExternalImport(StrictModel):
    packet: ExternalPacket
    packet_hash: Hash
    confirm_public_data: Literal[True]


def preview(packet: ExternalPacket) -> dict:
    return {
        'packet_hash': packet.digest(), 'kind': packet.kind, 'ts_code': packet.ts_code,
        'producer': packet.producer, 'producer_version': packet.producer_version,
        'upstream_status': packet.upstream_status, 'model': packet.model,
        'source_as_of': packet.source_as_of.isoformat(),
        'artifacts': [{'name':a.name, 'sha256':a.sha256, 'bytes':len(a.text.encode())} for a in packet.artifacts],
        'model_called': False, 'actionable': False, 'writes': False,
        'warnings': ['外部报告未经本系统事实验证；哈希不证明作者身份。',
                     '导入只建立待审核候选，不补写现有任务证据，不升级指标、概率或策略资格。',
                     '请确认文件不含账户、成本、登录信息或其他个人隐私。'],
    }


def import_packet(db: Session, packet: ExternalPacket, expected_hash: str, user_id: int | None):
    digest, scope = packet.digest(), owner_scope(user_id)
    if digest != expected_hash:
        raise WorkspaceError(409, 'external_preview_changed')
    lock_owner(db, scope)
    key = content_hash({'external_packet':digest})
    existing = db.scalar(select(WorkspaceResearchJob).where(WorkspaceResearchJob.owner_scope == scope, WorkspaceResearchJob.idempotency_key == key))
    if existing:
        return existing, False
    if packet.ts_code and not db.scalar(select(Instrument.id).where(Instrument.ts_code == packet.ts_code, Instrument.kind.in_(('ETF','LOF')))):
        raise WorkspaceError(404, 'instrument_not_found')
    now = datetime.now(UTC)
    recent = db.scalar(select(func.count()).select_from(WorkspaceResearchJob).where(WorkspaceResearchJob.owner_scope == scope, WorkspaceResearchJob.created_at >= now-timedelta(days=1))) or 0
    if recent >= workspace_settings().daily_job_budget:
        raise WorkspaceError(429, 'research_job_budget_exceeded')
    quality = 'stale' if packet.upstream_status == 'stale' or packet.source_as_of < now-timedelta(days=2) else 'incomplete' if packet.upstream_status == 'incomplete' else 'external_unverified'
    evidence = [{'id':f'external:{a.name}', 'kind':'external_untrusted_artifact', 'source':'user_imported_vibe_export',
                 'sha256':a.sha256, 'text':a.text, 'as_of':packet.source_as_of.isoformat(),
                 'available_at':now.isoformat(), 'source_time_verified':False} for a in packet.artifacts]
    bundle = {
        'schema_version':'etf-evidence-bundle-v1', 'origin':'external_archive',
        'request':{'kind':packet.kind, 'ts_code':packet.ts_code, 'include_holdings':False},
        'source_as_of':packet.source_as_of.isoformat(), 'source_snapshot_id':None,
        'external_packet_hash':digest, 'upstream_run_id':packet.run_id, 'upstream_status':packet.upstream_status,
        'quality':quality, 'privacy':'user_confirmed_public_artifacts', 'evidence':evidence,
        'constraints':{'actionable':False, 'research_only':True, 'source_time_verified':False,
                       'origin_identity_verified':False, 'external_content_is_untrusted':True,
                       'no_action_or_position_output':True, 'historical_1430_backtest':'not_qualified',
                       'note':'External archive, not an execution of a website-generated frozen-snapshot task.'},
    }
    job_id, input_hash = uuid4().hex, content_hash(bundle)
    report = next(a.text for a in packet.artifacts if a.name == 'report.md')
    limitations = ['导入来源与模型名称为上报信息，未独立验证。',
                   '此报告不代表本系统当前技术状态；原始资料仅供复核，不自动转为事实。',
                   '网站未调用模型；完成状态仅表示研究包已接收，不证明上游研究合格。']
    if len(report) > 50_000: limitations.append('正文展示截取前 50000 字符；完整原文保存在哈希绑定的导出证据中。')
    result = ResearchResult(schema_version='etf-research-result-v1',job_id=job_id,input_hash=input_hash,
        producer='vibe',producer_version=packet.producer_version,model=packet.model,
        summary=f'外部 Vibe 研究归档（未验证）：{packet.ts_code or "市场复盘"}；上游状态 {packet.upstream_status}',
        evidence_ids=[e['id'] for e in evidence], limitations=limitations,report_markdown=report[:50_000])
    output = result.model_dump(mode='json')
    row = WorkspaceResearchJob(job_id=job_id,user_id=user_id,owner_scope=scope,idempotency_key=key,
        kind=packet.kind,ts_code=packet.ts_code,status='completed',quality=quality,review_status='pending',
        input_hash=input_hash,bundle_json=bundle,result_json=output,result_hash=content_hash(output),
        created_at=now,completed_at=now,expires_at=now+timedelta(hours=workspace_settings().job_ttl_hours))
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(WorkspaceResearchJob).where(WorkspaceResearchJob.owner_scope == scope, WorkspaceResearchJob.idempotency_key == key))
        if existing is None:
            raise WorkspaceError(409, 'external_import_conflict') from None
        return existing, False
    return row, True


def packet_from_directory(directory: Path, **metadata) -> ExternalPacket:
    """Read five explicitly permitted native files, never .local, raw, or auth trees."""
    directory = Path(directory).absolute()
    if any(p.is_symlink() for p in (directory, *directory.parents)) or not directory.is_dir():
        raise ValueError('symbolic or missing run directory')
    artifacts = []
    for name in ALLOWED_FILES:
        path = directory / name
        if path.is_symlink(): raise ValueError('symbolic artifact is forbidden')
        if not path.exists(): continue
        if not path.is_file() or path.stat().st_size > 350_000:
            raise ValueError('artifact exceeds file bound')
        with path.open('rb') as handle:
            data = handle.read(350_001)
        if len(data)>350_000: raise ValueError('artifact exceeds file bound')
        artifacts.append(Artifact(name=name,sha256=hashlib.sha256(data).hexdigest(),text=data.decode('utf-8')))
    return ExternalPacket(schema_version='etf-external-research-v1',artifacts=artifacts,**metadata)
