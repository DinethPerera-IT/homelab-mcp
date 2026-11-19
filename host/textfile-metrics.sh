#!/bin/sh
# Host-side facts for node-exporter's textfile collector (read by homelab-mcp through Prometheus).
# Runs from the host crontab every 5 minutes. Read-only: docker inspect, apt-get --simulate, a file check.
#   homelab_containers.prom  every run:  running, restart count, health, start time per container
#   homelab_apt.prom         hourly:     pending apt upgrades (all / security), reboot required
set -eu
DIR="/var/lib/node_exporter/textfile"
now=$(date +%s)

write() {   # $1 = file name; metrics on stdin. Atomic: node-exporter never sees a half-written file.
    cat > "$DIR/.$1.tmp" && chmod 644 "$DIR/.$1.tmp" && mv "$DIR/.$1.tmp" "$DIR/$1"
}

ids=$(docker ps -aq)
{
    echo "# HELP homelab_container_running 1 if the container is running. restart_policy=no means stopping it is expected."
    echo "# TYPE homelab_container_running gauge"
    echo "# HELP homelab_container_restart_count Docker restart count (restarts by the restart policy, e.g. crash loops)."
    echo "# TYPE homelab_container_restart_count gauge"
    echo "# HELP homelab_container_started_timestamp_seconds When the container last started (catches manual restarts/recreates)."
    echo "# TYPE homelab_container_started_timestamp_seconds gauge"
    echo "# HELP homelab_container_health 1 for the container's current health status."
    echo "# TYPE homelab_container_health gauge"
    if [ -n "$ids" ]; then
        docker inspect --format '{{.Name}} {{.State.Running}} {{.RestartCount}} {{.State.StartedAt}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} {{.HostConfig.RestartPolicy.Name}}' $ids |
        while read -r name running restarts started health policy; do
            name=${name#/}
            [ "$running" = "true" ] && r=1 || r=0
            ts=$(date -d "$started" +%s 2>/dev/null || echo 0)
            echo "homelab_container_running{name=\"$name\",restart_policy=\"${policy:-no}\"} $r"
            echo "homelab_container_restart_count{name=\"$name\"} $restarts"
            echo "homelab_container_started_timestamp_seconds{name=\"$name\"} $ts"
            echo "homelab_container_health{name=\"$name\",status=\"$health\"} 1"
        done
    fi
    echo "# HELP homelab_textfile_containers_timestamp_seconds When this file was written."
    echo "# TYPE homelab_textfile_containers_timestamp_seconds gauge"
    echo "homelab_textfile_containers_timestamp_seconds $now"
} | write homelab_containers.prom

apt_file="$DIR/homelab_apt.prom"
if [ ! -f "$apt_file" ] || [ $((now - $(stat -c %Y "$apt_file"))) -ge 3300 ]; then
    sim=$(apt-get -s -o Debug::NoLocking=1 dist-upgrade 2>/dev/null | grep '^Inst ' || true)
    total=$(printf '%s' "$sim" | grep -c '^Inst ' || true)
    security=$(printf '%s\n' "$sim" | grep -ci 'security' || true)
    [ -f /var/run/reboot-required ] && reboot=1 || reboot=0
    printf '%s\n' \
        "# HELP homelab_apt_upgradable Packages with an upgrade available (apt-get --simulate dist-upgrade)." \
        "# TYPE homelab_apt_upgradable gauge" \
        "homelab_apt_upgradable $total" \
        "# HELP homelab_apt_security_upgradable Upgradable packages from a security pocket." \
        "# TYPE homelab_apt_security_upgradable gauge" \
        "homelab_apt_security_upgradable $security" \
        "# HELP homelab_reboot_required 1 if /var/run/reboot-required exists." \
        "# TYPE homelab_reboot_required gauge" \
        "homelab_reboot_required $reboot" \
        "# HELP homelab_textfile_apt_timestamp_seconds When the apt check last ran." \
        "# TYPE homelab_textfile_apt_timestamp_seconds gauge" \
        "homelab_textfile_apt_timestamp_seconds $now" | write homelab_apt.prom
fi
