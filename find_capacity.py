#!/usr/bin/env python3
"""Find the MAX number of users each stack can handle (no autoscaler).

Goal: per architecture (monolith-v4, monolith-v5, microservices-demo) and per
loadshape, with a FIXED number of replicas (no optimizer), ramp the user count up
until the failure rate exceeds a threshold. The highest user level that stays
under the threshold is the stack's capacity.

Everything is driven by ``capacity_config.json``:
    - replicas       : fixed replica count per infra (the "predefined config")
    - user_levels    : the user counts to try (ascending)
    - loadshapes     : {name: path} — the patterns to test the capacity under
    - run_time / spawn_rate / fail_threshold / controller

This complements (does not replace) the controller sweep (experiments_sweep.yaml).

RUN IT ON THE LOAD MACHINE (it calls run_experiment.py, which needs Docker/Locust).
    RESULTS_ROOT=results/capacity python find_capacity.py
    # or follow/resume inside a screen:
    screen -dmS soy-capacity bash -c 'RESULTS_ROOT=results/capacity python find_capacity.py 2>&1 | tee results/capacity/console.log'

Resumable: a level whose locust_stats.csv already exists is reused, not re-run.
Early-stop: once a level breaks, higher levels are skipped (they would break too).
"""
import json
import csv
import os
import sys
import subprocess
from pathlib import Path

CONFIG = sys.argv[1] if len(sys.argv) > 1 else "capacity_config.json"
cfg = json.load(open(CONFIG))

RUN_TIME = cfg.get("run_time", "180s")
TOTAL_S = int(float(str(RUN_TIME).rstrip("s")))       # run duration in seconds (drives the shapes)
SPAWN_CFG = cfg.get("spawn_rate", 100)                # int (global) OR {infra: int}
THRESH = float(cfg.get("fail_threshold", 0.05))
CONTROLLER = cfg.get("controller", "manual")          # fixed replicas => no optimizer
STOP_ON_BREAK = bool(cfg.get("stop_on_break", True))  # False => run every level (e.g. rupture x2)
REPLICAS = cfg["replicas"]                             # {infra: N}
LEVELS_CFG = cfg["user_levels"]                        # [..] global  OR  {infra: [..]} per-infra
SHAPES = cfg["loadshapes"]                             # {name: path}


def levels_for(infra):
    """User levels for an infra: per-infra list if user_levels is a dict, else the global list."""
    src = LEVELS_CFG.get(infra, []) if isinstance(LEVELS_CFG, dict) else LEVELS_CFG
    return sorted(src)


def spawn_for(infra):
    """Spawn rate for an infra: per-infra if spawn_rate is a dict, else the global value."""
    return int(SPAWN_CFG.get(infra, 100) if isinstance(SPAWN_CFG, dict) else SPAWN_CFG)

# the service the controller scales (the rest of a per-service dict is fixed extra)
SCALABLE = {"monolith-v4": "node", "monolith-v5": "ms-exercise",
            "microservices-demo": "frontend"}


def split_replicas(infra):
    """From an int OR a per-service dict, return (fixed_scalable, extra_csv).

    8                                  -> (8, "")                 # scale the scalable svc
    {"ms-exercise":8,"gateway":2,...}  -> (8, "gateway=2,...")    # + fixed extra services
    """
    spec = REPLICAS[infra]
    if isinstance(spec, dict):
        scal = SCALABLE.get(infra, "")
        fixed = int(spec.get(scal, 1))
        extra = ",".join(f"{k}={v}" for k, v in spec.items() if k != scal)
        return fixed, extra
    return int(spec), ""


RESULTS_ROOT = os.environ.get("RESULTS_ROOT", "results/capacity")
os.environ["RESULTS_ROOT"] = RESULTS_ROOT
Path(RESULTS_ROOT).mkdir(parents=True, exist_ok=True)
PY = sys.executable


