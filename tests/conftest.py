import httpx
import pytest

from homelab_mcp.prometheus import Prometheus


@pytest.fixture
def anyio_backend():
    return "asyncio"


def fake_prometheus(answers: dict[str, list[tuple[dict, float]]], fail: bool = False) -> Prometheus:
    """Prometheus double: maps an exact PromQL string to vector samples; unknown queries return no data."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/query", "only instant queries are allowed"
        if fail:
            raise httpx.ConnectError("down")
        result = [{"metric": labels, "value": [0, str(value)]}
                  for labels, value in answers.get(request.url.params["query"], [])]
        return httpx.Response(200, json={"status": "success", "data": {"resultType": "vector", "result": result}})

    return Prometheus("http://prom.test:9090", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
