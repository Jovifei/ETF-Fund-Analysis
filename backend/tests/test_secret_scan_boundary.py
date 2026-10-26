"""The source scanner must not skip a repository because of its parent path."""
from pathlib import Path
import shutil,subprocess,sys

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=Path("codex/skills/fund-research/scripts/check_no_secrets.py")


def scanner_repo(tmp_path):
    root=tmp_path/".codex"/"worktrees"/"synthetic-repo"
    target=root/SCRIPT
    target.parent.mkdir(parents=True)
    shutil.copy2(ROOT/SCRIPT,target)
    return root,target


def test_codex_parent_is_not_a_reason_to_ignore_all_source(tmp_path):
    root,script=scanner_repo(tmp_path)
    (root/"sample.py").write_text('token = "'+('x'*32)+'"')
    result=subprocess.run([sys.executable,str(script)],capture_output=True,text=True)
    assert result.returncode==2
    assert "sample.py:1" in result.stdout and 'x'*32 not in result.stdout


def test_generated_directories_inside_the_repo_remain_excluded(tmp_path):
    root,script=scanner_repo(tmp_path)
    generated=root/"frontend"/"node_modules"
    generated.mkdir(parents=True)
    (generated/"generated.js").write_text('token = "'+('x'*32)+'"')
    (root/"safe.py").write_text('print("safe")')
    result=subprocess.run([sys.executable,str(script)],capture_output=True,text=True)
    assert result.returncode==0


def test_allowed_fixture_cannot_hide_a_second_secret_on_the_same_line(tmp_path):
    root,script=scanner_repo(tmp_path)
    tests=root/"backend"/"tests";tests.mkdir(parents=True)
    (tests/"sample.py").write_text('allowed="legacy-machine-token-only"; token="'+('z'*32)+'"')
    result=subprocess.run([sys.executable,str(script)],capture_output=True,text=True)
    assert result.returncode==2
    assert "sample.py:1" in result.stdout and 'z'*32 not in result.stdout


def test_only_exact_quoted_fixture_is_exempt_and_only_in_tests(tmp_path):
    root,script=scanner_repo(tmp_path)
    tests=root/"backend"/"tests";tests.mkdir(parents=True)
    sample=tests/"sample.py"
    sample.write_text('token="legacy-machine-token-only"')
    assert subprocess.run([sys.executable,str(script)],capture_output=True).returncode==0
    sample.write_text('token="'+'legacy-machine-token-only'+'-not-the-fixture"')
    assert subprocess.run([sys.executable,str(script)],capture_output=True).returncode==2
    sample.unlink()
    (root/"sample.py").write_text('token="legacy-machine-token-only"')
    assert subprocess.run([sys.executable,str(script)],capture_output=True).returncode==2


def test_placeholder_text_cannot_hide_another_secret_on_the_line(tmp_path):
    root,script=scanner_repo(tmp_path)
    (root/"sample.py").write_text('placeholder="CHANGE_ME_EXAMPLE"; token="'+('y'*32)+'"')
    assert subprocess.run([sys.executable,str(script)],capture_output=True).returncode==2


def test_placeholder_candidate_value_itself_remains_allowed(tmp_path):
    root,script=scanner_repo(tmp_path)
    (root/"sample.py").write_text('token="CHANGE_ME_EXAMPLE_VALUE_WITH_NO_REAL_CREDENTIAL"')
    assert subprocess.run([sys.executable,str(script)],capture_output=True).returncode==0
