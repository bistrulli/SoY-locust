#!/usr/bin/env python3
"""Compare the Online Boutique under NO proxy vs Envoy, across a user-count RAMP.

For each (variant, shape, user level) run microservices-demo with 2 replicas on
every gRPC backend and collect per-container metrics (bench/metrics.py) so we can
see, AT EACH LEVEL:
  - the load spread: with `node` (no proxy) gRPC pins to ONE replica; with `envoy`
    both replicas should show non-zero CPU — cleanest in the HEALTHY levels (1k-5k)
    before the app host saturates.
  - where the proxy's capacity gain appears (higher levels).

A ramp avoids the single-25k pitfall where the app host is saturated and the
per-replica evidence is drowned by overload.

frontend stays at 1 replica (binds host :8080) and redis-cart at 1 (stateful);
only the 9 gRPC backends are scaled to 2.

Run ON THE LOAD MACHINE:
    RESULTS_ROOT=results/proxyramp python compare_proxies.py
Resumable: a run whose result.json already exists is skipped.
"""
import os
import sys
import subprocess
from pathlib import Path

LEVELS = [1000, 2000, 5000, 10000, 15000, 20000]   # under the ~28k ephemeral-port ceiling
SPAWN = 2000
WARMUP, HOLD = 60, 60
TOTAL_S = WARMUP + HOLD
RUN_TIME = f"{TOTAL_S + 10}s"

VARIANTS = ["envoy", "node"]                         # envoy first (early validation); nginx dropped (it collapses)
SHAPES = {"constant": "bench/loadshapes/constant.py"}

BACKENDS = ["productcatalogservice", "currencyservice", "cartservice",
            "recommendationservice", "adservice", "checkoutservice",
            "shippingservice", "paymentservice", "emailservice"]
SCALE_EXTRA = ",".join(f"{s}=2" for s in BACKENDS)   # 2 replicas on every gRPC backend

RESULTS_ROOT = os.environ.get("RESULTS_ROOT", "results/proxyramp")
os.environ["RESULTS_ROOT"] = RESULTS_ROOT
Path(RESULTS_ROOT).mkdir(parents=True, exist_ok=True)
PY = sys.executable


def shape_env(users):
    e = dict(os.environ)
    e["SHAPE_TOTAL_S"] = str(TOTAL_S)
    e["SHAPE_STEP_S"] = str(max(1, TOTAL_S // 5))
    e["SHAPE_STEP_USERS"] = str(max(1, users // 4))
    e["SHAPE_RAMP_S"] = str(max(1, TOTAL_S // 3))
    e["SHAPE_PEAK_S"] = str(max(1, TOTAL_S // 3))
    return e


def already_done(tag):
    return (Path(RESULTS_ROOT) / tag / "result.json").exists()


def main():
    print(f"Proxy ramp — microservices-demo, backends x2, spawn {SPAWN}/s, run_time {RUN_TIME}")
    print(f"Variants: {VARIANTS} | shapes: {list(SHAPES)} | levels: {LEVELS} | results={RESULTS_ROOT}\n")
    for variant in VARIANTS:
        for shape, shape_path in SHAPES.items():
            for users in LEVELS:
                tag = f"microservices-demo__{variant}__{shape}__u{users}"
                if already_done(tag):
                    print(f"### {variant} / {shape} / u{users}: cached — skipped")
                    continue
                print(f"\n### {variant} / {shape} / {users} users, backends x2 ###")
                cmd = [PY, "run_experiment.py", "run",
                       "--infra", "microservices-demo",
                       "--variant", variant,
                       "--controller", "manual",
                       "--fixed-replicas", "1",          # frontend binds :8080 -> stays 1
                       "--scale-extra", SCALE_EXTRA,     # 9 gRPC backends -> 2
                       "--loadshape", shape_path,
                       "--users", str(users),
                       "--spawn-rate", str(SPAWN),
                       "--run-time", RUN_TIME,
                       "--tag", tag]
                subprocess.run(cmd, env=shape_env(users))
    print("\nDone: proxy ramp (node/envoy x constant x levels). "
          "Per-container metrics in each run's metrics/ dir.")


if __name__ == "__main__":
    main()
