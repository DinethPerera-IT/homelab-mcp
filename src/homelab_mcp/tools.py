"""The six read-only tools. Each runs fixed queries from queries.py and returns small, rounded results
plus `as_of`, so the agent reports measured numbers instead of guessing them."""

import asyncio
import math
from datetime import datetime, timezone

from homelab_mcp import queries as q
from homelab_mcp.prometheus import Prometheus

KUMA_STATUS_NAMES = {0: "down", 1: "up", 2: "pending", 3: "maintenance"}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _r(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


async def _scalars(prom: Prometheus, named: dict[str, str]) -> dict[str, float | None]:
    values = await asyncio.gather(*(prom.scalar(query) for query in named.values()))
    return dict(zip(named, values))


async def host_summary(prom: Prometheus) -> dict:
    v = await _scalars(prom, {
        "cpu": q.CPU_PCT, "ram": q.RAM_PCT, "disk": q.disk_used_pct(), "load1": q.LOAD1, "load5": q.LOAD5,
        "load15": q.LOAD15, "cores": q.CPU_CORES, "uptime": q.UPTIME_S, "apt": q.APT_UPGRADABLE,
        "apt_sec": q.APT_SECURITY, "reboot": q.REBOOT_REQUIRED, "backup_age": q.BACKUP_AGE_S,
    })
    return {
        "as_of": _now(),
        "cpu_used_pct": _r(v["cpu"]), "ram_used_pct": _r(v["ram"]), "disk_root_used_pct": _r(v["disk"]),
        "load": {"1m": _r(v["load1"], 2), "5m": _r(v["load5"], 2), "15m": _r(v["load15"], 2)},
        "cpu_cores": None if v["cores"] is None else int(v["cores"]),
        "uptime_days": _r(None if v["uptime"] is None else v["uptime"] / 86400),
        "maintenance": {
            "apt_upgradable": None if v["apt"] is None else int(v["apt"]),
            "apt_security_upgradable": None if v["apt_sec"] is None else int(v["apt_sec"]),
            "reboot_required": None if v["reboot"] is None else bool(v["reboot"]),
            "last_backup_age_hours": _r(None if v["backup_age"] is None else v["backup_age"] / 3600),
        },
    }


async def disk_trend(prom: Prometheus, days: int) -> dict:
    v = await _scalars(prom, {
        "now": q.disk_used_pct(), "then": q.disk_used_pct(days), "to_full": q.disk_days_to_full(days),
    })
    change = None if v["now"] is None or v["then"] is None else v["now"] - v["then"]
    to_full = v["to_full"] if v["to_full"] is not None and v["to_full"] > 0 else None
    return {
        "as_of": _now(), "window_days": days,
        "disk_root_used_pct_now": _r(v["now"]), "disk_root_used_pct_then": _r(v["then"]),
        "change_pct_points": _r(change, 2),
        "days_until_full": _r(to_full) if to_full is not None and to_full < 36500 else None,
        "filling": to_full is not None,
    }


async def resource_trend(prom: Prometheus, metric: str, hours: int) -> dict:
    v = await _scalars(prom, {fn: q.trend(metric, hours, fn) for fn in ("min", "avg", "max")})
    digits = 2 if metric == "load1" else 1
    unit = "load" if metric == "load1" else "pct"
    return {"as_of": _now(), "metric": metric, "window_hours": hours, "unit": unit,
            "min": _r(v["min"], digits), "avg": _r(v["avg"], digits), "max": _r(v["max"], digits)}


async def targets_status(prom: Prometheus) -> dict:
    up, textfile_err = await asyncio.gather(prom.query(q.TARGETS_UP), prom.scalar(q.TEXTFILE_SCRAPE_ERROR))
    targets = [{"job": s.labels.get("job", "?"), "instance": s.labels.get("instance", "?"), "up": s.value == 1}
               for s in up]
    return {"as_of": _now(), "targets_total": len(targets), "targets_down": [t for t in targets if not t["up"]],
            "targets": targets, "textfile_scrape_error": None if textfile_err is None else bool(textfile_err)}


async def container_status(prom: Prometheus, hours: int) -> dict:
    running, restarts, started_ago, unhealthy, data_age = await asyncio.gather(
        prom.query(q.CONTAINER_RUNNING), prom.query(q.container_restarts(hours)),
        prom.query(q.CONTAINER_STARTED_AGO_S), prom.query(q.CONTAINER_UNHEALTHY),
        prom.scalar(q.CONTAINER_DATA_AGE_S))
    if not running:
        return {"as_of": _now(), "available": False,
                "note": "No container metrics in Prometheus (host/textfile-metrics.sh not running?)."}
    window_s = hours * 3600
    return {
        "as_of": _now(), "available": True, "window_hours": hours,
        "containers_total": len(running),
        # Only containers meant to stay up (restart policy always/unless-stopped/on-failure) count as a problem;
        # restart_policy=no containers (one-off `docker run`s, kept rollbacks) are stopped on purpose.
        "not_running": sorted(s.labels["name"] for s in running if s.value != 1 and s.labels.get("restart_policy") != "no"),
        "stopped_on_purpose": sum(1 for s in running if s.value != 1 and s.labels.get("restart_policy") == "no"),
        "crash_restarts": {s.labels["name"]: math.ceil(s.value) for s in restarts if s.value > 0},
        "started_in_window": sorted(s.labels["name"] for s in started_ago if 0 <= s.value < window_s),
        "unhealthy": {s.labels["name"]: s.labels.get("status", "?") for s in unhealthy},
        "data_age_minutes": _r(None if data_age is None else data_age / 60),
    }


async def service_checks(prom: Prometheus) -> dict:
    status, certs = await asyncio.gather(prom.query(q.KUMA_STATUS), prom.query(q.KUMA_CERT_DAYS))
    if not status:
        return {"as_of": _now(), "available": False,
                "note": "Uptime Kuma isn't scraped by Prometheus yet, so there are no service checks."}
    by_state: dict[str, list[str]] = {name: [] for name in KUMA_STATUS_NAMES.values()}
    for s in status:
        by_state[KUMA_STATUS_NAMES.get(int(s.value), "unknown")].append(s.labels.get("monitor_name", "?"))
    return {
        "as_of": _now(), "available": True, "monitors_total": len(status),
        "down": sorted(by_state["down"]), "pending": sorted(by_state["pending"]),
        "maintenance": sorted(by_state["maintenance"]), "up_count": len(by_state["up"]),
        "certs_expiring_14d": {s.labels.get("monitor_name", "?"): int(s.value) for s in certs if 0 <= s.value < 14},
    }
