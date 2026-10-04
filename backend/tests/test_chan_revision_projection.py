"""Preserve verified revision metadata without altering chart geometry or storage."""
import json
from copy import deepcopy
from pathlib import Path

import pytest
from app.workspace.chan_chart_overlay import project_persisted_chan

FIXTURES = Path(__file__).resolve().parents[2] / "frontend" / "tests" / "fixtures"
BASE = json.loads((FIXTURES / "chan_chart_projection.json").read_text())
REVISION = json.loads((FIXTURES / "chan_revision_evidence.json").read_text())


def test_revision_metadata_is_allowlisted_and_does_not_change_the_existing_projection():
    evidence = {**deepcopy(BASE["evidence"]), **deepcopy(REVISION)}
    evidence["diagnostics"] = {"private": "must-not-leak"}
    evidence["transitions"][0]["extra"] = "must-not-leak"
    before = deepcopy(evidence)
    result = project_persisted_chan(evidence, "basis-research")
    assert result.pop("revision_evidence") == REVISION
    assert result == BASE["chart"]["chan_observation"]
    assert evidence == before


def test_legacy_projection_is_byte_equivalent_without_a_transition_list():
    result = project_persisted_chan(deepcopy(BASE["evidence"]), "basis-research")
    assert result == BASE["chart"]["chan_observation"]
    assert "revision_evidence" not in result


@pytest.mark.parametrize("transitions", [None, {}, "UNKNOWN"])
def test_unavailable_transition_list_is_not_an_empty_success(transitions):
    evidence = {**deepcopy(BASE["evidence"]), "transitions": transitions}
    assert "revision_evidence" not in project_persisted_chan(evidence, "basis-research")


def test_empty_verified_transition_list_stays_distinct_from_legacy_unknown():
    evidence = {**deepcopy(BASE["evidence"]), "transitions": []}
    result = project_persisted_chan(evidence, "basis-research")
    assert result["revision_evidence"]["transitions"] == []
    assert result["revision_evidence"]["cutoff_at"] is None


def test_malformed_metadata_and_unknown_transition_codes_fail_closed():
    evidence = {**deepcopy(BASE["evidence"]), "sequence_number": True,
                "cutoff_at": {}, "input_hash": [], "transitions": [
                    {"structure_key": 3, "status": "CONFIRMED", "revision_id": {},
                     "prior_revision_id": False, "reappearance": "true"}, None]}
    result = project_persisted_chan(evidence, "basis-research")["revision_evidence"]
    assert result["sequence_number"] is None
    assert result["cutoff_at"] is None
    assert result["input_hash"] is None
    assert len(result["transitions"]) == 2
    assert all(all(value is None for value in row.values()) for row in result["transitions"])


@pytest.mark.parametrize("reason", ["snapshot_missing", "persistent_evidence_corrupt", "unsupported_interval"])
def test_unavailable_evidence_cannot_leak_a_revision_card(reason):
    evidence = {**deepcopy(BASE["evidence"]), **deepcopy(REVISION), "available": False, "reason_code": reason}
    result = project_persisted_chan(evidence, "basis-research")
    assert "revision_evidence" not in result
    assert result["drawable"] is False


def test_price_mismatch_does_not_project_revision_evidence_or_change_fallback():
    evidence = {**deepcopy(BASE["evidence"]), **deepcopy(REVISION)}
    before = project_persisted_chan(BASE["evidence"], "different-basis")
    assert project_persisted_chan(evidence, "different-basis") == before
