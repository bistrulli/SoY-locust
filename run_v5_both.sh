#!/usr/bin/env bash
# =============================================================================
# v5 two-level campaign: LEVEL 450 (efficiency) then LEVEL 900 (overload).
# Mirrors run_v4_both.sh. Meant to be launched INSIDE a detached screen on host 101.
#
#   screen -dmS soy-xp-v5both ./run_v5_both.sh
#
# Monitor:
#   tail -f results/v5uopt/console.log       # LEVEL 450
#   tail -f results/v5uopt900/console.log    # LEVEL 900
#   screen -r soy-xp-v5both                  # the live executor  (detach: Ctrl-A D)
#   tail -f results/v5both.log               # everything
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")"
[ -f config.env ] && . ./config.env
PY="${PYTHON:-python3}"

echo "=== [$(date '+%F %T')] LEVEL 450  RUN_TAG=v5uopt  (max 8, efficiency) ==="
mkdir -p results/v5uopt
RESULTS_ROOT=results/v5uopt "$PY" run_experiment.py matrix \
    --file experiments_v5_uopt.yaml --infra monolith-v5 2>&1 | tee -a results/v5uopt/console.log

echo "=== [$(date '+%F %T')] LEVEL 900  RUN_TAG=v5uopt900  (autoscalers max 16, overload) ==="
mkdir -p results/v5uopt900
RESULTS_ROOT=results/v5uopt900 "$PY" run_experiment.py matrix \
    --file experiments_v5_uopt_u900.yaml --infra monolith-v5 2>&1 | tee -a results/v5uopt900/console.log

echo "=== [$(date '+%F %T')] BOTH LEVELS DONE ==="
