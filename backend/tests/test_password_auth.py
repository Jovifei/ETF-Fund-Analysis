from __future__ import annotations

import base64
import hashlib
import hmac
from collections.abc import Iterator

import pytest
from app.core.config import Settings, get_settings
from app.core.security import AuthSessionManager, hash_password, login_throttle
from app.db.session import session_scope
from app.main import app
from app.models import AuthUser
from app.services.auth_service import AuthService
from fastapi.testclient import TestClient
from sqlalchemy import select


@pytest.fixture()
def password_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        auth_enabled=True,
        private_access_token="legacy-machine-token-only",
        auth_username="jovi",
        auth_email="jovi@example.test",
        auth_password_hash=hash_password("correct horse battery staple"),
        auth_session_secret="test-session-secret-that-is-long-and-random",
        auth_session_ttl_minutes=30,
        auth_cookie_secure=False,
        market_provider="mock",
    )


@pytest.fixture()
def password_client(monkeypatch: pytest.MonkeyPatch, password_settings: Settings) -> Iterator[TestClient]:
    import app.main as main_module

    login_throttle.reset_for_tests()
    app.dependency_overrides[get_settings] = lambda: password_settings
    monkeypatch.setattr(main_module, "settings", password_settings)
    with session_scope() as db:
        if db.scalar(select(AuthUser).where(AuthUser.username == "jovi")) is None:
            AuthService().create_user(
                db,
                username="jovi",
                email="jovi@example.test",
                password="correct horse battery staple",
                role="admin",
            )
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_settings, None)
        login_throttle.reset_for_tests()


def test_password_login_sets_http_only_session_and_csrf_cookies(password_client: TestClient) -> None:
    response = password_client.post(
        "/api/auth/login",
        json={"identifier": "jovi@example.test", "password": "correct horse battery staple"},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"authenticated": True, "identifier": "jovi", "role": "admin"}
    cookies = response.headers.get_list("set-cookie")
    assert any("fund-session=" in value and "HttpOnly" in value and "SameSite=lax" in value for value in cookies)
    assert any("fund-csrf=" in value and "HttpOnly" not in value and "SameSite=lax" in value for value in cookies)
    assert "correct horse" not in response.text


def test_secure_cookie_uses_host_prefix_and_secure_flag(
    monkeypatch: pytest.MonkeyPatch, password_settings: Settings
) -> None:
    import app.main as main_module

    settings = password_settings.model_copy(update={"auth_cookie_secure": True})
    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr(main_module, "settings", settings)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/auth/login", json={"identifier": "jovi", "password": "correct horse battery staple"}
            )
        cookies = response.headers.get_list("set-cookie")
        assert any("__Host-fund-session=" in value and "Secure" in value and "HttpOnly" in value for value in cookies)
        assert any("__Host-fund-csrf=" in value and "Secure" in value and "HttpOnly" not in value for value in cookies)
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_password_login_has_generic_error_for_unknown_and_wrong_password(password_client: TestClient) -> None:
    unknown = password_client.post("/api/auth/login", json={"identifier": "unknown", "password": "bad"})
    wrong = password_client.post("/api/auth/login", json={"identifier": "jovi", "password": "bad"})

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json() == {"detail": "登录失败，请检查凭据后重试"}


@pytest.mark.parametrize(
    ("identifier", "password"),
    [("", "bad"), ("   ", "bad"), ("unknown", "")],
)
def test_password_login_returns_generic_401_for_blank_credentials(
    password_client: TestClient, identifier: str, password: str
) -> None:
    blank = password_client.post("/api/auth/login", json={"identifier": identifier, "password": password})
    unknown = password_client.post("/api/auth/login", json={"identifier": "unknown", "password": "bad"})

    assert blank.status_code == unknown.status_code == 401
    assert blank.json() == unknown.json() == {"detail": "登录失败，请检查凭据后重试"}


def test_login_throttle_keeps_the_same_generic_failure(password_client: TestClient) -> None:
    responses = [
        password_client.post("/api/auth/login", json={"identifier": "jovi", "password": "bad"}) for _ in range(6)
    ]

    assert all(response.status_code == 401 for response in responses)
    assert len({response.text for response in responses}) == 1


