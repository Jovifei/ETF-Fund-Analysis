"""Real CurrentUser DPAPI round-trip; no real email or credential is used."""
import os
import pytest
from app.workspace.local_notifications import SMTPConfig

@pytest.mark.skipif(os.name!="nt",reason="Windows CurrentUser secret protection")
def test_smtp_config_keeps_secret_encrypted_and_defaults_disabled(tmp_path):
    from app.workspace.local_notifications import save_smtp_config,load_smtp_config
    c=SMTPConfig(host="smtp.example.invalid",port=465,username="fixture@example.invalid",
                 password="synthetic-authorization-code",sender="fixture@example.invalid",recipient="fixture@example.invalid")
    path=save_smtp_config(tmp_path,c)
    assert c.password not in path.read_text()
    loaded,policy=load_smtp_config(tmp_path)
    assert loaded.password==c.password and loaded.recipient_id==c.recipient_id
    assert policy=={"enabled":False,"owner_confirmed":False}
    assert "synthetic-authorization-code" not in repr(loaded)

@pytest.mark.skipif(os.name!="nt",reason="Windows CurrentUser secret protection")
def test_config_cannot_silently_overwrite_existing_settings(tmp_path):
    from app.workspace.local_notifications import save_smtp_config
    c=SMTPConfig(host="smtp.example.invalid",port=465,username="fixture@example.invalid",
                 password="synthetic-code",sender="fixture@example.invalid",recipient="fixture@example.invalid")
    save_smtp_config(tmp_path,c)
    with pytest.raises(ValueError,match="already"):
        save_smtp_config(tmp_path,c)
