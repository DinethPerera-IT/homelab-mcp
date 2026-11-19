import pytest

from homelab_mcp import queries as q
from homelab_mcp import tools
from homelab_mcp.prometheus import PrometheusError
from tests.conftest import fake_prometheus

pytestmark = pytest.mark.anyio


async def test_host_summary_rounds_and_reports_missing_data_as_null():
    prom = fake_prometheus({q.CPU_PCT: [({}, 12.345)], q.disk_used_pct(): [({}, 37.44)], q.UPTIME_S: [({}, 172800)],
                            q.REBOOT_REQUIRED: [({}, 1)], q.BACKUP_AGE_S: [({}, 5400)]})
    r = await tools.host_summary(prom)
    assert r["cpu_used_pct"] == 12.3 and r["disk_root_used_pct"] == 37.4 and r["uptime_days"] == 2.0
    assert r["ram_used_pct"] is None
    assert r["maintenance"]["reboot_required"] is True and r["maintenance"]["last_backup_age_hours"] == 1.5


async def test_disk_trend_filling_and_not_filling():
    filling = fake_prometheus({q.disk_used_pct(): [({}, 40)], q.disk_used_pct(7): [({}, 38)],
                               q.disk_days_to_full(7): [({}, 210.4)]})
    r = await tools.disk_trend(filling, 7)
    assert r["change_pct_points"] == 2 and r["days_until_full"] == 210.4 and r["filling"] is True
    shrinking = fake_prometheus({q.disk_days_to_full(7): [({}, -50)]})
    r = await tools.disk_trend(shrinking, 7)
    assert r["days_until_full"] is None and r["filling"] is False


async def test_container_status_reports_problems_only():
    prom = fake_prometheus({
        q.CONTAINER_RUNNING: [({"name": "a"}, 1), ({"name": "b"}, 0)],
        q.container_restarts(24): [({"name": "a"}, 0), ({"name": "c"}, 2.4)],
        q.CONTAINER_STARTED_AGO_S: [({"name": "a"}, 600), ({"name": "b"}, 999999)],
        q.CONTAINER_UNHEALTHY: [({"name": "c", "status": "unhealthy"}, 1)],
    })
    r = await tools.container_status(prom, 24)
    assert r["not_running"] == ["b"] and r["crash_restarts"] == {"c": 3}
    assert r["started_in_window"] == ["a"] and r["unhealthy"] == {"c": "unhealthy"}


async def test_container_and_service_checks_say_when_there_is_no_data():
    prom = fake_prometheus({})
    assert (await tools.container_status(prom, 24))["available"] is False
    assert (await tools.service_checks(prom))["available"] is False


async def test_service_checks_groups_monitors():
    prom = fake_prometheus({q.KUMA_STATUS: [({"monitor_name": "grafana"}, 1), ({"monitor_name": "pihole"}, 0)],
                            q.KUMA_CERT_DAYS: [({"monitor_name": "site"}, 9), ({"monitor_name": "ok"}, 60)]})
    r = await tools.service_checks(prom)
    assert r["down"] == ["pihole"] and r["up_count"] == 1 and r["certs_expiring_14d"] == {"site": 9}


async def test_unreachable_prometheus_is_an_error_not_a_guess():
    with pytest.raises(PrometheusError):
        await tools.host_summary(fake_prometheus({}, fail=True))
