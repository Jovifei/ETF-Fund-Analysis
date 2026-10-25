"""Non-zero CLI exits need a stdout sentinel: pipelines hide the process exit code."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_cli(name="run_local_compute"):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_failure_exit_emits_machine_readable_sentinel(capsys):
    cli = load_cli()
    assert cli.emit_exit(1) == 1
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["exit_code"] == 1 and payload["status"] == "failed"


def test_success_exit_stays_silent(capsys):
    cli = load_cli()
    assert cli.emit_exit(0) == 0
    assert capsys.readouterr().out == ""
