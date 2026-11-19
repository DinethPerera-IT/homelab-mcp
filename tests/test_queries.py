import pytest

from homelab_mcp import queries as q


def test_disk_used_matches_df_formula_and_offsets_every_selector():
    assert "offset" not in q.disk_used_pct()
    shifted = q.disk_used_pct(7)
    assert shifted.count(" offset 7d") == shifted.count("_bytes{") == 5


@pytest.mark.parametrize("bad", [0, 15, -1, True, "7", 7.0])
def test_days_to_full_rejects_out_of_range_or_non_int(bad):
    with pytest.raises(ValueError):
        q.disk_days_to_full(bad)


@pytest.mark.parametrize("metric,hours,fn", [("up", 24, "max"), ("cpu", 2, "max"), ("cpu", 24, "rate"),
                                             ('cpu"}) or vector(1', 24, "max")])
def test_trend_only_builds_known_queries(metric, hours, fn):
    with pytest.raises(ValueError):
        q.trend(metric, hours, fn)


def test_container_restarts_window_is_fixed():
    assert q.container_restarts(24) == "increase(homelab_container_restart_count[24h])"
    with pytest.raises(ValueError):
        q.container_restarts(25)