def fail_rate(tag):
    """Aggregated failure rate from a finished run, or None if missing."""
    p = Path(RESULTS_ROOT) / tag / "locust_stats.csv"
    if not p.exists():
        return None
    for row in csv.DictReader(open(p)):
        if (row.get("Name") or "").strip() == "Aggregated":
            rq = float(row.get("Request Count", 0) or 0)
            fl = float(row.get("Failure Count", 0) or 0)
            return (fl / rq) if rq else 1.0
    return None


def _shape_env(users):
    """Deterministic SHAPE_* so constant/step/peak each REACH `users` within ~run_time
    (esp. the shop's high levels): step climbs in ~4 steps, peak = ramp/plateau/ramp."""
    env = dict(os.environ)
    env["SHAPE_TOTAL_S"] = str(TOTAL_S)
    env["SHAPE_STEP_S"] = str(max(1, TOTAL_S // 5))          # step: ~4 steps up to `users`, then hold
    env["SHAPE_STEP_USERS"] = str(max(1, users // 4))
    env["SHAPE_RAMP_S"] = str(max(1, TOTAL_S // 3))          # peak: ramp -> plateau(`users`) -> ramp
    env["SHAPE_PEAK_S"] = str(max(1, TOTAL_S // 3))
    return env


def run_one(infra, shape_path, users, tag):
    fixed, extra = split_replicas(infra)
    cmd = [PY, "run_experiment.py", "run",
           "--infra", infra,
           "--controller", CONTROLLER,
           "--fixed-replicas", str(fixed),
           "--loadshape", shape_path,
           "--users", str(users),
           "--spawn-rate", str(spawn_for(infra)),
           "--run-time", RUN_TIME,
           "--tag", tag]
    if extra:
        cmd += ["--scale-extra", extra]
    subprocess.run(cmd, env=_shape_env(users))
    return fail_rate(tag)


def main():
    print(f"Capacity test — controller={CONTROLLER} (fixed replicas, no optimizer), "
          f"run_time={RUN_TIME}, threshold={THRESH*100:.0f}%")
    print(f"Replicas: {REPLICAS}")
    results = {}
    for infra, nrepl in REPLICAS.items():
        fixed, _ = split_replicas(infra)
        for shape_name, shape_path in SHAPES.items():
            print(f"\n### {infra} / {shape_name}  (replicas={nrepl}) ###")
            max_ok, breaking = None, None
            for u in levels_for(infra):
                tag = f"{infra}__{shape_name}__r{fixed}__u{u}"
                fr = fail_rate(tag)                        # resume: reuse if present
                cached = fr is not None
                if fr is None:
                    fr = run_one(infra, shape_path, u, tag)
                if fr is None:
                    print(f"  users={u:>6} : RUN FAILED (no stats) — skipping level")
                    continue
                tag_ok = fr <= THRESH
                print(f"  users={u:>6} : fail={fr*100:5.1f}%  "
                      f"[{'OK' if tag_ok else 'BREAK'}]{'  (cached)' if cached else ''}")
                if tag_ok:
                    max_ok = u
                elif breaking is None:
                    breaking = u                           # first break (record; keep going for rupture x2)
                if not tag_ok and STOP_ON_BREAK:
                    break                                  # higher levels break too
            results[f"{infra}/{shape_name}"] = {
                "replicas": nrepl, "max_users": max_ok, "breaking_users": breaking,
            }

    print("\n" + "=" * 64)
    print(f"MAX USERS PER STACK  (sustained fail <= {THRESH*100:.0f}%)")
    print("=" * 64)
    print(f"{'infra / loadshape':>38} {'replicas':>8} {'max_users':>10} {'breaks_at':>10}")
    for k, v in results.items():
        print(f"{k:>38} {str(v['replicas']):>28} "
              f"{str(v['max_users']):>10} {str(v['breaking_users']):>10}")
    out = Path(RESULTS_ROOT) / "max_users.json"
    json.dump(results, open(out, "w"), indent=2)
    print(f"\n-> written {out}")


if __name__ == "__main__":
    main()
