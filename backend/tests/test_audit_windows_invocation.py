"""Regression for bounded, non-interactive Windows ACL invocation."""
import json
from types import SimpleNamespace


def test_windows_acl_command_has_no_inherited_stdin_and_uses_encoded_script(tmp_path, monkeypatch):
    import base64
    from app.workspace import bridge_runtime as runtime
    me = 'S-1-5-21-1-2-3-1000'
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            'current': me, 'owner': me, 'protected': True,
            'rules': [{'sid': me, 'allow': True, 'rights': 2032127}],
        }))
    monkeypatch.setattr(runtime.subprocess, 'run', run)
    runtime.windows_private_directory(tmp_path / "with 'quotes' 中文", created=False)
    args, kwargs = calls[0]
    assert args[-2] == '-EncodedCommand'
    script = base64.b64decode(args[-1], validate=True).decode('utf-16le')
    assert 'Get-Acl' in script and 'with' not in script
    assert kwargs['stdin'] == runtime.subprocess.DEVNULL
    assert kwargs['env']['ETF_ACL_TARGET'].endswith("with 'quotes' 中文")
    assert kwargs['env']['ETF_ACL_CREATE'] == '0'
    assert kwargs['timeout'] <= 30
