"""The mail body consumes an accepted generation, never the legacy cloud DB."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import pytest
from app.workspace.shadow_bundle import digest
from app.workspace.local_display_contract import compute_parts_hashes

AT=datetime(2026,10,26,6,34,tzinfo=timezone.utc)

@pytest.fixture
def packet():
    parts={"overview":{"rows":[{"ts_code":"510300.SH","grade":"观望","actionable":False}],
                       "generated_at":AT.isoformat(),"contains_mock":False},
        "details":{"510300.SH":{"instrument":{"ts_code":"510300.SH"},"daily_as_of":"2026-10-23",
            "quote":{"price":2.5,"source_time":AT.isoformat(),"source":"sina:hq_sinajs:v1",
                     "is_realtime":False,"status":"unverified","actionable":False}}},
        "charts":{},"sectors":{"sectors":[]}}
    m={"contract_version":"local-display-v2","code_sha":"a"*40,"config_hash":"b"*64,"sequence":7,
       "generated_at":AT.isoformat(),"expires_at":(AT+timedelta(hours=2)).isoformat(),
       "actionable":False,"data_origin":"local_research","universe":["510300.SH"],
       "parts_hashes":compute_parts_hashes(parts)}
    r={"status":"accepted","sequence":7,"bundle_id":digest(m),"manifest_hash":digest(m),"received_at":AT.isoformat()}
    return {"manifest":m,"parts":parts},r


def build(packet,**changes):
    from app.workspace.local_digest import build_digest
    b,r=packet
    args=dict(bundle=b,receipt=r,session="2026-10-26",slot="14:30",recipient_id="c"*64,
              now=AT+timedelta(minutes=1),expected_code_sha="a"*40,expected_config_hash="b"*64)
    args.update(changes)
    return build_digest(**args)


def test_digest_keeps_generation_and_honest_ai_and_consumer_state(packet):
    result=build(packet)
    assert result.binding["generation"]==7 and result.binding["bundle_id"]==packet[1]["bundle_id"]
    assert result.binding["ai_status"]=="analysis_unavailable"
    assert result.binding["consumer_state"]=="NOT_OBSERVED"
    assert "2026-10-23" in result.body and "510300.SH" in result.body
    assert "2.5" in result.body and "AI解释不可用" in result.body
    assert "非实时" in result.body and "待验证" in result.body


@pytest.mark.parametrize("case",["wrong_receipt","wrong_sha","expired","previous_session","mock","not_received"])
def test_unqualified_packet_cannot_be_a_normal_current_digest(packet,case):
    b,r=deepcopy(packet)
    changes={}
    if case=="wrong_receipt":r["bundle_id"]="d"*64
    if case=="wrong_sha":changes["expected_code_sha"]="d"*40
    if case=="expired":changes["now"]=AT+timedelta(hours=3)
    if case=="previous_session":changes["session"]="2026-10-27"
    if case=="mock":
        b["parts"]["overview"]["contains_mock"]=True
        b["manifest"]["parts_hashes"]=compute_parts_hashes(b["parts"])
    if case=="not_received":r["status"]="pending"
    with pytest.raises(ValueError):build((b,r),**changes)


def test_late_ai_exception_cannot_change_the_deterministic_snapshot(packet):
    original=deepcopy(packet)
    def failed(value):raise TimeoutError("private key must not leak")
    result=build(packet,analyzer=failed)
    assert result.binding["ai_status"]=="analysis_unavailable"
    assert "private key" not in result.body and packet==original


def test_close_digest_requires_same_session_daily_material(packet):
    with pytest.raises(ValueError,match="settled"):
        build(packet,kind="eod")


def test_status_notice_does_not_require_a_successful_pipeline():
    from app.workspace.local_digest import build_status_digest
    result=build_status_digest(session="2026-10-26",slot="14:30",recipient_id="c"*64,now=AT,reason="data_not_ready")
    assert result.binding["kind"]=="status" and result.binding["generation"] is None
    assert "未就绪" in result.body


def test_eod_does_not_accept_board_only_material_with_new_daily_dates(packet):
    b,r=deepcopy(packet)
    b["parts"]["details"]["510300.SH"]["daily_as_of"]="2026-10-26"
    b["manifest"]["parts_hashes"]=compute_parts_hashes(b["parts"])
    r.update(bundle_id=digest(b["manifest"]),manifest_hash=digest(b["manifest"]))
    with pytest.raises(ValueError,match="settled"):
        build((b,r),kind="eod")


def test_successful_ai_is_bound_to_the_exact_input_and_references(packet):
    from app.analysis.contracts import AnalysisEnvelope,AnalysisOutput,AnalysisProvider,AnalysisStatus
    def analyze(value):
        output=AnalysisOutput(facts=("既有研究分级保持观望。",),evidence_ids=value.evidence_ids,
                              confidence_statement="资料仅供研究，资格尚未验证。")
        return AnalysisEnvelope(status=AnalysisStatus.COMPLETED,provider=AnalysisProvider.CODEX_OPENAI_RESPONSES,
            model="synthetic-model",latency_ms=1,input_hash=value.input_hash,prompt_version=value.prompt_version,
            schema_version=value.schema_version,output=output,result_hash=output.result_hash)
    result=build(packet,analyzer=analyze)
    assert result.binding["ai_status"]=="completed" and result.binding["ai_result_hash"]
    assert "既有研究分级保持观望" in result.body


def test_fake_ai_provenance_is_unavailable(packet):
    from app.analysis.contracts import AnalysisEnvelope,AnalysisOutput,AnalysisProvider,AnalysisStatus
    def analyze(value):
        output=AnalysisOutput(facts=("捏造的建议。",),evidence_ids=("other-bundle",),confidence_statement="不可信。")
        return AnalysisEnvelope(status=AnalysisStatus.COMPLETED,provider=AnalysisProvider.CODEX_OPENAI_RESPONSES,
            model="synthetic-model",latency_ms=1,input_hash="f"*64,prompt_version=value.prompt_version,
            schema_version=value.schema_version,output=output,result_hash=output.result_hash)
    result=build(packet,analyzer=analyze)
    assert result.binding["ai_status"]=="analysis_unavailable" and "捏造的建议" not in result.body


def test_eod_minimal_flags_are_not_a_complete_settled_observation(packet):
    b,r=deepcopy(packet)
    b["parts"]["details"]["510300.SH"]["daily_as_of"]="2026-10-26"
    b["manifest"]["input_observation"]={"type":"settled_daily_research","source_session":"2026-10-26","is_realtime":False}
    b["manifest"]["parts_hashes"]=compute_parts_hashes(b["parts"])
    r.update(bundle_id=digest(b["manifest"]),manifest_hash=digest(b["manifest"]))
    with pytest.raises(ValueError,match="settled"):
        build((b,r),kind="eod")


def test_ai_provenance_versions_remain_bound_even_if_service_is_unavailable(packet):
    result=build(packet)
    assert result.binding["ai_prompt_version"]=="analysis-v1"
    assert result.binding["ai_schema_version"]=="analysis-v1"
    assert result.binding["ai_provider"] is None and result.binding["ai_model"] is None


def test_previous_slot_packet_is_not_relabeled_as_the_next_slot(packet):
    with pytest.raises(ValueError,match="slot"):
        build(packet,slot="14:45")


def test_schema_valid_oversized_ai_text_falls_back_without_blocking_mail(packet):
    from app.analysis.contracts import AnalysisEnvelope,AnalysisOutput,AnalysisProvider,AnalysisStatus
    def analyze(value):
        output=AnalysisOutput(facts=tuple("解释"*6000 for _ in range(6)),evidence_ids=value.evidence_ids,
                              confidence_statement="仅供研究。")
        return AnalysisEnvelope(status=AnalysisStatus.COMPLETED,provider=AnalysisProvider.CODEX_OPENAI_RESPONSES,
            model="synthetic-model",latency_ms=1,input_hash=value.input_hash,prompt_version=value.prompt_version,
            schema_version=value.schema_version,output=output,result_hash=output.result_hash)
    result=build(packet,analyzer=analyze)
    assert result.binding["ai_status"]=="analysis_unavailable"
    assert result.binding["ai_result_hash"] is None and result.binding["ai_model"] is None
    assert len(result.body)<12000 and "AI解释不可用" in result.body
