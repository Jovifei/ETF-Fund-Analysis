from app.services.task_outcome import coverage_outcome


def test_stale_completed_outputs_are_partial_not_current_success():
    result = coverage_outcome(4, 4, stale_count=4)
    assert result["status"] == "partial"
    assert result["coverage_complete"] is False
