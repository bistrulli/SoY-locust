#!/usr/bin/env bash
# =============================================================================
# "One command" driver for SoY-locust load experiments.
#
# Topology (the harness + Locust run HERE, on the LOAD machine; the app
# runs on the remote APP machine):
#     load machine     : 192.168.3.101  (here)
#     app machine      : 192.168.3.102  (remote Docker + Scaphandre)
#     Tasmota wattmeter: 192.168.3.131
#
# A campaign is keyed by RUN_TAG (like bench-v2): it names results/<RUN_TAG>/ AND the
# screen session 'soy-xp-<RUN_TAG>'. Keep the SAME RUN_TAG to resume; change it for a
# fresh campaign; use distinct RUN_TAGs to run two campaigns in parallel.
#
#   RUN_TAG=run1 ./xp.sh go        # all-in-one: check → start (recommended)
#   RUN_TAG=run1 ./xp.sh start     # runs the WHOLE matrix INSIDE screen 'soy-xp-run1'
#                          #   - the screen IS the executor → `screen -r soy-xp-run1` shows it live
#                          #   - AUTO-RESUME: skips runs whose result.json already exists
#   RUN_TAG=run1 ./xp.sh start --force   # re-run EVERYTHING, ignore already-done runs
#   RUN_TAG=run1 ./xp.sh start run --infra microservices-demo --controller hpa --variant go
#   RUN_TAG=t1   ./xp.sh test      # run ONE configured experiment (TEST_* in config.env)
#   RUN_TAG=run1 ./xp.sh watch     # = screen -r soy-xp-run1  (attach to the live executor)
#   RUN_TAG=run1 ./xp.sh status    # screen state + last run + nb of results
#   RUN_TAG=run1 ./xp.sh follow    # tail -f results/run1/console.log (read-only)
#   RUN_TAG=run1 ./xp.sh stop      # quits the screen (stops the run) + teardown of the infra
#   ./xp.sh check                  # probes energy/system (Scaphandre/Tasmota/docker)
#   ./xp.sh aggregate              # builds results/summary.csv
#   ./xp.sh sync                   # (from your DEV box) rsync the source → load machine
#   (RUN_TAG is optional: without it, results=results/ and screen=soy-xp)
#
# ⚠️  The run lives INSIDE the screen:
#       - detach WITHOUT stopping it:   Ctrl-A then D
#       - Ctrl-C / `exit` / closing the screen  ==  STOP the run
#     The full log is mirrored to results/<RUN_TAG>/console.log (via tee, persists even
#     if the screen dies), so `follow` / `status` work regardless. Session: SOY_SCREEN=...
#
# Override possible: BENCH_APP_HOST=... DOCKER_HOST=... RUN_TAG=run1 ./xp.sh go
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")"

# --- central config: machines, ports, endpoints, measurement & reproducibility ---
# Edit config.env to retarget the two machines or pin the load; env vars still override.
[ -f config.env ] && . ./config.env

# --- campaign / idempotency key (like bench-v2 RUN_TAG) ---
# RUN_TAG groups a whole campaign: it names the results dir AND the screen session,
# so two campaigns with distinct RUN_TAG run in parallel without colliding, and
# `start` RESUMES a campaign by skipping the runs already present in results/<RUN_TAG>/.
RUN_TAG="${RUN_TAG:-}"
if [ -n "$RUN_TAG" ]; then
  export RESULTS_ROOT="${RESULTS_ROOT:-results/$RUN_TAG}"
  SCREEN_NAME="${SOY_SCREEN:-soy-xp-$RUN_TAG}"
else
  export RESULTS_ROOT="${RESULTS_ROOT:-results}"
  SCREEN_NAME="${SOY_SCREEN:-soy-xp}"
fi

# LOAD_HOST / LOAD_DIR / BENCH_APP_HOST and the endpoints come from config.env (sourced above).
PY="${PYTHON:-python3}"
PIDFILE=".xp.${RUN_TAG:-default}.pid"
LOGFILE="$RESULTS_ROOT/console.log"              # tee mirror of the run (overwritten each start)

