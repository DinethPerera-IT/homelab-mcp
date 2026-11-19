"""Registers the six tools with the MCP SDK. Input types (Literal enums, bounded ints) are validated by
the SDK before any tool runs; every tool is marked read-only."""

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from homelab_mcp import __version__, tools
from homelab_mcp.prometheus import Prometheus
from homelab_mcp.queries import RestartHours, TrendHours, TrendMetric

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True,
                            open_world_hint=False)

INSTRUCTIONS = (
    "Read-only facts about Dina's homelab server, measured by Prometheus. Report the numbers these tools "
    "return; never estimate them. A null value means no data: say so instead of guessing."
)


def build_server(prom: Prometheus) -> MCPServer:
    server = MCPServer(name="homelab-mcp", version=__version__, instructions=INSTRUCTIONS)

    @server.tool(annotations=READ_ONLY)
    async def host_summary() -> dict:
        """Current CPU, RAM, root disk use, load, uptime, pending apt updates, reboot needed, backup age."""
        return await tools.host_summary(prom)

    @server.tool(annotations=READ_ONLY)
    async def disk_trend(days: Annotated[int, Field(ge=1, le=14)] = 7) -> dict:
        """Root disk use now vs `days` ago, the change, and days until full at that rate."""
        return await tools.disk_trend(prom, days)

    @server.tool(annotations=READ_ONLY)
    async def resource_trend(metric: TrendMetric, hours: TrendHours = 24) -> dict:
        """Min, average and max of cpu (%), ram (%) or load1 over the last 1, 6, 24 or 168 hours."""
        return await tools.resource_trend(prom, metric, hours)

    @server.tool(annotations=READ_ONLY)
    async def targets_status() -> dict:
        """Which Prometheus scrape targets are up or down."""
        return await tools.targets_status(prom)

    @server.tool(annotations=READ_ONLY)
    async def container_status(hours: RestartHours = 24) -> dict:
        """Docker containers: not running, crash restarts, (re)started in the window, unhealthy."""
        return await tools.container_status(prom, hours)

    @server.tool(annotations=READ_ONLY)
    async def service_checks() -> dict:
        """Uptime Kuma monitors that are down, pending or in maintenance, and certificates expiring soon."""
        return await tools.service_checks(prom)

    return server
