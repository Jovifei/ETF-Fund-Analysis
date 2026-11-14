"""Direct navigation must serve the independent research SPA, not a 404."""
from types import SimpleNamespace

from fastapi.testclient import TestClient
from starlette.applications import Starlette

from app.workspace import ui


def test_us_markets_direct_navigation_serves_spa_without_catchall(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<html>isolated research SPA</html>", encoding="utf-8")
    monkeypatch.setattr(ui, "DIST", tmp_path)
    monkeypatch.setattr(ui, "workspace_settings", lambda: SimpleNamespace(ui_enabled=True))
    with TestClient(ui.WorkspaceMiddleware(Starlette())) as client:
        for path in ("/", "/research/us-markets"):
            response = client.get(path)
            assert response.status_code == 200
            assert "isolated research SPA" in response.text
        assert client.get("/research/not-a-real-page").status_code == 404
        assert client.get("/api/workspace/not-a-real-api").status_code == 404
