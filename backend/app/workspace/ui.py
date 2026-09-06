"""Exact-route Vue rollout and bounded bodies, not a catch-all SPA fallback."""
from __future__ import annotations

import re
from pathlib import Path

from starlette.responses import FileResponse, JSONResponse

from app.workspace.config import workspace_settings

DIST = Path(__file__).resolve().parents[1] / "workspace_dist"
UI_PATHS = frozenset({"/", "/boards", "/analysis", "/watchlist", "/holdings", "/ai", "/research", "/research/news", "/review", "/factors", "/history", "/settings", "/profile", "/system", "/decision/1430"})


class WorkspaceMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path, method = scope.get("path", ""), scope.get("method", "GET")
        protected_response = path.startswith(("/api/workspace/", "/api/bridge/", "/api/search/"))

        async def private_send(message):
            if protected_response and message["type"] == "http.response.start":
                message = {**message, "headers": [(key, value) for key, value in message.get("headers", []) if key.lower() != b"cache-control"] + [(b"cache-control", b"private, no-store")]}
            await send(message)

        if protected_response and method in {"POST", "PUT", "PATCH"}:
            content = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                content.extend(message.get("body", b""))
                if len(content) > 5_000_000:
                    await JSONResponse({"detail": "request exceeds workspace limit"}, 413)(scope, receive, private_send)
                    return
                if not message.get("more_body", False):
                    break
            original_receive = receive
            consumed = False

            async def replay():
                nonlocal consumed
                if not consumed:
                    consumed = True
                    return {"type": "http.request", "body": bytes(content), "more_body": False}
                return await original_receive()

            receive = replay
        if method in {"GET", "HEAD"} and path.startswith("/workspace-assets/"):
            root = DIST / "workspace-assets"
            candidate = (root / path.removeprefix("/workspace-assets/")).resolve()
            try:
                candidate.relative_to(root.resolve())
                if not candidate.is_file():
                    raise ValueError("missing")
            except (ValueError, OSError):
                await JSONResponse({"detail": "asset not found"}, 404)(scope, receive, private_send)
                return
            await FileResponse(candidate, headers={"Cache-Control": "public, max-age=31536000, immutable"})(scope, receive, private_send)
            return
        if method in {"GET", "HEAD"} and workspace_settings().ui_enabled and (path in UI_PATHS or re.fullmatch(r"/etf/\d{6}\.(SH|SZ|BJ)", path)):
            entry = DIST / "index.html"
            if not entry.is_file():
                await JSONResponse({"detail": "Vue build missing; run npm ci and npm run build in frontend, or disable WORKSPACE_UI_ENABLED"}, 503)(scope, receive, private_send)
                return
            await FileResponse(entry, media_type="text/html", headers={"Cache-Control": "no-cache"})(scope, receive, private_send)
            return
        await self.app(scope, receive, private_send)
