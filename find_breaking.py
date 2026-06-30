#!/usr/bin/env python3
"""Ramp the user count up and find each stack's BREAKING POINT.

Definition (per stack, fixed replicas, no optimizer, multi-process load):
    a user level is "OK" only if it sustains < fail_threshold failures for at
    least `hold_s` seconds (>= 1 minute). We ramp the level up step by step; the
    last OK level is the stack's capacity, the first failing level is the break.

Each level is a fresh constant-load run (warmup then a held window); the failure
rate is measured over the LAST `hold_s` seconds (the sustained minute) from
locust_stats_history.csv — not the whole run, so the warmup ramp does not count.

Driven by capacity_config.json:
    replicas : per-infra fixed replicas (int, or per-service dict)
    ramp     : { warmup_s, hold_s, spawn_rate, fail_threshold,
                 levels: { <infra>: {start, step, max} } }

RUN ON THE LOAD MACHINE:
    RESULTS_ROOT=results/breaking python find_breaking.py
    # or, in a screen:  RUN_TAG=brk ./xp.sh breaking
Resumable (a level with a history csv is reused); early-stop at the first break.
"""
import json
import csv
import os
import sys
import subprocess
from pathlib import Path

CONFIG = sys.argv[1] if len(sys.argv) > 1 else "capacity_config.json"
cfg = json.load(open(CONFIG))
REPLICAS = cfg["replicas"]
RAMP = cfg.get("ramp", {})
WARMUP = int(RAMP.get("warmup_s", 40))
HOLD = int(RAMP.get("hold_s", 60))                      # >= 60 => "1 minute"
SPAWN = int(RAMP.get("spawn_rate", 200))
THRESH = float(RAMP.get("fail_threshold", 0.05))        # < 5%
LEVELS = RAMP.get("levels", {})
# Scaling strategy, configured up front: "manual" (fixed replicas, no optimizer)
# or an autoscaler "hpa"/"uopt" with its parameters.
CONTROLLER = RAMP.get("controller", "manual")
TARGET = float(RAMP.get("target_utilization", 0.5))
MIN_R = int(RAMP.get("min_replicas", 1))
MAX_R = int(RAMP.get("max_replicas", 8))
SHAPE = "bench/loadshapes/constant.py"                   # hold a constant level
RUN_TIME = f"{WARMUP + HOLD + 10}s"

SCALABLE = {"monolith-v4": "node", "monolith-v5": "ms-exercise",
            "microservices-demo": "frontend"}
RESULTS_ROOT = os.environ.get("RESULTS_ROOT", "results/breaking")
os.environ["RESULTS_ROOT"] = RESULTS_ROOT
Path(RESULTS_ROOT).mkdir(parents=True, exist_ok=True)
PY = sys.executable


def split_replicas(infra):
    spec = REPLICAS[infra]
    if isinstance(spec, dict):
        scal = SCALABLE.get(infra, "")
        return int(spec.get(scal, 1)), ",".join(f"{k}={v}" for k, v in spec.items() if k != scal)
    return int(spec), ""


def sustained_fail_rate(tag):
    """Failure rate over the LAST HOLD seconds (the sustained window), or None."""
    p = Path(RESULTS_ROOT) / tag / "locust_stats_history.csv"
    if not p.exists():
        return None
    pts = []  # (timestamp, total_requests, total_failures)
    for row in csv.DictReader(open(p)):
        if (row.get("Name") or "").strip() != "Aggregated":
            continue
        try:
            ts = float(row.get("Timestamp") or 0)
            req = float(row.get("Total Request Count") or 0)
            fail = float(row.get("Total Failure Count") or 0)
        except (TypeError, ValueError):
            continue
        pts.append((ts, req, fail))
    if len(pts) < 2:
        return None
    t_end = pts[-1][0]
    start = next((p for p in pts if p[0] >= t_end - HOLD), pts[0])
    dreq = pts[-1][1] - start[1]
    dfail = pts[-1][2] - start[2]
    return (dfail / dreq) if dreq > 0 else 1.0


def run_level(infra, users, tag):
    fixed, extra = split_replicas(infra)   # scalable count (fixed mode) + fixed secondaries
    cmd = [PY, "run_experiment.py", "run", "--infra", infra,
           "--controller", CONTROLLER,
           "--loadshape", SHAPE, "--users", str(users), "--spawn-rate", str(SPAWN),
           "--run-time", RUN_TIME, "--tag", tag]
    if CONTROLLER == "manual":
        cmd += ["--fixed-replicas", str(fixed)]
    else:                                  # autoscaler: it scales the scalable service
        cmd += ["--target-util", str(TARGET),
                "--min-replicas", str(MIN_R), "--max-replicas", str(MAX_R)]
    if extra:                              # secondary tiers stay fixed even under an autoscaler
        cmd += ["--scale-extra", extra]
    subprocess.run(cmd)
    return sustained_fail_rate(tag)


def main():
    print(f"Breaking-point ramp — fixed replicas, multi-process load.")
    print(f"OK = sustained fail < {THRESH*100:.0f}% over the last {HOLD}s "
          f"(warmup {WARMUP}s, spawn {SPAWN}/s)\n")
    results = {}
    for infra in REPLICAS:
        lv = LEVELS.get(infra)
        if not lv:
            print(f"## {infra}: no ramp levels configured — skipped"); continue
        print(f"## {infra}  (controller={CONTROLLER}, replicas {REPLICAS[infra]})")
        users = lv["start"]; max_ok = None; breaking = None
        while users <= lv["max"]:
            tag = f"{infra}__ramp__{CONTROLLER}__u{users}"
            fr = sustained_fail_rate(tag)
            cached = fr is not None
            if fr is None:
                fr = run_level(infra, users, tag)
            if fr is None:
                print(f"   users={users:>5} : RUN FAILED (no history)"); users += lv["step"]; continue
            ok = fr <= THRESH
            print(f"   users={users:>5} : sustained fail={fr*100:5.1f}%  "
                  f"[{'OK' if ok else 'BREAK'}]{'  (cached)' if cached else ''}")
            if ok:
                max_ok = users; users += lv["step"]
            else:
                breaking = users; break
        results[infra] = {"replicas": REPLICAS[infra], "max_users": max_ok,
                          "breaking_users": breaking}

    print("\n" + "=" * 60)
    print(f"BREAKING POINT  (max users sustaining fail < {THRESH*100:.0f}% for {HOLD}s)")
    print("=" * 60)
    print(f"{'infra':>22} {'max_users':>10} {'breaks_at':>10}")
    for k, v in results.items():
        print(f"{k:>22} {str(v['max_users']):>10} {str(v['breaking_users']):>10}")
    out = Path(RESULTS_ROOT) / "breaking.json"
    json.dump(results, open(out, "w"), indent=2)
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
