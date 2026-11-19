"""Minimal Prometheus client: only GET /api/v1/query (instant queries). Nothing else is reachable."""

import math
from dataclasses import dataclass

import httpx


class PrometheusError(RuntimeError):
    pass


@dataclass(frozen=True)
class Sample:
    labels: dict[str, str]
    value: float


class Prometheus:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None, timeout: float = 10.0):
        self._url = base_url.rstrip("/") + "/api/v1/query"
        self._client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=False)

    async def query(self, promql: str) -> list[Sample]:
        try:
            r = await self._client.get(self._url, params={"query": promql})
            body = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise PrometheusError(f"Prometheus unreachable: {type(exc).__name__}") from exc
        if r.status_code != 200 or body.get("status") != "success":
            raise PrometheusError(f"Prometheus error: {body.get('error', r.status_code)}")
        data = body["data"]
        if data["resultType"] == "scalar":
            return [Sample({}, float(data["result"][1]))]
        return [Sample(item.get("metric", {}), float(item["value"][1])) for item in data["result"]]

    async def scalar(self, promql: str) -> float | None:
        """First value of a query, or None when there is no data (or it isn't a finite number)."""
        samples = await self.query(promql)
        if not samples or not math.isfinite(samples[0].value):
            return None
        return samples[0].value
