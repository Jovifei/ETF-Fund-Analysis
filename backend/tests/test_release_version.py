from app.core.config import Settings


def test_v100_release_reports_the_canonical_application_version():
    assert Settings(_env_file=None).app_version == "1.0.0"