def test_session_me_logout_and_csrf_for_unsafe_cookie_requests(password_client: TestClient) -> None:
    login = password_client.post(
        "/api/auth/login", json={"identifier": "jovi", "password": "correct horse battery staple"}
    )
    assert login.status_code == 200
    assert password_client.get("/api/auth/me").json() == {"authenticated": True, "identifier": "jovi", "role": "admin"}

    rejected = password_client.post("/api/demo/reset")
    assert rejected.status_code == 403
    accepted = password_client.post("/api/demo/reset", headers={"X-CSRF-Token": password_client.cookies.get("fund-csrf")})
    assert accepted.status_code == 200, accepted.text

    logout = password_client.post("/api/auth/logout", headers={"X-CSRF-Token": password_client.cookies.get("fund-csrf")})
    assert logout.status_code == 200
    assert "Max-Age=0" in logout.headers.get("set-cookie", "")
    assert password_client.get("/api/auth/me").json() == {"authenticated": False, "identifier": None, "role": None}


def test_expired_session_is_rejected_and_legacy_bearer_is_never_browser_identity(
    password_client: TestClient, password_settings: Settings
) -> None:
    manager = AuthSessionManager(password_settings)
    expired = manager.issue("jovi", now=0)
    password_client.cookies.set("fund-session", expired)

    assert password_client.get("/api/auth/me").json() == {"authenticated": False, "identifier": None, "role": None}
    legacy_headers = {"Authorization": "Bearer legacy-machine-token-only"}
    assert password_client.get("/api/auth/me", headers=legacy_headers).json() == {
        "authenticated": False,
        "identifier": None,
        "role": None,
    }
    assert password_client.get("/api/news", headers=legacy_headers).status_code == 200
    assert password_client.post("/api/demo/reset", headers=legacy_headers).status_code == 401


