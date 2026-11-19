"""Every PromQL query homelab-mcp can run. No tool accepts PromQL: tool inputs are enums or bounded
integers (validated by the MCP SDK before a tool runs), and queries are built only from these templates."""

from typing import Literal

ROOT_FS = 'mountpoint="/",fstype="ext4"'

# host
CPU_PCT = '100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))'
RAM_PCT = "100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)"
LOAD1, LOAD5, LOAD15 = "node_load1", "node_load5", "node_load15"
CPU_CORES = 'count(node_cpu_seconds_total{mode="idle"})'
UPTIME_S = "node_time_seconds - node_boot_time_seconds"

# host facts from the textfile collector (host/textfile-metrics.sh, hermes data-backup.sh)
APT_UPGRADABLE = "homelab_apt_upgradable"
APT_SECURITY = "homelab_apt_security_upgradable"
REBOOT_REQUIRED = "homelab_reboot_required"
BACKUP_AGE_S = "time() - homelab_last_backup_timestamp_seconds"

# scrape targets
TARGETS_UP = "up"
TEXTFILE_SCRAPE_ERROR = "node_textfile_scrape_error"

# containers (textfile collector)
CONTAINER_RUNNING = "homelab_container_running"
CONTAINER_STARTED_AGO_S = "time() - homelab_container_started_timestamp_seconds"
CONTAINER_UNHEALTHY = 'homelab_container_health{status!~"healthy|none"}'
CONTAINER_DATA_AGE_S = "time() - homelab_textfile_containers_timestamp_seconds"

# Uptime Kuma (only once Prometheus scrapes Kuma's /metrics)
KUMA_STATUS = "monitor_status"
KUMA_CERT_DAYS = "monitor_cert_days_remaining"

TrendMetric = Literal["cpu", "ram", "load1"]
TrendHours = Literal[1, 6, 24, 168]
RestartHours = Literal[24, 168]
_TREND_EXPR = {"cpu": CPU_PCT, "ram": RAM_PCT, "load1": LOAD1}
MAX_TREND_DAYS = 14  # Prometheus keeps 15 days


def disk_used_pct(offset_days: int = 0) -> str:
    """Root filesystem used %, same formula as `df` (blocks reserved for root don't count as usable)."""
    _check_days(offset_days, allow_zero=True)
    off = f" offset {offset_days}d" if offset_days else ""
    size = f"node_filesystem_size_bytes{{{ROOT_FS}}}{off}"
    free = f"node_filesystem_free_bytes{{{ROOT_FS}}}{off}"
    avail = f"node_filesystem_avail_bytes{{{ROOT_FS}}}{off}"
    return f"100 * ({size} - {free}) / ({size} - {free} + {avail})"


def disk_days_to_full(days: int) -> str:
    """Days until the root filesystem is full at the linear rate of the last `days` days."""
    _check_days(days)
    avail = f"node_filesystem_avail_bytes{{{ROOT_FS}}}"
    return f"{avail} / -deriv({avail}[{days}d]) / 86400"


def trend(metric: str, hours: int, fn: str) -> str:
    if metric not in _TREND_EXPR or hours not in (1, 6, 24, 168) or fn not in ("min", "avg", "max"):
        raise ValueError("unsupported trend query")
    return f"{fn}_over_time(({_TREND_EXPR[metric]})[{hours}h:5m])"


def container_restarts(hours: int) -> str:
    if hours not in (24, 168):
        raise ValueError("hours must be 24 or 168")
    return f"increase(homelab_container_restart_count[{hours}h])"


def _check_days(days: int, allow_zero: bool = False) -> None:
    low = 0 if allow_zero else 1
    if not isinstance(days, int) or isinstance(days, bool) or not low <= days <= MAX_TREND_DAYS:
        raise ValueError(f"days must be an integer from {low} to {MAX_TREND_DAYS}")
