#!/usr/bin/env bash
# =============================================================================
# Chained v4 re-run (two-level design): prune dead cells → LEVEL 300 → LEVEL 400.
# Meant to be launched INSIDE a detached screen on host 101; runs both matrices
# sequentially. The wedge self-heal (bench/runner.py) protects each run so the
# night survives a Swarm dispatcher wedge unattended.
#
#   screen -dmS soy-xp-v4both ./run_v4_both.sh
#
# Monitor:
#   ./xp.sh follow                        # LEVEL 300 → results/v4uopt/console.log
#   RUN_TAG=v4uopt400 ./xp.sh follow      # LEVEL 400 → results/v4uopt400/console.log
#   screen -r soy-xp-v4both               # the live executor  (detach: Ctrl-A D)
#   tail -f results/v4both.log            # everything (prune + both levels)
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")"
[ -f config.env ] && . ./config.env
PY="${PYTHON:-python3}"

echo "=== [$(date '+%F %T')] PRUNE dead (0-node) cells in results/v4uopt ==="
"$PY" tools/prune_failed_runs.py results/v4uopt --apply || true

echo "=== [$(date '+%F %T')] LEVEL 300  RUN_TAG=v4uopt  (max 8, Pareto) — resume, redo pruned ==="
mkdir -p results/v4uopt
RESULTS_ROOT=results/v4uopt "$PY" run_experiment.py matrix \
    --file experiments_v4_uopt.yaml --infra monolith-v4 2>&1 | tee -a results/v4uopt/console.log

echo "=== [$(date '+%F %T')] LEVEL 400  RUN_TAG=v4uopt400  (autoscalers max 20, overload) ==="
mkdir -p results/v4uopt400
RESULTS_ROOT=results/v4uopt400 "$PY" run_experiment.py matrix \
    --file experiments_v4_uopt_u400.yaml --infra monolith-v4 2>&1 | tee -a results/v4uopt400/console.log

echo "=== [$(date '+%F %T')] BOTH LEVELS DONE ==="
