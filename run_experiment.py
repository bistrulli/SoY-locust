#!/usr/bin/env python3
"""Unified driver for SoY-locust load experiments.

Subcommands:
    run      runs ONE experiment (infra × controller × loadshape × variant)
    matrix   unrolls a comparison matrix from a YAML file
    check    probes the energy/system measurement chain (energy_probe)
    list     lists available infra, controllers and variants

Examples:
    python run_experiment.py check
    python run_experiment.py list
    python run_experiment.py run --infra microservices-demo --controller hpa \\
        --loadshape locust_file/loadshapes/cyclical_shape.py --users 200 --run-time 180s
    python run_experiment.py run --infra microservices-demo --controller hpa \\
        --variant go --users 200            # language impact (currencyservice Go)
    python run_experiment.py run --infra monolith-v5 --controller manual-sched \\
        --schedule 0:1,60:3,120:2 --run-time 180s
    python run_experiment.py run --infra monolith-v4 --controller uopt --dry-run
    python run_experiment.py matrix --file experiments.yaml
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from bench.config import BenchConfig
from bench.controllers import CONTROLLER_KINDS
from bench.infra import get_infra, list_infra, INFRA
from bench.metrics import energy_probe
from bench.runner import ExperimentSpec, run_experiment, _tag


def _setup_logging() -> None:
    level = os.getenv("SOY_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S")


def _parse_schedule(s: str):
    """'0:1,60:3,120:2' -> [[0.0,1],[60.0,3],[120.0,2]]"""
    out = []
    for part in s.split(","):
        t, r = part.split(":")
        out.append([float(t), int(r)])
    return out


# =============================================================================
# run
# =============================================================================

def cmd_run(args) -> int:
    spec = ExperimentSpec(
        infra=args.infra,
        controller=args.controller,
        loadshape=args.loadshape,
        locustfile=args.locustfile,
        host=args.host,
        users=args.users,
        spawn_rate=args.spawn_rate,
        run_time=args.run_time,
        target_utilization=args.target_util,
        min_replicas=args.min_replicas,
        max_replicas=args.max_replicas,
        fixed_replicas=args.fixed_replicas,
        schedule=_parse_schedule(args.schedule) if args.schedule else None,
        initial_replicas=args.initial_replicas,
        control_period_s=args.control_period,
        variant=args.variant,
        web_port=args.web_port,
        tag=args.tag,
        repetition=args.rep,
        uopt_method=args.uopt_method,
        hpa_tolerance=args.hpa_tolerance,
        hpa_downscale_s=args.hpa_downscale,
        rps_per_user=args.rps_per_user,
        capacity=args.capacity,
        fail_threshold=args.fail_threshold,
        sla_p95_ms=args.sla_p95_ms,
        break_samples=args.break_samples,
        stop_on_break=not args.no_stop_on_break,
        keep_up=args.keep_up,
        dry_run=args.dry_run,
    )
    summary = run_experiment(spec, BenchConfig.from_env())
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


# =============================================================================
# matrix
# =============================================================================

def cmd_matrix(args) -> int:
    import yaml
    doc = yaml.safe_load(Path(args.file).read_text())
    defaults = doc.get("defaults", {}) or {}
    cfg = BenchConfig.from_env()
    n = 0
    results = []
    for entry in doc.get("experiments", []):
        infra_name = entry["infra"]
        if args.infra and infra_name != args.infra:
            continue                       # --infra: run ONE stack instead of all
        infra = get_infra(infra_name)
        controllers = entry.get("controllers", ["none"])
        variants = entry.get("variants", [infra.default_variant])
        reps = int(entry.get("reps", defaults.get("reps", 1)))

        def g(key, dflt=None):
            return entry.get(key, defaults.get(key, dflt))

        loadshapes = g("loadshapes") or [g("loadshape")]
        for shape in loadshapes:
            if args.shape and (not shape or Path(shape).stem != args.shape):
                continue                   # --shape: run ONE loadshape
            for variant in variants:
                for controller in controllers:
                    for rep in range(reps):
                        spec = ExperimentSpec(
                            infra=infra_name,
                            controller=controller,
                            loadshape=shape,
                            locustfile=g("locustfile"),
                            host=g("host"),
                            users=int(g("users", 100)),
                            spawn_rate=int(g("spawn_rate", 50)),
                            run_time=str(g("run_time", "120s")),
                            target_utilization=float(g("target_utilization", 0.5)),
                            min_replicas=g("min_replicas"),
                            max_replicas=g("max_replicas"),
                            fixed_replicas=g("fixed_replicas"),
                            schedule=g("schedule"),
                            initial_replicas=g("initial_replicas"),
                            control_period_s=float(g("control_period_s", 5.0)),
                            variant=variant,
                            repetition=rep,
                            label=g("label"),
                            uopt_method=str(g("uopt_method", "scip")),
                            rps_per_user=float(g("rps_per_user", 1.0)),
                            capacity=bool(g("capacity", False)),
                            fail_threshold=float(g("fail_threshold", 0.02)),
                            sla_p95_ms=g("sla_p95_ms"),
                            break_samples=int(g("break_samples", 3)),
                            stop_on_break=bool(g("stop_on_break", True)),
                            dry_run=args.dry_run,
                        )
                        n += 1
                        # --- resume: skip a run whose result.json already exists ---
                        tag = _tag(spec, infra)
                        done = cfg.results_path(tag, "result.json")
                        if done.exists() and not args.force and not args.dry_run:
                            logging.info("[matrix %d] SKIP (already done): %s", n, tag)
                            results.append({"tag": tag, "skipped": True})
                            continue
                        logging.info("[matrix %d] %s/%s/%s/%s rep%d", n, infra_name,
                                     controller, variant,
                                     Path(shape).stem if shape else "noshape", rep)
                        try:
                            results.append(run_experiment(spec, cfg))
                        except Exception as e:
                            # the failure is already explained (e.g. backends prints a
                            # registry-auth hint); keep the log clean, full trace at DEBUG.
                            logging.error("[matrix %d] experiment failed: %s", n, e)
                            logging.debug("experiment traceback:", exc_info=True)
                            results.append({"infra": infra_name, "controller": controller,
                                            "variant": variant, "error": str(e)})
    skipped = sum(1 for r in results if r.get("skipped"))
    logging.info("[matrix] done: %d run(s), %d skipped (already present)",
                 len(results) - skipped, skipped)
    print(json.dumps({"runs": len(results), "skipped": skipped, "results": results},
                     indent=2, ensure_ascii=False))
    return 0


# =============================================================================
# check / list
# =============================================================================

def _format_check(probe: dict):
    """Human-readable verdict for `check`. Returns (text, all_ok)."""
    lines = ["=== Measurement chain — preflight ===",
             f"Topology : app={probe.get('app_host')}  docker={probe.get('docker_host')}",
             f"           system source: {probe.get('system_source')}",
             ""]
    active = []          # sources actually recording
    rapl_ok = system_ok = False

    # --- RAPL / energy ---
    rapl_e = probe.get("rapl_energy_J") or {}
    rapl_src = probe.get("rapl_source")
    if rapl_src == "disabled":
        rapl_ok = True   # intentionally off (RAPL_ENABLED=0) — not a failure
        lines.append("  [--] RAPL energy            disabled (RAPL_ENABLED=0)")
    elif rapl_src not in (None, "none") and rapl_e:
        rapl_ok = True
        active.append("RAPL")
        parts = "  ".join(f"{k}={v} J" for k, v in rapl_e.items())
        lines.append(f"  [OK] RAPL energy ({rapl_src})   {parts}")
    else:
        lines.append("  [!!] RAPL energy            no source (Scaphandre/sysfs) — or set RAPL_ENABLED=0")

    # --- wattmeter (power) ---
    ns = probe.get("power_samples", 0)
    if ns:
        active.append("wattmeter")
        lines.append(f"  [OK] Wattmeter (Tasmota)    {ns} power sample(s)")
    elif probe.get("wattmeter_http") in (None, "(disabled)"):
        lines.append("  [--] Wattmeter              disabled")
    else:
        lines.append(f"  [!!] Wattmeter              no response from {probe.get('wattmeter_http')} "
                     "— or set WATTMETER_ENABLED=0")

    # --- CPU / memory (per-container) ---
    sysd = probe.get("system")
    src = probe.get("system_source")
    if sysd:
        system_ok = True
        active.append("CPU/mem")
        nc = sysd.get("containers")
        extra = f"  ({nc} container(s))" if nc else ""
        lines.append(f"  [OK] CPU/mem ({src})       "
                     f"cpu={sysd.get('cpu_pct')}%  mem={sysd.get('mem_used_mi')} MiB{extra}")
    elif src == "docker":
        if probe.get("docker_reachable"):
            system_ok = True   # daemon reachable → metrics WILL be captured during the run
            active.append("CPU/mem")
            lines.append("  [..] CPU/mem (docker)       daemon OK, 0 container — normal before "
                         "deploy; captured live from `docker stats` during the run")
        else:
            lines.append(f"  [!!] CPU/mem (docker)       daemon UNREACHABLE at "
                         f"{probe.get('docker_host')}  (check DOCKER_HOST / :2375 / network)")
    elif src == "psutil":
        lines.append("  [!!] CPU/mem (psutil)       psutil unavailable (pip install psutil)")

    # --- verdict --- (CPU/mem required; energy sources may be disabled)
    lines.append("")
    if system_ok and rapl_ok:
        lines.append(f"VERDICT: ✅ ALL OK — {' + '.join(active) or 'no source'} ready to record.")
        all_ok = True
    elif not active:
        lines.append("VERDICT: ❌ NOTHING responds — check Scaphandre / Tasmota / docker / network "
                     "(or disable the energy sources).")
        all_ok = False
    else:
        missing = []
        if not rapl_ok:
            missing.append("RAPL (enable a source or RAPL_ENABLED=0)")
        if not system_ok:
            missing.append("CPU/mem")
        lines.append(f"VERDICT: ⚠️  PARTIAL — missing: {', '.join(missing)}.")
        all_ok = False
    return "\n".join(lines), all_ok


def cmd_check(args) -> int:
    probe = energy_probe(args.seconds, BenchConfig.from_env())
    text, all_ok = _format_check(probe)
    print(text)
    if args.json:
        print("\n--- raw probe ---")
        print(json.dumps(probe, indent=2, ensure_ascii=False))
    return 0 if all_ok else 1


def cmd_aggregate(args) -> int:
    from bench.aggregate import aggregate
    cfg = BenchConfig.from_env()
    out = aggregate(args.results_root or cfg.results_root, args.out)
    print(out)
    return 0


def cmd_report(args) -> int:
    from bench.report import generate_report
    cfg = BenchConfig.from_env()
    out = generate_report(args.results_root or cfg.results_root, args.out,
                          compile_pdf_flag=not args.no_pdf)
    print(out)
    return 0


def cmd_down(args) -> int:
    """Best-effort teardown of all infra (cleanup)."""
    cfg = BenchConfig.from_env()
    for name in list_infra():
        try:
            INFRA[name].make_backend(cfg).teardown()
        except Exception as e:
            logging.warning("teardown %s: %s", name, e)
    return 0


def cmd_list(args) -> int:
    print("Infrastructures:")
    for name in list_infra():
        inf = INFRA[name]
        vs = f" | variants: {', '.join(inf.variant_names())}" if inf.variants else ""
        print(f"  - {name:<20} svc={inf.scalable_service:<12} host={inf.host_url}{vs}")
    print(f"\nControllers: {', '.join(CONTROLLER_KINDS)}")
    return 0


def main() -> int:
    _setup_logging()
    p = argparse.ArgumentParser(description="SoY-locust load-experiment driver")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("run", help="run an experiment")
    pr.add_argument("--infra", required=True, choices=list_infra())
    pr.add_argument("--controller", default="none", choices=CONTROLLER_KINDS)
    pr.add_argument("--loadshape", default=None)
    pr.add_argument("--locustfile", default=None)
    pr.add_argument("--host", default=None)
    pr.add_argument("--users", type=int, default=100)
    pr.add_argument("--spawn-rate", type=int, default=50)
    pr.add_argument("--run-time", default="120s")
    pr.add_argument("--target-util", type=float, default=0.5)
    pr.add_argument("--min-replicas", type=int, default=None)
    pr.add_argument("--max-replicas", type=int, default=None)
    pr.add_argument("--fixed-replicas", type=int, default=None,
                    help="for --controller manual")
    pr.add_argument("--schedule", default=None,
                    help="manual plan 't:r,...' e.g.: 0:1,60:3,120:2")
    pr.add_argument("--initial-replicas", type=int, default=None)
    pr.add_argument("--control-period", type=float, default=5.0)
    pr.add_argument("--variant", default=None,
                    help="infra variant (e.g. msdemo: node|go|python|java|csharp)")
    pr.add_argument("--web-port", type=int, default=8089)
    pr.add_argument("--tag", default=None)
    pr.add_argument("--rep", type=int, default=0)
    pr.add_argument("--uopt-method", default="scip", choices=["scip", "casadi"])
    pr.add_argument("--hpa-tolerance", type=float, default=0.10)
    pr.add_argument("--hpa-downscale", type=float, default=60.0)
    pr.add_argument("--rps-per-user", type=float, default=1.0,
                    help="throughput/iterations per second per user (constant_throughput)")
    pr.add_argument("--capacity", action="store_true",
                    help="capacity test: stepped ramp + breaking-point detection")
    pr.add_argument("--fail-threshold", type=float, default=0.02,
                    help="max failure rate before breaking (default 2%%)")
    pr.add_argument("--sla-p95-ms", type=float, default=None,
                    help="p95 latency SLA in ms (breaks if exceeded)")
    pr.add_argument("--break-samples", type=int, default=3)
    pr.add_argument("--no-stop-on-break", action="store_true",
                    help="do not stop the run at the breaking point")
    pr.add_argument("--keep-up", action="store_true", help="do not teardown at the end")
    pr.add_argument("--dry-run", action="store_true",
                    help="without Docker/Locust (fake backend + synthetic signal)")
    pr.set_defaults(func=cmd_run)

    pm = sub.add_parser("matrix", help="unroll a YAML matrix")
    pm.add_argument("--file", default="experiments.yaml")
    pm.add_argument("--infra", default=None,
                    help="run ONLY this infra's entries (one stack instead of all)")
    pm.add_argument("--shape", default=None,
                    help="run ONLY this loadshape (filename stem, e.g. cyclical)")
    pm.add_argument("--dry-run", action="store_true")
    pm.add_argument("--force", action="store_true",
                    help="re-run even runs whose result.json already exists (no resume)")
    pm.set_defaults(func=cmd_matrix)

    pc = sub.add_parser("check", help="probe energy/system (energy_probe)")
    pc.add_argument("--seconds", type=float, default=4.0)
    pc.add_argument("--json", action="store_true", help="also dump the raw probe JSON")
    pc.set_defaults(func=cmd_check)

    pa = sub.add_parser("aggregate", help="aggregate results → summary.csv")
    pa.add_argument("--results-root", default=None)
    pa.add_argument("--out", default=None)
    pa.set_defaults(func=cmd_aggregate)

    prep = sub.add_parser("report", help="figures + LaTeX/PDF report (white paper)")
    prep.add_argument("--results-root", default=None)
    prep.add_argument("--out", default=None)
    prep.add_argument("--no-pdf", action="store_true", help="generate .tex without compiling")
    prep.set_defaults(func=cmd_report)

    pd = sub.add_parser("down", help="teardown of all infra (cleanup)")
    pd.set_defaults(func=cmd_down)

    pl = sub.add_parser("list", help="list infra/controllers/variants")
    pl.set_defaults(func=cmd_list)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
