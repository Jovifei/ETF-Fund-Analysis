"""Build a bounded digest from one accepted immutable display generation."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, date, timedelta
import json
import re
from zoneinfo import ZoneInfo

from app.analysis.contracts import AnalysisEnvelope, AnalysisStatus, VerifiedAnalysisInput
from app.workspace.local_display_contract import verify_bundle_integrity
from app.workspace.local_display_read import quote_display_state
from app.workspace.protocol import safe_text
from app.workspace.shadow_bundle import digest
from app.workspace.shadow_client import _validate_receipt

TZ=ZoneInfo("Asia/Shanghai")
STATUS_REASONS={"data_not_ready":"数据未就绪", "delivery_not_confirmed":"服务器接收未确认",
                "consumer_not_observed":"网页消费待验证", "bundle_unqualified":"展示包未通过当前校验",
                "pipeline_missing":"本机流水线缺席或未完成", "smtp_not_configured":"邮件发送通道尚未配置"}

@dataclass(frozen=True)
class Digest:
    subject: str
    body: str
    binding: dict


def _context(session,slot,recipient_id,now):
    date.fromisoformat(session)
    if (not isinstance(now,datetime) or now.tzinfo is None or now.utcoffset() is None
            or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]",slot)
            or not re.fullmatch(r"[0-9a-f]{64}",recipient_id)):
        raise ValueError("explicit notification context required")


def build_status_digest(*,session,slot,recipient_id,now,reason):
    _context(session,slot,recipient_id,now)
    if reason not in STATUS_REASONS:
        raise ValueError("fixed notification reason required")
    return Digest(f"【ETF链路状态】{session} {slot}",
        f"{session} {slot}：{STATUS_REASONS[reason]}。\n"
        f"检查时间：{now.astimezone(TZ).isoformat()}。\n没有将旧数据替换为本槽决策；请查看网站的真实数据时点。",
        {"session":session,"slot":slot,"kind":"status","generation":None,"bundle_id":None,
         "recipient_id":recipient_id,"consumer_state":"NOT_OBSERVED","ai_status":"analysis_unavailable"})


def build_digest(*,bundle,receipt,session,slot,recipient_id,now,expected_code_sha,expected_config_hash,
                 kind="normal",analyzer=None,consumer=None):
    _context(session,slot,recipient_id,now)
    if kind not in {"normal","late","eod"} or not verify_bundle_integrity(bundle,now=now):
        raise ValueError("current qualified display bundle required")
    m=bundle["manifest"];parts=bundle["parts"]
    generated=datetime.fromisoformat(m["generated_at"])
    if (m["code_sha"]!=expected_code_sha or m["config_hash"]!=expected_config_hash
            or generated.astimezone(TZ).date().isoformat()!=session
            or parts["overview"].get("contains_mock") is True):
        raise ValueError("current session and approved producer required")
    planned=datetime.fromisoformat(session+"T"+slot).replace(tzinfo=TZ)
    earliest=planned-timedelta(minutes=20) if kind=="eod" else planned
    if generated<earliest:
        raise ValueError("bundle predates its notification slot")
    _validate_receipt(receipt,m,"local-display-v2")
    received=datetime.fromisoformat(receipt["received_at"])
    if received>now or received<generated:
        raise ValueError("valid actual receipt time required")
    rows=parts["overview"].get("rows")
    if (not isinstance(rows,list) or not rows or any(not isinstance(r,dict) for r in rows)
            or len(rows)!=len(m["universe"])
            or {r.get("ts_code") for r in rows}!=set(m["universe"])):
        raise ValueError("complete published digest scope required")
    facts=[]
    for row in rows:
        code=row["ts_code"];detail=parts["details"].get(code)
        if not isinstance(detail,dict):
            raise ValueError("published detail object required")
        raw_quote=detail.get("quote")
        raw_quote={} if raw_quote is None else raw_quote
        if not isinstance(raw_quote,dict) or any(type(raw_quote[k]) is not bool for k in
                ("is_realtime","timestamp_verified","is_mock") if k in raw_quote):
            raise ValueError("typed published quote required")
        if any(raw_quote.get(k) is not None and (not isinstance(raw_quote[k],str) or len(raw_quote[k])>128)
               for k in ("source","source_time","status")):
            raise ValueError("bounded published quote metadata required")
        daily=detail.get("daily_as_of")
        if daily is not None:
            if not isinstance(daily,str):
                raise ValueError("dated published daily input required")
            date.fromisoformat(daily)
        if row.get("grade") is not None and not isinstance(row["grade"],str):
            raise ValueError("published research grade text required")
        quote=quote_display_state(raw_quote,expired=False,now=now)
        if quote.get("is_mock") is True or "mock" in str(quote.get("source","")).lower():
            raise ValueError("mock material cannot become a live digest")
        grade=safe_text(str(row.get("grade") or "数据未就绪")[:64])
        price=quote.get("price")
        if price is not None and (type(price) not in (int,float) or not __import__("math").isfinite(price)):
            raise ValueError("finite published price required")
        facts.append({"code":code,"research_grade":grade,"daily_as_of":detail.get("daily_as_of"),
                      "price":price,"quote_source_time":quote.get("source_time"),
                      "quote_status":quote.get("status"),"is_realtime":quote.get("is_realtime") is True})
    observation=m.get("input_observation") or {}
    expected_observation={"contract_version":"settled-daily-research-input-v1","type":"settled_daily_research",
        "basis":"settled_daily_bars","source_session":session,"scope_hash":digest(sorted(m["universe"])),
        "is_realtime":False,"source_qualification":"UNKNOWN","actionable":False,"calibration_status":"not_calibrated"}
    complete_observation=(isinstance(observation,dict)
        and all(type(observation.get(k)) is type(v) and observation[k]==v for k,v in expected_observation.items())
        and all(isinstance(observation.get(k),str) and re.fullmatch(r"[a-f0-9]{64}",observation[k])
                for k in ("daily_input_hash","quote_batch_hash","quote_task_hash")))
    if kind=="eod" and (not complete_observation or any(f["daily_as_of"]!=session for f in facts)
            or observation.get("type")!="settled_daily_research" or observation.get("source_session")!=session
            or observation.get("is_realtime") is not False):
        raise ValueError("settled current-session daily material required")
    reference="bundle:"+digest(m)
    text=json.dumps({"session":session,"slot":slot,"generation":m["sequence"],"facts":facts,
                     "research_only":True,"actionable":False},ensure_ascii=False,separators=(",",":"))
    if len(text)>11000:
        raise ValueError("bounded digest input exceeded")
    safe_text(text)
    input_data=VerifiedAnalysisInput(news_title="ETF冻结研究批次：只解释已有事实，不计算数值或给出交易指令",
                                     news_body=text,evidence_ids=(reference,))
    ai_status,ai_result_hash,ai_lines="analysis_unavailable",None,[]
    ai_model,ai_provider=None,None
    if analyzer is not None:
        try:
            result=analyzer(input_data)
            if (not isinstance(result,AnalysisEnvelope) or result.status is not AnalysisStatus.COMPLETED
                    or result.input_hash!=input_data.input_hash or result.output is None
                    or result.prompt_version!=input_data.prompt_version or result.schema_version!=input_data.schema_version
                    or not result.output.evidence_ids or not set(result.output.evidence_ids)<={reference}):
                raise ValueError("bound AI evidence required")
            ai_lines=[*result.output.facts,*result.output.inferences,*result.output.risk_flags]
            if result.output.confidence_statement:
                ai_lines.append(result.output.confidence_statement)
            if sum(len(line) for line in ai_lines)>12000:
                raise ValueError("bounded AI explanation required")
            for line in ai_lines:
                safe_text(line)
                if re.search(r"[0-9]",line):
                    raise ValueError("AI numeric text is not an authoritative input")
            ai_status,ai_result_hash="completed",result.result_hash
            ai_model,ai_provider=result.model,result.provider.value
        except Exception:
            ai_lines=[]
    state="NOT_OBSERVED"
    if (isinstance(consumer,dict) and consumer.get("generation")==m["sequence"]
            and consumer.get("bundle_id")==digest(m) and consumer.get("state")=="READER_MATCHED"):
        state="READER_MATCHED"
    body=[f"{session} {slot} 研究摘要"+("（迟到补发）" if kind=="late" else ""),
          f"批次：{m['sequence']}；生成：{generated.astimezone(TZ).isoformat()}；服务器接收：{received.astimezone(TZ).isoformat()}。",
          "网站服务器已核同批读取；正常登录页面需另行验收。" if state=="READER_MATCHED" else "服务器已接收；网页消费待验证，不能仅凭回执认定页面已刷新。",
          "研究分级及价格均来自冻结数据；UNKNOWN / actionable=false / not_calibrated。"]
    for f in facts:
        body.append(f"{f['code']}：研究分级 {f['research_grade']}；日线 {f['daily_as_of'] or '未知'}；"
                    f"价格 {f['price'] if f['price'] is not None else '缺失'}；报价时点 {f['quote_source_time'] or '未知'}；"
                    +("实时观察" if f["is_realtime"] else "非实时")+"。")
    body.extend(["AI文字解释：",*ai_lines] if ai_lines else ["AI解释不可用；以上为确定性研究摘要。"])
    return Digest(f"【ETF研究】{session} {slot} 批次{m['sequence']}"+("（补发）" if kind=="late" else ""),
                  "\n".join(body),{"session":session,"slot":slot,"kind":kind,"generation":m["sequence"],
                  "bundle_id":digest(m),"recipient_id":recipient_id,"ai_input_hash":input_data.input_hash,
                  "ai_result_hash":ai_result_hash,"ai_status":ai_status,"consumer_state":state,
                  "ai_model":ai_model,"ai_provider":ai_provider,"ai_prompt_version":input_data.prompt_version,
                  "ai_schema_version":input_data.schema_version,
                  "data_as_of":session if kind=="eod" else min((f["daily_as_of"] or "unknown") for f in facts),
                  "expires_at":m["expires_at"]})
