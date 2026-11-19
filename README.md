# homelab-mcp

A small, **read-only** [MCP](https://modelcontextprotocol.io) server that gives an AI agent (here:
[Hermes Agent](https://hermes-agent.nousresearch.com)) real numbers about a homelab server, measured by Prometheus,
so it never has to guess them.

> Code collects the facts; the AI only explains them.

## Architecture

```
Discord ─► Hermes (container) ──mcp_internal (internal)──► homelab-mcp (container) ──mcp_prom──► Prometheus (host :9090)
             │ br-hermes: internet only                         no internet, no host except :9090      │
             ✗ host services, other containers                                                          ▼
                                                                    node-exporter ◄── textfile collector ◄── host cron
                                                                    (CPU, RAM, disk, load)    (containers, apt, reboot, backup age)
```

## Tools (all read-only, fixed PromQL)

No tool accepts PromQL. Inputs are enums or bounded integers, validated by the MCP SDK before a tool runs; queries are
built only from templates in [`src/homelab_mcp/queries.py`](src/homelab_mcp/queries.py).

| Tool | Inputs | Returns |
|---|---|---|
| `host_summary` | none | CPU %, RAM %, root disk % (df formula), load 1/5/15, cores, uptime, pending apt (all/security), reboot required, last backup age |
| `disk_trend` | `days` 1–14 (default 7) | root disk % now vs then, change, days until full (`deriv`), or "not filling" |
| `resource_trend` | `metric` cpu/ram/load1, `hours` 1/6/24/168 | min / avg / max over the window |
| `targets_status` | none | Prometheus scrape targets up/down, textfile collector errors |
| `container_status` | `hours` 24/168 | containers not running, crash restarts, (re)started in window, unhealthy, data age |
| `service_checks` | none | Uptime Kuma monitors down/pending/maintenance, certificates expiring < 14 days |

Every result includes `as_of`; missing data is `null`, never a guess.

## Security model

| Layer | Control |
|---|---|
| Inputs | No raw PromQL; enums and bounded ints only; only `GET /api/v1/query` is ever called |
| Auth | `Authorization: Bearer <HOMELAB_MCP_TOKEN>` on every request (constant-time compare); refuses to start with a missing, placeholder or < 32-char token |
| HTTP | MCP SDK DNS-rebinding protection: only `Host: homelab-mcp:8000` |
| Container | non-root (10001), `read_only` + 16 MB `noexec` tmpfs, `cap_drop: ALL`, `no-new-privileges`, 64 pids, 128 MB RAM, 0.25 CPU, **no published ports**, no Docker socket, no host mounts |
| Supply chain | base image pinned by digest (`python:3.13-slim@sha256:e48f59cdba69…`); every dependency hash-locked (`pip install --require-hashes --no-deps`) |
| Network | `mcp_internal` is `internal: true`; host firewall ([`host/homelab-isolation.nft`](host/homelab-isolation.nft)) blocks Hermes from all host services and other containers, lets homelab-mcp reach only Prometheus :9090, no internet |

## Layout

```
src/homelab_mcp/   queries.py (PromQL templates) · prometheus.py (client) · tools.py · server.py · app.py (auth, HTTP)
tests/             query validation, tool logic against a fake Prometheus, auth + MCP handshake
host/              textfile-metrics.sh (cron) · node-exporter.compose.yaml · homelab-isolation.nft + .service
```

## Run

```bash
cp .env.example .env && chmod 600 .env          # set HOMELAB_MCP_TOKEN (same value in the agent's .env)
docker build --target test .                     # runs the test suite; the build fails if a test fails
docker compose up -d --build
```

Agent side (Hermes `config.yaml`):

```yaml
mcp_servers:
  homelab:
    url: http://homelab-mcp:8000/mcp
    headers: { Authorization: "Bearer ${HOMELAB_MCP_TOKEN}" }
    tools: { include: [host_summary, disk_trend, resource_trend, targets_status, container_status, service_checks] }
```

## Host side

- `host/textfile-metrics.sh`, every 5 min from cron: per-container running / restart count / health / start time;
  hourly: pending apt upgrades (simulated) and reboot-required. Written atomically for node-exporter's textfile collector.
- `host/node-exporter.compose.yaml`: node-exporter pinned by digest, textfile directory mounted read-only.
- `host/homelab-isolation.nft` + `.service`: an own nftables table (never touches Docker's or Tailscale's rules),
  loaded at boot after Docker.

## Updating dependencies

```bash
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/src -w /src python:3.13-slim \
  sh -c 'pip install -q --user uv && ~/.local/bin/uv pip compile --generate-hashes --python-version 3.13 \
         --python-platform x86_64-unknown-linux-gnu -o requirements.txt requirements.in'
```

Then rebuild with `--target test` before deploying.
