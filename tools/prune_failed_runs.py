#!/usr/bin/env python3
"""Delete result dirs of runs where the scalable service never ran (Swarm wedge).

``xp.sh start`` auto-resumes by SKIPPING any run whose ``result.json`` already exists.
When a night's campaign hits a wedged Swarm dispatcher, the dead runs still leave a
(useless, 100 %-ConnectionRefused) ``result.json`` behind — so a plain re-launch skips
exactly the runs you need to redo. This prunes those dead dirs so the re-launch
re-executes them; the *valid* runs (baselines, healthy hpa, …) are kept.

A run is "dead" when the scalable service (read from its ``config.json`` →
``resolved.scalable_service``) had **0 running containers** during the run
(``result.json`` → ``metrics.containers`` has no entry for it) — i.e. the app never
came up. Cross-checked against the Locust failure rate when available.

Usage (dry-run by default — prints what WOULD be deleted, deletes nothing):
    python tools/prune_failed_runs.py results/v4uopt
    python tools/prune_failed_runs.py results/v4uopt --apply        # actually delete
    python tools/prune_failed_runs.py results/v4uopt --controller uopt   # only uopt cells
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
from pathlib import Path


def _running_scalable(run_dir: Path, scalable: str) -> int:
    """Count RUNNING containers of the scalable service recorded in result.json."""
    try:
        j = json.loads((run_dir / "result.json").read_text())
    except Exception:
        return -1  # unreadable => treat as unknown (not pruned)
    conts = (j.get("metrics") or {}).get("containers") or {}
    # swarm container key looks like '<stack>_<service>.<slot>.<id>' → match '_<svc>.'
    pat = re.compile(rf"_{re.escape(scalable)}\.")
    n = sum(1 for k in conts if pat.search(k) or k.startswith(f"{scalable}."))
    return n


def _scalable_of(run_dir: Path) -> str | None:
    try:
        cfg = json.loads((run_dir / "config.json").read_text())
        return (cfg.get("resolved") or {}).get("scalable_service")
    except Exception:
        return None


def _fail_pct(run_dir: Path) -> float | None:
    ls = run_dir / "locust_stats.csv"
    if not ls.exists():
        return None
    try:
        with ls.open() as f:
            for r in csv.DictReader(f):
                if r.get("Name") == "Aggregated":
                    req = float(r.get("Request Count", 0) or 0)
                    nf = float(r.get("Failure Count", 0) or 0)
                    return round(100 * nf / req, 1) if req else None
    except Exception:
        return None
    return None


def _healed(run_dir: Path) -> bool:
    try:
        j = json.loads((run_dir / "result.json").read_text())
        return bool((j.get("swarm_heal") or {}).get("healed"))
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results_dir", help="campaign dir, e.g. results/v4uopt")
    ap.add_argument("--apply", action="store_true",
                    help="actually delete (default: dry-run, delete nothing)")
    ap.add_argument("--controller", default=None,
                    help="only consider runs of this controller (e.g. uopt)")
    args = ap.parse_args()

    root = Path(args.results_dir)
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2

    runs = sorted(p.parent for p in root.rglob("result.json"))
    dead, kept, healed_kept = [], 0, 0
    for run_dir in runs:
        name = run_dir.name
        if args.controller and f"__{args.controller}__" not in name:
            continue
        scalable = _scalable_of(run_dir)
        if not scalable:
            kept += 1
            continue
        nrun = _running_scalable(run_dir, scalable)
        if nrun == 0 and not _healed(run_dir):
            dead.append((run_dir, scalable, _fail_pct(run_dir)))
        else:
            kept += 1
            if _healed(run_dir):
                healed_kept += 1

    print(f"Scanned {len(runs)} run(s) under {root}")
    if healed_kept:
        print(f"  ({healed_kept} kept run(s) were self-healed mid-run — NOT pruned)")
    if not dead:
        print("No dead (0-running-container) runs found. Nothing to prune. ✅")
        return 0

    verb = "DELETING" if args.apply else "would delete"
    print(f"\n{len(dead)} dead run(s) ({verb}); {kept} kept:\n")
    for run_dir, scalable, fp in dead:
        print(f"  ✗ {run_dir.name}   (0 running {scalable!r}, fail={fp}%)")
        if args.apply:
            shutil.rmtree(run_dir, ignore_errors=True)

    if not args.apply:
        print(f"\nDry-run — nothing deleted. Re-run with --apply to remove the "
              f"{len(dead)} dir(s), then re-launch the campaign to redo them.")
    else:
        print(f"\nDeleted {len(dead)} dir(s). Re-launch the campaign to redo them "
              f"(auto-resume will now re-execute the pruned cells).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
