#!/usr/bin/env python3
"""Compare the Online Boutique under NO proxy / Envoy / nginx, at a fixed high load.

For each (proxy variant, loadshape), deploy microservices-demo with 2 replicas on
every gRPC backend and drive USERS users, then collect per-container metrics
(bench/metrics.py) so we can compare:
  - the proxy sidecars' overhead (CPU / RAM / net per container), and
  - the load spread: with `node` (no proxy) gRPC pins to ONE replica; with
    `envoy`/`nginx` both replicas should show non-zero CPU.

frontend stays at 1 replica (it binds host :8080) and redis-cart stays at 1
(stateful cache); only the 9 gRPC backends are scaled to 2.

Run ON THE LOAD MACHINE (calls run_experiment.py; needs Docker/Locust):
    RESULTS_ROOT=results/proxycmp python compare_proxies.py
Resumable: a run whose locust_stats.csv already exists is skipped.

NOTE: at USERS=30000 the load host may exhaust ephemeral ports
(OSError 99 'Cannot assign requested address'); those are client-side failures,
not the app — the per-container CPU/spread comparison stays valid.
"""
import os
import sys
import subprocess
from pathlib import Path

USERS = 25000     # ~88% of the load host's ephemeral-port ceiling (~28.2k ports:
                  # 32768-60999) — the max deliverable without port exhaustion, and well
                  # above the shop's 1-replica break (20k) so the proxy's effect is clear
SPAWN = 2000
WARMUP, HOLD = 60, 60
TOTAL_S = WARMUP + HOLD
RUN_TIME = f"{TOTAL_S + 10}s"

# envoy first so an untested proxy config fails fast; node (baseline) last.
VARIANTS = ["envoy", "nginx", "node"]
SHAPES = {
    "constant": "bench/loadshapes/constant.py",
    "step": "bench/loadshapes/step.py",
    "peak": "bench/loadshapes/peak.py",
}
BACKENDS = ["productcatalogservice", "currencyservice", "cartservice",
            "recommendationservice", "adservice", "checkoutservice",
            "shippingservice", "paymentservice", "emailservice"]
SCALE_EXTRA = ",".join(f"{s}=2" for s in BACKENDS)   # 2 replicas on every gRPC backend

RESULTS_ROOT = os.environ.get("RESULTS_ROOT", "results/proxycmp")
os.environ["RESULTS_ROOT"] = RESULTS_ROOT
Path(RESULTS_ROOT).mkdir(parents=True, exist_ok=True)
PY = sys.executable


def shape_env():
    """Deterministic SHAPE_* so constant/step/peak each reach USERS within the window."""
    e = dict(os.environ)
    e["SHAPE_TOTAL_S"] = str(TOTAL_S)
    e["SHAPE_STEP_S"] = str(max(1, TOTAL_S // 5))
    e["SHAPE_STEP_USERS"] = str(max(1, USERS // 4))
    e["SHAPE_RAMP_S"] = str(max(1, TOTAL_S // 3))
    e["SHAPE_PEAK_S"] = str(max(1, TOTAL_S // 3))
    return e


def already_done(tag):
    return (Path(RESULTS_ROOT) / tag / "locust_stats.csv").exists()


def main():
    print(f"Proxy comparison — microservices-demo @ {USERS} users, backends x2, "
          f"spawn {SPAWN}/s, run_time {RUN_TIME}")
    print(f"Variants: {VARIANTS} | shapes: {list(SHAPES)} | results={RESULTS_ROOT}\n")
    for variant in VARIANTS:
        for shape, shape_path in SHAPES.items():
            tag = f"microservices-demo__{variant}__{shape}__u{USERS}"
            if already_done(tag):
                print(f"### {variant} / {shape}: cached — skipped")
                continue
            print(f"\n### {variant} / {shape} — {USERS} users, backends x2 ###")
            cmd = [PY, "run_experiment.py", "run",
                   "--infra", "microservices-demo",
                   "--variant", variant,
                   "--controller", "manual",
                   "--fixed-replicas", "1",          # frontend (scalable svc) binds :8080 -> stays 1
                   "--scale-extra", SCALE_EXTRA,     # 9 gRPC backends -> 2
                   "--loadshape", shape_path,
                   "--users", str(USERS),
                   "--spawn-rate", str(SPAWN),
                   "--run-time", RUN_TIME,
                   "--tag", tag]
            subprocess.run(cmd, env=shape_env())
    print("\nDone: proxy comparison (envoy/nginx/node x constant/step/peak). "
          "Per-container metrics in each run's metrics/ dir.")


if __name__ == "__main__":
    main()
