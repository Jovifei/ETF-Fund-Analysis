from app.utils.reproducibility import feature_schema_hash, reproducibility_payload


def test_reproducibility_payload_is_stable_and_versioned(monkeypatch):
    monkeypatch.setenv("GIT_COMMIT_SHA", "a" * 40)
    strategy = {"version": "signal-test", "forecast": {"horizons": [1, 5, 20]}}
    first = reproducibility_payload(
        strategy=strategy,
        feature_schema_version="feature-test-v1",
        features=["b", "a", "a"],
        code_component="unit-test",
    )
    second = reproducibility_payload(
        strategy=strategy,
        feature_schema_version="feature-test-v1",
        features=["a", "b"],
        code_component="unit-test",
    )
    assert first == second
    assert first["git_commit_sha"] == "a" * 40
    assert first["feature_schema_hash"] == feature_schema_hash(["a", "b"])
    assert len(first["config_hash"]) == 64
