from app.services.task_outcome import coverage_outcome, normalize_outcome


def test_stale_completed_outputs_are_partial_not_current_success():
    result = coverage_outcome(4, 4, stale_count=4)
    assert result["status"] == "partial"
    assert result["coverage_complete"] is False


def test_stale_outputs_with_no_current_date_completion_are_still_partial():
    result = coverage_outcome(4, 0, stale_count=4, updated=4)
    assert result["status"] == "partial"
    assert result["coverage_complete"] is False


def test_normalization_preserves_stale_partial_status():
    result = normalize_outcome({"requested": 4, "completed": 0, "stale_count": 4, "updated": 4})
    assert result["status"] == "partial"
    assert result["coverage_complete"] is False
