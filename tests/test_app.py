from starlette.testclient import TestClient

from homelab_mcp.app import build_app

TOKEN = "t" * 40
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}}


def client(base_url="http://homelab-mcp:8000"):
    return TestClient(build_app(TOKEN, "http://prom.test:9090", ["homelab-mcp:8000"]), base_url=base_url)


def test_requests_without_or_with_wrong_token_are_rejected():
    with client() as c:
        assert c.post("/mcp", json=INIT, headers=MCP_HEADERS).status_code == 401
        bad = {**MCP_HEADERS, "Authorization": "Bearer " + "x" * 40}
        assert c.post("/mcp", json=INIT, headers=bad).status_code == 401


def test_wrong_host_header_is_refused_even_with_token():
    with client("http://evil.example") as c:
        r = c.post("/mcp", json=INIT, headers={**MCP_HEADERS, "Authorization": f"Bearer {TOKEN}"})
        assert r.status_code in (400, 403, 421)


def test_authorized_client_sees_exactly_the_six_read_only_tools():
    auth = {**MCP_HEADERS, "Authorization": f"Bearer {TOKEN}"}
    with client() as c:
        init = c.post("/mcp", json=INIT, headers=auth)
        assert init.status_code == 200
        version = init.json()["result"]["protocolVersion"]
        listed = c.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                        headers={**auth, "MCP-Protocol-Version": version})
        assert listed.status_code == 200
        tools = listed.json()["result"]["tools"]
        assert sorted(t["name"] for t in tools) == sorted(
            ["host_summary", "disk_trend", "resource_trend", "targets_status", "container_status", "service_checks"])
        assert all(t["annotations"]["readOnlyHint"] for t in tools)
