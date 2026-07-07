#!/usr/bin/env bash
# =============================================================================
# Standalone safety-net for the wedging remote Swarm dispatcher (v4).
#
# The runner already self-heals a wedge INSIDE each run (bench/runner.py
# `_ensure_service_scheduled`). This is a belt-and-suspenders watchdog for the
# cases the in-run heal can't cover (the harness itself stuck, a wedge between
# runs, etc.). Run it in a SECOND screen on the load host (101) alongside a
# campaign; it restarts docker on the app host when the scalable service is
# scheduled but nothing is actually running.
#
#   # on 101, next to `RUN_TAG=... ./xp.sh start ...`
#   screen -dmS soy-watchdog ./tools/swarm_watchdog.sh
#   screen -r soy-watchdog          # watch it   |   screen -S soy-watchdog -X quit  # stop
#
# Detection: `<stack>_<svc>` has desired-state=running tasks (>0) BUT 0 running
# containers, for STRIKES consecutive polls → wedged → `ssh <APP_HOST> restart docker`.
# A COOLDOWN after each restart avoids thrashing while the daemon comes back.
#
# Config (env, all optional — sourced from config.env if present):
#   STACK=soy_v4  SVC=node  APP_HOST=192.168.3.102  DOCKER_HOST=tcp://...:2375
#   INTERVAL=30   STRIKES=3   COOLDOWN=180
#   RESTART_CMD='sudo systemctl restart docker'   APP_SSH=$APP_HOST
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.."
[ -f config.env ] && . ./config.env

STACK="${STACK:-soy_v4}"
SVC="${SVC:-node}"
APP_SSH="${SOY_APP_SSH:-${APP_HOST:-192.168.3.102}}"
RESTART_CMD="${SOY_DOCKER_RESTART_CMD:-sudo systemctl restart docker}"
INTERVAL="${INTERVAL:-30}"     # seconds between polls
STRIKES="${STRIKES:-3}"        # consecutive wedged polls before acting
COOLDOWN="${COOLDOWN:-180}"    # seconds to wait after a restart

full="${STACK}_${SVC}"
strikes=0
echo "[watchdog] guarding ${full} on docker=${DOCKER_HOST:-local} (ssh ${APP_SSH})"
echo "[watchdog] interval=${INTERVAL}s strikes=${STRIKES} cooldown=${COOLDOWN}s cmd='${RESTART_CMD}'"

_desired() { docker service ps "$full" --filter desired-state=running -q 2>/dev/null | grep -c . ; }
_running() { docker ps --filter "name=${full}" -q 2>/dev/null | grep -c . ; }

while true; do
  desired=$(_desired); running=$(_running)
  ts=$(date '+%H:%M:%S')
  if [ "${desired:-0}" -gt 0 ] && [ "${running:-0}" -eq 0 ]; then
    strikes=$((strikes + 1))
    echo "[watchdog ${ts}] WEDGE? ${full}: desired=${desired} running=0  (strike ${strikes}/${STRIKES})"
    if [ "$strikes" -ge "$STRIKES" ]; then
      echo "[watchdog ${ts}] ⚠️  restarting docker on ${APP_SSH} …"
      ssh -o BatchMode=yes -o ConnectTimeout=10 "$APP_SSH" "$RESTART_CMD" \
        && echo "[watchdog ${ts}] restart issued" \
        || echo "[watchdog ${ts}] restart command returned non-zero (daemon may be bouncing)"
      strikes=0
      sleep "$COOLDOWN"
      continue
    fi
  else
    [ "$strikes" -ne 0 ] && echo "[watchdog ${ts}] recovered: ${full} desired=${desired} running=${running}"
    strikes=0
  fi
  sleep "$INTERVAL"
done
