"""Aggregation of results → a "tidy" CSV ready for the white paper figures.

Walks ``results/<tag>/`` and produces ``results/summary.csv``: **one row per run**
combining energy (RAPL + wall), system resources (CPU/mem/IO), scaling
behavior (replica·seconds, number of actions) and Locust perf (throughput, p95/p99
latency, failures), plus the derived energy/request metrics.
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Output columns (stable order for the figures)
COLUMNS = [
    "tag", "infra", "controller", "variant", "loadshape", "rep", "scalable_service",
    "duration_s",
    # energy
    "rapl_package_J", "rapl_cores_J", "rapl_dram_J", "rapl_host_J",
    "wall_energy_J", "watts_peak", "wall_over_rapl",
    # system (app)
    "cpu_pct_avg", "cpu_pct_peak", "mem_used_mi_avg", "mem_used_mi_peak",
    "disk_read_mb", "disk_write_mb", "net_recv_mb", "net_sent_mb",
    # scaling
    "replicas_mean", "replicas_max", "replica_seconds", "scale_actions", "cpu_util_mean",
    # Locust perf
    "requests", "failures", "fail_ratio", "rps", "rt_avg_ms", "rt_p95_ms", "rt_p99_ms",
    "users_max",
    # capacity (breaking point)
    "knee_rps", "breaking_rps", "breaking_users", "max_rps", "broken",
    # derived energy/request
    "wall_J_per_req", "rapl_package_J_per_req",
]


def _num(x, default=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _scaling_summary(csv_path: Path) -> dict:
    if not csv_path.exists():
        return {}
    rows = list(csv.DictReader(open(csv_path)))
    if not rows:
        return {}
    el = [_num(r.get("elapsed_s")) for r in rows]
    cur = [_num(r.get("replicas_cur")) for r in rows]
    des = [_num(r.get("replicas_desired")) for r in rows]
    util = [_num(r.get("cpu_util_per_replica")) for r in rows]
    replica_seconds = 0.0
    for i in range(len(rows) - 1):
        replica_seconds += cur[i] * max(0.0, el[i + 1] - el[i])
    total = (el[-1] - el[0]) if len(el) > 1 else 0.0
    actions = sum(1 for r in rows
                  if _num(r.get("replicas_desired")) != _num(r.get("replicas_cur")))
    return {
        "replicas_mean": round(replica_seconds / total, 3) if total else (cur[0] if cur else 0),
        "replicas_max": int(max(cur + des)) if (cur or des) else 0,
        "replica_seconds": round(replica_seconds, 1),
        "scale_actions": actions,
        "cpu_util_mean": round(sum(util) / len(util), 4) if util else 0.0,
        "users_max": round(max(_num(r.get("active_users")) for r in rows), 1),
    }


def _locust_summary(prefix: Path) -> dict:
    """Read the 'Aggregated' row from ``<prefix>_stats.csv``."""
    stats = Path(str(prefix) + "_stats.csv")
    if not stats.exists():
        return {}
    agg = None
    for r in csv.DictReader(open(stats)):
        if r.get("Name") in ("Aggregated", "Total"):
            agg = r
            break
    if not agg:
        return {}
    req = _num(agg.get("Request Count"))
    fails = _num(agg.get("Failure Count"))
    return {
        "requests": int(req),
        "failures": int(fails),
        "fail_ratio": round(fails / req, 4) if req else 0.0,
        "rps": _num(agg.get("Requests/s")),
        "rt_avg_ms": _num(agg.get("Average Response Time")),
        "rt_p95_ms": _num(agg.get("95%")),
        "rt_p99_ms": _num(agg.get("99%")),
    }


def summarize_run(run_dir: Path) -> Optional[dict]:
    cfg = _read_json(run_dir / "config.json")
    if not cfg:
        return None
    spec = cfg.get("spec", {})
    res = cfg.get("resolved", {})
    svc = res.get("scalable_service", "")
    metrics = _read_json(run_dir / "metrics" / "load.metrics.json")
    rsrc = metrics.get("resources", {})
    rapl = metrics.get("rapl", {})
    watt = metrics.get("wattmeter", {})
    loadshape = res.get("loadshape") or spec.get("loadshape") or ""

    row = {c: "" for c in COLUMNS}
    row.update({
        "tag": res.get("tag", run_dir.name),
        "infra": spec.get("infra", ""),
        "controller": spec.get("controller", ""),
        "variant": res.get("variant", ""),
        "loadshape": Path(loadshape).stem if loadshape else "",
        "rep": spec.get("repetition", 0),
        "scalable_service": svc,
        "duration_s": metrics.get("duration_s", ""),
        "rapl_package_J": rapl.get("package_J", ""),
        "rapl_cores_J": rapl.get("cores_J", ""),
        "rapl_dram_J": rapl.get("dram_J", ""),
        "rapl_host_J": rapl.get("host_J", ""),
        "wall_energy_J": watt.get("wall_energy_J", ""),
        "watts_peak": watt.get("watts_peak", ""),
        "wall_over_rapl": metrics.get("wall_over_rapl", ""),
        "cpu_pct_avg": rsrc.get("cpu_pct_avg", ""),
        "cpu_pct_peak": rsrc.get("cpu_pct_peak", ""),
        "mem_used_mi_avg": rsrc.get("mem_used_mi_avg", ""),
        "mem_used_mi_peak": rsrc.get("mem_used_mi_peak", ""),
        "disk_read_mb": rsrc.get("disk_read_mb", ""),
        "disk_write_mb": rsrc.get("disk_write_mb", ""),
        "net_recv_mb": rsrc.get("net_recv_mb", ""),
        "net_sent_mb": rsrc.get("net_sent_mb", ""),
    })
    row.update(_scaling_summary(run_dir / "scaling" / f"{svc}.csv"))
    row.update(_locust_summary(run_dir / "locust"))

    # capacity (from result.json)
    cap = _read_json(run_dir / "result.json").get("capacity", {})
    if cap:
        row.update({
            "knee_rps": cap.get("knee_rps", ""),
            "breaking_rps": cap.get("breaking_rps", ""),
            "breaking_users": cap.get("breaking_users", ""),
            "max_rps": cap.get("max_rps", ""),
            "broken": cap.get("broken", ""),
        })

    # derived energy/request
    req = _num(row.get("requests"))
    if req:
        if _num(watt.get("wall_energy_J")):
            row["wall_J_per_req"] = round(_num(watt["wall_energy_J"]) / req, 5)
        if _num(rapl.get("package_J")):
            row["rapl_package_J_per_req"] = round(_num(rapl["package_J"]) / req, 5)
    return row


def aggregate(results_root: str, out_path: Optional[str] = None) -> str:
    root = Path(results_root)
    out = Path(out_path) if out_path else (root / "summary.csv")
    rows: List[dict] = []
    for run_dir in sorted(root.iterdir()) if root.exists() else []:
        if run_dir.is_dir() and (run_dir / "config.json").exists():
            r = summarize_run(run_dir)
            if r:
                rows.append(r)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    logger.info("Aggregation: %d run(s) → %s", len(rows), out)
    return str(out)