_have_screen()    { [ "${XP_NO_SCREEN:-0}" = 1 ] && return 1; command -v screen >/dev/null 2>&1; }
_screen_running() { _have_screen && screen -ls 2>/dev/null | grep -q "[.]${SCREEN_NAME}[[:space:]]"; }
# RUNNING if the executor screen is alive OR (fallback mode) the pidfile process is.
_running() { _screen_running || { [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; }; }

case "${1:-}" in
  start)
    shift
    if _running; then echo "Already running (screen '${SCREEN_NAME}' or PID file)."; exit 1; fi
    if [ "$#" -eq 0 ]; then
      ARGS=(matrix --file experiments.yaml)             # default: the whole matrix (auto-resume)
    elif [ "$1" = "--force" ]; then
      shift; ARGS=(matrix --file experiments.yaml --force "$@")
    else
      ARGS=("$@")
    fi
    echo "Topology: app=$BENCH_APP_HOST docker=$DOCKER_HOST scaph=$SCAPHANDRE_URL watt=$WATTMETER_HTTP sys=$SYS_SOURCE"
    echo "Campaign: RUN_TAG=${RUN_TAG:-(none)}  results=$RESULTS_ROOT  screen=$SCREEN_NAME"
    echo "Command: $PY run_experiment.py ${ARGS[*]}"
    mkdir -p "$RESULTS_ROOT"
    rm -f "$LOGFILE"
    if _have_screen; then
      # The experiment runs INSIDE a detached screen → `screen -r soy-xp` attaches
      # to the live executor. `tee` mirrors everything to xp.log (persists even if
      # the screen is killed). cwd is inherited, so paths stay relative to the repo.
      CMD=$(printf '%q ' "$PY" run_experiment.py "${ARGS[@]}")
      screen -dmS "$SCREEN_NAME" bash -c "${CMD} 2>&1 | tee $LOGFILE"
      rm -f "$PIDFILE"
      echo "Started in screen '${SCREEN_NAME}' (the LIVE executor) → log: $LOGFILE"
      echo "See it live:   screen -r ${SCREEN_NAME}     (or: ./xp.sh watch)"
      echo "Detach without stopping:  Ctrl-A then D     |     stop the run:  ./xp.sh stop"
    else
      # Fallback (no screen installed): detached background process.
      if command -v setsid >/dev/null 2>&1; then
        setsid "$PY" run_experiment.py "${ARGS[@]}" >"$LOGFILE" 2>&1 &
      else
        nohup "$PY" run_experiment.py "${ARGS[@]}" >"$LOGFILE" 2>&1 &
      fi
      echo $! > "$PIDFILE"
      echo "Started (PID $(cat "$PIDFILE")) — no 'screen' installed, detached → log: $LOGFILE"
      echo "Follow:  ./xp.sh follow"
    fi
    ;;

  go)
    # all-in-one (like bench-v2 `go`): preflight check, then start (detached, in screen).
    shift
    echo "[go] preflight check…"
    if ! "$PY" run_experiment.py check; then
      echo "[go] ⚠️  check failed — fix the measurement/registry chain, or bypass with ./xp.sh start"
      exit 1
    fi
    echo "[go] check OK → starting…"
    exec "$0" start "$@"
    ;;

  test)
    # run ONE configured experiment (see TEST_* in config.env). Extra args pass
    # through, e.g.:  RUN_TAG=t ./xp.sh test --capacity --users 300
    shift
    targs=(run --infra "$TEST_INFRA" --controller "$TEST_CONTROLLER"
           --users "$TEST_USERS" --run-time "$TEST_RUN_TIME")
    [ -n "${TEST_VARIANT:-}" ] && targs+=(--variant "$TEST_VARIANT")
    echo "[test] ${TEST_INFRA} / ${TEST_CONTROLLER}${TEST_VARIANT:+ / $TEST_VARIANT}  users=$TEST_USERS time=$TEST_RUN_TIME"
    exec "$0" start "${targs[@]}" "$@"
    ;;

  status)
    if _screen_running; then
      echo "● RUNNING in screen '${SCREEN_NAME}'  (attach: screen -r ${SCREEN_NAME})"
      screen -ls 2>/dev/null | grep "${SCREEN_NAME}" || true
    elif _running; then
      echo "● RUNNING (PID $(cat "$PIDFILE"), fallback mode)"
    else
      echo "○ stopped  (no screen '${SCREEN_NAME}', no live PID)"
    fi
    echo "Current run:"
    grep -E "=== Experiment|\[matrix" "$LOGFILE" 2>/dev/null | tail -1 || true
    n=$(find "$RESULTS_ROOT" -maxdepth 2 -name result.json 2>/dev/null | wc -l | tr -d ' ')
    echo "Completed runs: ${n}"
    echo "Log: $LOGFILE   (live: ./xp.sh watch  |  read-only: ./xp.sh follow)"
    echo "--- last lines ---"
    tail -n 8 "$LOGFILE" 2>/dev/null || echo "(no log)"
    ;;

  follow)
    tail -f "$LOGFILE"
    ;;

  watch|attach|screen)
    # Attach to the LIVE executor screen (what `start` created). Detach with
    # Ctrl-A D to leave it running. If no screen is live (run finished, or started
    # in fallback mode), fall back to a read-only tail of xp.log.
    if _screen_running; then
      echo "Attaching to executor screen '${SCREEN_NAME}' — detach with Ctrl-A D (do NOT Ctrl-C)…"
      exec screen -r "${SCREEN_NAME}"
    fi
    if [ ! -f "$LOGFILE" ]; then echo "No screen '${SCREEN_NAME}' and no log yet. Start a run: ./xp.sh start"; exit 1; fi
    echo "(no live screen '${SCREEN_NAME}' — tailing ${LOGFILE} read-only; Ctrl-C quits the viewer only)"
    exec tail -n +1 -f "${LOGFILE}"
    ;;

  stop)
    stopped=0
    if _screen_running; then
      echo "Quitting executor screen '${SCREEN_NAME}'…"
      screen -S "${SCREEN_NAME}" -X quit 2>/dev/null || true
      stopped=1
    fi
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      PID="$(cat "$PIDFILE")"
      echo "Stopping process group (PID $PID)…"
      kill -TERM "-$PID" 2>/dev/null || kill -TERM "$PID" 2>/dev/null
      sleep 3
      kill -KILL "-$PID" 2>/dev/null || true
      stopped=1
    fi
    [ "$stopped" = 0 ] && echo "No process running."
    rm -f "$PIDFILE"
    echo "Teardown of infra…"
    "$PY" run_experiment.py down || true
    echo "Stopped."
    ;;

  sync)
    # Push local source → LOAD machine (harness) AND APP machine. The app host needs
    # the SAME tree because compose bind-mounts (prometheus.yml, nginx confs…) resolve
    # on the DOCKER DAEMON's host (the app), not where compose runs. Run from your DEV box.
    # Excludes results/runtime/pycache so remote measurements are never touched.
    for H in "${LOAD_HOST}" "${BENCH_APP_HOST}"; do
      echo "rsync ./ → ${H}:${LOAD_DIR}/"
      rsync -av --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
            --exclude 'results' --exclude 'results-benoit' --exclude 'runtime_data' \
            --exclude 'profiled_data*' \
            ./ "${H}:${LOAD_DIR}/" || echo "  (rsync to ${H} failed — see above)"
    done
    echo "→ harness=${LOAD_HOST}  |  app/bind-mounts=${BENCH_APP_HOST}  (dir ~/${LOAD_DIR})"
    ;;

  check)    "$PY" run_experiment.py check ;;
  aggregate) "$PY" run_experiment.py aggregate ;;
  report)   "$PY" run_experiment.py report ;;
  list)     "$PY" run_experiment.py list ;;

  *)
    sed -n '2,36p' "$0"   # prints the help header
    exit 1
    ;;
esac
