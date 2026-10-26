"""Approved producer identities: the ECS consumer expectation must be registered."""
import importlib.util
import json
from pathlib import Path

import pytest

from app.workspace import bundle_identity

ROOT = Path(__file__).resolve().parents[2]
CURRENT_CODE_SHA = "c39ab09aa5ab26b814015f0844a6aaa45a05ffd4"
CURRENT_CONFIG_HASH = "a12c6ea1c812d2cd4b5365c3fa383dbd6c6e4296e004806897d9545008b8e5c8"


def load_cli(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_registry_approves_the_validated_next_consumer_expectation():
    identities = bundle_identity.load_identities()
    assert bundle_identity.approved_identity(CURRENT_CODE_SHA, CURRENT_CONFIG_HASH) is not None
    assert identities[-1]["code_sha"] == CURRENT_CODE_SHA
    assert identities[-1]["config_hash"] == CURRENT_CONFIG_HASH


def test_unknown_identity_is_not_silently_approved():
    assert bundle_identity.approved_identity("f" * 40, CURRENT_CONFIG_HASH) is None
    assert bundle_identity.approved_identity(CURRENT_CODE_SHA, "0" * 64) is None


@pytest.mark.parametrize("mutate", [
    lambda data: data.update(registry_version="other-version"),
    lambda data: data.update(identities=[]),
    lambda data: data["identities"][0].update(code_sha="abc"),
    lambda data: data["identities"][0].update(config_hash="short"),
    lambda data: data["identities"].append(dict(data["identities"][0])),
])
def test_malformed_registry_is_rejected(mutate):
    data = json.loads((ROOT / "config" / "bundle_identity_registry.json").read_text(encoding="utf-8"))
    mutate(data)
    with pytest.raises(ValueError):
        bundle_identity.validate_registry(data)


def test_check_script_reports_unregistered_identity(tmp_path, capsys):
    cli = load_cli("check_bundle_identity")
    assert cli.main(["--code-sha", CURRENT_CODE_SHA, "--config-hash", CURRENT_CONFIG_HASH]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "approved"
    assert cli.main(["--code-sha", "f" * 40, "--config-hash", CURRENT_CONFIG_HASH]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "unregistered"


def test_previous_producer_remains_approved_for_controlled_rollback():
    assert bundle_identity.approved_identity("dcffa8ebac1027d174b213915ff78a7e51b99097",
        "041a12867ac3588be1c45588bfcff5de8b28d6667c3ab3a42b90d20f28deac61") is not None
