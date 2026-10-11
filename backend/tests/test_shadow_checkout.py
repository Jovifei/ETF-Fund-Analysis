import importlib.util
from pathlib import Path
import subprocess
import pytest

spec=importlib.util.spec_from_file_location('local_job',Path(__file__).parents[2]/'scripts/shadow_local_job.py');job=importlib.util.module_from_spec(spec);spec.loader.exec_module(job)

def test_job_requires_exact_clean_application_checkout(tmp_path):
    def git(*args):return subprocess.check_output(['git','-C',str(tmp_path),*args],text=True).strip()
    git('init');(tmp_path/'backend').mkdir();(tmp_path/'backend/app.py').write_text('value=1\n');git('add','backend/app.py');git('-c','user.name=OfflineFixture','-c','user.email=fixture@example.invalid','commit','-m','fixture');sha=git('rev-parse','HEAD')
    assert job.checkout_identity(sha,root=tmp_path)==sha
    with pytest.raises(ValueError):job.checkout_identity('a'*40,root=tmp_path)
    (tmp_path/'backend/app.py').write_text('value=2\n')
    with pytest.raises(ValueError):job.checkout_identity(sha,root=tmp_path)