def test_malformed_session_cookie_is_rejected_without_a_server_error(
    password_client: TestClient, password_settings: Settings
) -> None:
    encoded = "a"  # Signed but invalid base64url: decode must not escape as a 500.
    signature = base64.urlsafe_b64encode(
        hmac.new(password_settings.auth_session_secret.get_secret_value().encode(), encoded.encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    password_client.cookies.set("fund-session", f"{encoded}.{signature}")

    assert password_client.get("/api/auth/me").json() == {"authenticated": False, "identifier": None, "role": None}
    assert password_client.get("/api/bootstrap").status_code == 401


def test_signed_json_array_session_cookie_is_rejected_without_a_server_error(
    password_client: TestClient, password_settings: Settings
) -> None:
    encoded = base64.urlsafe_b64encode(b"[]").rstrip(b"=").decode()
    signature = base64.urlsafe_b64encode(
        hmac.new(password_settings.auth_session_secret.get_secret_value().encode(), encoded.encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    password_client.cookies.set("fund-session", f"{encoded}.{signature}")

    assert password_client.get("/api/auth/me").json() == {"authenticated": False, "identifier": None, "role": None}
    assert password_client.get("/api/bootstrap").status_code == 401


def test_cookie_secure_is_required_by_production_configuration() -> None:
    with pytest.raises(ValueError, match="AUTH_COOKIE_SECURE"):
        Settings(
            _env_file=None,
            app_env="production",
            auth_enabled=True,
            private_access_token="",
            auth_username="jovi",
            auth_password_hash=hash_password("correct horse battery staple"),
            auth_session_secret="production-session-secret-that-is-long-and-random",
            auth_cookie_secure=False,
            ocr_mode="disabled",
        )


def test_production_rejects_disabled_authentication() -> None:
    with pytest.raises(ValueError, match="AUTH_ENABLED=true"):
        Settings(
            _env_file=None,
            app_env="production",
            auth_enabled=False,
            ocr_mode="disabled",
        )


@pytest.mark.parametrize("app_env", ("development", "test"))
def test_nonproduction_allows_explicitly_disabled_authentication(app_env: str) -> None:
    settings = Settings(
        _env_file=None,
        app_env=app_env,
        auth_enabled=False,
        ocr_mode="disabled",
    )

    assert settings.auth_enabled is False


def test_production_database_auth_requires_no_legacy_single_account_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in ("PRIVATE_ACCESS_TOKEN", "AUTH_USERNAME", "AUTH_PASSWORD_HASH", "AUTH_SESSION_SECRET"):
        monkeypatch.delenv(key, raising=False)
    settings = Settings(
        _env_file=None,
        app_env="production",
        auth_enabled=True,
        database_url="postgresql+psycopg://fund_app@db/fund_decision",
        auto_create_schema=False,
        auth_cookie_secure=True,
        ocr_mode="disabled",
    )

    assert not settings.password_auth_configured
    assert not settings.legacy_bearer_configured


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("private_access_token", "CHANGE_ME_AT_LEAST_32_RANDOM_CHARS", "legacy Bearer"),
        ("private_access_token", "change-this-private-token-at-least-32-chars", "legacy Bearer"),
        ("auth_email", "legacy@example.test", "AUTH_EMAIL"),
        ("auth_session_secret", "CHANGE_ME_SESSION_SECRET_REPLACE_THIS_VALUE", "AUTH_SESSION_SECRET"),
    ],
)
def test_production_rejects_obsolete_single_account_or_bearer_settings(field: str, value: str, message: str) -> None:
    options = {
        "_env_file": None,
        "app_env": "production",
        "auth_enabled": True,
        "database_url": "postgresql+psycopg://fund_app@db/fund_decision",
        "auto_create_schema": False,
        "auth_cookie_secure": True,
        "ocr_mode": "disabled",
    }
    options[field] = value

    with pytest.raises(ValueError, match=message):
        Settings(**options)


def test_development_keeps_legacy_auth_email_compatibility() -> None:
    settings = Settings(
        _env_file=None,
        app_env="development",
        auth_enabled=True,
        auth_email="legacy@example.test",
        ocr_mode="disabled",
    )

    assert settings.auth_email == "legacy@example.test"


def test_production_rejects_legacy_token_even_when_non_placeholder() -> None:
    with pytest.raises(ValueError, match="legacy Bearer"):
        Settings(
        _env_file=None,
        app_env="production",
        auth_enabled=True,
        private_access_token="legacy-only-machine-token-kept-for-cli-compatibility-1234567890",
        database_url="postgresql+psycopg://fund_app@db/fund_decision",
        auto_create_schema=False,
        auth_cookie_secure=True,
        ocr_mode="disabled",
        )


def test_known_placeholder_legacy_token_is_never_an_accepted_bearer_credential() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        auth_enabled=True,
        private_access_token="CHANGE_ME_AT_LEAST_32_RANDOM_CHARS",
        auth_username="jovi",
        auth_password_hash=hash_password("correct horse battery staple"),
        auth_session_secret="test-session-secret-that-is-long-and-random",
        auth_cookie_secure=False,
        market_provider="mock",
    )

    assert not settings.legacy_bearer_configured


def test_production_rejects_non_argon2id_account_hash() -> None:
    with pytest.raises(ValueError, match="Argon2id"):
        Settings(
            _env_file=None,
            app_env="production",
            auth_enabled=True,
            auth_username="jovi",
            auth_password_hash="not-an-argon-hash",
            auth_session_secret="production-session-secret-that-is-long-and-random",
            auth_cookie_secure=True,
            ocr_mode="disabled",
        )


def test_startup_rejects_malformed_argon2id_hash() -> None:
    with pytest.raises(ValueError, match="AUTH_PASSWORD_HASH"):
        Settings(
            _env_file=None,
            app_env="test",
            auth_enabled=True,
            auth_username="jovi",
            auth_password_hash="$argon2id$v=19$m=not-a-number,t=3,p=4$ZmFrZQ$ZmFrZQ",
            auth_session_secret="test-session-secret-that-is-long-and-random",
            auth_cookie_secure=False,
            market_provider="mock",
        )


def test_ip_login_throttle_rejects_new_identifiers_before_password_verification(
    monkeypatch: pytest.MonkeyPatch, password_client: TestClient
) -> None:
    for _ in range(5):
        response = password_client.post("/api/auth/login", json={"identifier": "jovi", "password": "bad"})
        assert response.status_code == 401

    monkeypatch.setattr(
        AuthService,
        "authenticate",
        lambda *_args, **_kwargs: pytest.fail("rate-limited login verified a password"),
    )
    throttled = password_client.post("/api/auth/login", json={"identifier": "new-identifier", "password": "bad"})
    assert throttled.status_code == 401
    assert throttled.json() == {"detail": "登录失败，请检查凭据后重试"}


def test_forwarded_header_rotation_cannot_evade_per_ip_login_throttle(
    monkeypatch: pytest.MonkeyPatch, password_client: TestClient
) -> None:
    for index in range(5):
        response = password_client.post(
            "/api/auth/login",
            headers={"X-Forwarded-For": f"203.0.113.{index}"},
            json={"identifier": "jovi", "password": "bad"},
        )
        assert response.status_code == 401

    monkeypatch.setattr(
        AuthService,
        "authenticate",
        lambda *_args, **_kwargs: pytest.fail("spoofed header bypassed throttle"),
    )
    blocked = password_client.post(
        "/api/auth/login",
        headers={"X-Forwarded-For": "198.51.100.99"},
        json={"identifier": "new-identifier", "password": "bad"},
    )
    assert blocked.status_code == 401


def test_local_docker_template_uses_development_for_non_secure_http_cookie() -> None:
    root = __import__("pathlib").Path(__file__).resolve().parents[2]
    template = (root / "deploy" / ".env.local.docker.example").read_text(encoding="utf-8")
    quickstart = (root / "QUICKSTART.md").read_text(encoding="utf-8")
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")

    assert "APP_ENV=development" in template
    assert "AUTH_COOKIE_SECURE=false" in template
    assert "APP_ENV=development" in quickstart
    assert "APP_ENV: ${APP_ENV:-production}" in compose


def test_proxy_templates_do_not_trust_client_supplied_forwarded_for_headers() -> None:
    root = __import__("pathlib").Path(__file__).resolve().parents[2]
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    dockerfile = (root / "backend" / "Dockerfile").read_text(encoding="utf-8")
    nginx = (root / "deploy" / "nginx.conf.example").read_text(encoding="utf-8")

    assert "--proxy-headers" not in compose
    assert "--forwarded-allow-ips '*'" not in compose
    assert "--proxy-headers" not in dockerfile
    assert "--forwarded-allow-ips" not in dockerfile
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in nginx
    assert "$proxy_add_x_forwarded_for" not in nginx


def test_auth_dependencies_are_pinned_to_the_reviewed_argon2_versions() -> None:
    root = __import__("pathlib").Path(__file__).resolve().parents[2]
    project = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert '"pwdlib[argon2]==0.3.1"' in project
    assert '"argon2-cffi==25.1.0"' in project
    assert '"argon2-cffi-bindings==26.1.0"' in project


def test_deployment_handoffs_describe_database_browser_auth_without_legacy_bearer() -> None:
    root = __import__("pathlib").Path(__file__).resolve().parents[2]
    for path in (
        root / "CODEX_DEPLOYMENT_TASKS.md",
        root / "HANDOFF.md",
        root / "QUICKSTART.md",
        root / "docs" / "ALIYUN_DEPLOYMENT.md",
        root / "docs" / "LOCAL_AGENT_PROMPT_V070.md",
        root / "docs" / "QUALIFICATION_HANDOFF_V070.md",
    ):
        text = path.read_text(encoding="utf-8")
        assert "AUTH_ENABLED" in text
        assert "DATABASE_URL" in text
        assert "AUTO_CREATE_SCHEMA=false" in text
        assert "AUTH_COOKIE_SECURE=true" in text
        assert "auth-bootstrap-admin" in text
        assert "浏览器" in text


def test_auth_disabled_keeps_demo_test_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.main as main_module

    settings = Settings(_env_file=None, app_env="test", auth_enabled=False, market_provider="mock")
    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr(main_module, "settings", settings)
    try:
        with TestClient(app) as client:
            bootstrap = client.get("/api/bootstrap")
            assert bootstrap.status_code == 200
            # Offline/single-user mode retains the legacy shared operational
            # dashboard.  Member filtering is only an enrolled-user boundary.
            assert "tasks" in bootstrap.json()
            assert "provider_health" in bootstrap.json()
            assert client.get("/api/auth/me").json() == {"authenticated": True, "identifier": None, "role": None}
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_static_login_uses_cookies_and_never_persists_access_tokens() -> None:
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    html = (root / "app" / "static" / "index.html").read_text(encoding="utf-8")
    script = (root / "app" / "static" / "app.js").read_text(encoding="utf-8")

    assert "fundDecisionToken" not in script
    assert "PRIVATE_ACCESS_TOKEN" not in html
    assert "credentials:'same-origin'" in script
    assert "X-CSRF-Token" in script
    generator = root.parent / "scripts" / "generate_password_hash.py"
    assert "getpass.getpass" in generator.read_text(encoding="utf-8")


def test_static_account_management_is_identity_aware_and_admin_only() -> None:
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    html = (root / "app" / "static" / "index.html").read_text(encoding="utf-8")
    script = (root / "app" / "static" / "app.js").read_text(encoding="utf-8")

    for marker in (
        'id="accountIdentity"',
        'id="adminAccountsPanel"',
        'id="adminCreateForm"',
        'id="adminResetPasswordForm"',
        'type="password"',
        'id="adminAccountStatus"',
    ):
        assert marker in html
    for marker in (
        "refreshAuthIdentity",
        "isEnrolledAdmin",
        "loadAdminUsers",
        "/api/admin/users",
        "renderAdminAccounts",
        "activeAdminCount",
        "selfDisable",
        "当前账户已停用，登录会话已失效。",
    ):
        assert marker in script
    assert "password_hash" not in html
    assert "password_hash" not in script
