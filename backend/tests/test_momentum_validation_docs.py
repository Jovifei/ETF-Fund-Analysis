from __future__ import annotations

from pathlib import Path


def test_research_scheme_and_audit_documents_exist_and_valid():
    worktree_root = Path(__file__).resolve().parents[2]
    docs_dir = worktree_root / "docs"

    v2_scheme = docs_dir / "research" / "ETF_QUANT_STRATEGY_RESEARCH_AND_INTEGRATION_20261024_V2.md"
    audit_doc = docs_dir / "audits" / "ETF_FACTOR_EMPIRICAL_INDEPENDENT_AUDIT_20261024.md"
    checklist = docs_dir / "research" / "MOMENTUM_VALIDATION_ACCEPTANCE_CHECKLIST_20261024.md"

    for doc_path in [v2_scheme, audit_doc, checklist]:
        assert doc_path.exists(), f"Missing required document: {doc_path}"
        content = doc_path.read_text(encoding="utf-8")
        assert len(content) > 500, f"Document {doc_path} is unexpectedly small"
        assert "research_only" in content
        assert "actionable=false" in content

    # Verify v2 scheme core concepts
    scheme_text = v2_scheme.read_text(encoding="utf-8")
    assert "120日截面动量" in scheme_text
    assert "12月时间序列动量" in scheme_text
    assert "tsmom_volscaled" in scheme_text
    assert "双动量" in scheme_text
    assert "T+1" in scheme_text

    # Verify independent audit key points
    audit_text = audit_doc.read_text(encoding="utf-8")
    assert "Sharpe" in audit_text
    assert "波动缩放" in audit_text
    assert "recent_all_enabled" in audit_text
    assert "z_mr_20" in audit_text

    # Verify checklist gates
    chk_text = checklist.read_text(encoding="utf-8")
    assert "A0" in chk_text
    assert "A1" in chk_text
    assert "A2" in chk_text
    assert "A3" in chk_text
    assert "A4" in chk_text
