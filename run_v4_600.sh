#!/usr/bin/env bash
# =============================================================================
# v4 EXTREME OVERLOAD level (users=600, autoscalers max_replicas=20 — same budget
# as the 400 level). Third level of the v4 design; see experiments_v4_uopt_u600.yaml
# for the full rationale. Meant to be launched AFTER level 400 has finished (same
# app host 102 — do not run two campaigns against it concurrently).
#
#   screen -dmS soy-xp-v4600 ./run_v4_600.sh
#
# Monitor:
#   RUN_TAG=v4uopt600 ./xp.sh follow      # results/v4uopt600/console.log
#   screen -r soy-xp-v4600                # the live executor  (detach: Ctrl-A D)
#   tail -f results/v4uopt600/console.log
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")"
[ -f config.env ] && . ./config.env
PY="${PYTHON:-python3}"

echo "=== [$(date '+%F %T')] LEVEL 600  RUN_TAG=v4uopt600  (autoscalers max 20, extreme overload) ==="
mkdir -p results/v4uopt600
RESULTS_ROOT=results/v4uopt600 "$PY" run_experiment.py matrix \
    --file experiments_v4_uopt_u600.yaml --infra monolith-v4 2>&1 | tee -a results/v4uopt600/console.log

echo "=== [$(date '+%F %T')] LEVEL 600 DONE ==="
