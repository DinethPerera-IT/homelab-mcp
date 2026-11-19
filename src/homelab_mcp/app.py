"""HTTP entry point: MCP over streamable HTTP, behind a bearer token and DNS-rebinding protection."""

import hmac
import json
import os
import sys

import uvicorn
from mcp.server.transport_security import TransportSecuritySettings

from homelab_mcp.prometheus import Prometheus
from homelab_mcp.server import build_server

MIN_TOKEN_LENGTH = 32


class BearerAuth:
    """ASGI middleware: every HTTP request needs `Authorization: Bearer <token>` (constant-time compare)."""

    def __init__(self, app, token: str):
        self._app = app
        self._expected = f"Bearer {token}".encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            given = dict(scope.get("headers") or []).get(b"authorization", b"")
            if not hmac.compare_digest(given, self._expected):
                body = json.dumps({"error": "unauthorized"}).encode()
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"application/json"),
                                        (b"www-authenticate", b"Bearer")]})
                await send({"type": "http.response.body", "body": body})
                return
        await self._app(scope, receive, send)


def build_app(token: str, prometheus_url: str, allowed_hosts: list[str]):
    server = build_server(Prometheus(prometheus_url))
    security = TransportSecuritySettings(enable_dns_rebinding_protection=True,
                                         allowed_hosts=allowed_hosts, allowed_origins=[])
    inner = server.streamable_http_app(json_response=True, stateless_http=True, transport_security=security)
    return BearerAuth(inner, token)


def _config() -> tuple[str, str, list[str], str, int]:
    token = os.environ.get("HOMELAB_MCP_TOKEN", "")
    if len(token) < MIN_TOKEN_LENGTH or token.upper().startswith("CHANGE"):
        sys.exit(f"HOMELAB_MCP_TOKEN missing, a placeholder, or shorter than {MIN_TOKEN_LENGTH} characters: "
                 "refusing to start.")
    prometheus_url = os.environ.get("PROMETHEUS_URL", "")
    if not prometheus_url.startswith(("http://", "https://")):
        sys.exit("PROMETHEUS_URL must be an http(s) URL.")
    hosts = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "homelab-mcp:8000").split(",") if h.strip()]
    return token, prometheus_url, hosts, os.environ.get("BIND_HOST", "0.0.0.0"), int(os.environ.get("PORT", "8000"))


def main() -> None:
    token, prometheus_url, hosts, bind, port = _config()
    app = build_app(token, prometheus_url, hosts)
    uvicorn.run(app, host=bind, port=port, server_header=False, date_header=False, proxy_headers=False,
                log_level="info")
