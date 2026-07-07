"""End-to-end orchestration of an experiment.

    preflight (energy_probe) → deploy backend → initial replicas → Phase.start
    → (if autoscaler) ScalingLoop → Locust load → stop → Phase.stop → teardown
    → results under results/<tag>/.

``--dry-run`` replaces Docker/Locust with a dummy backend + a synthetic signal
to validate the whole sample→decide→scale chain without infra (the psutil system
metrics remain real).
"""
from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

import os

from .backends import StubBackend, exec_in_container, _heal_enabled
from .capacity import CapacityProbe
from .config import CFG, BenchConfig
from .controllers import make_controller
from .infra import REPO_ROOT, get_infra
from .locustctl import LocustRunner, build_locust_cmd
from .metrics import Phase, energy_probe
from .scaling import ScalingLoop
from .signals import Signal, SignalSource, make_signal

logger = logging.getLogger(__name__)

try:
    from pytimeparse import parse as _timeparse
except Exception:  # pragma: no cover
    _timeparse = None


def parse_seconds(s, default: float = 120.0) -> float:
    if s is None:
        return default
    if isinstance(s, (int, float)):
        return float(s)
    if _timeparse:
        v = _timeparse(s)
        if v:
            return float(v)
    try:
        return float(str(s).rstrip("s"))
    except ValueError:
        return default


@dataclass
class ExperimentSpec:
    infra: str
    controller: str = "none"               # none|manual|manual-sched|hpa|uopt|openclass
    loadshape: Optional[str] = None
    locustfile: Optional[str] = None
    host: Optional[str] = None
    users: int = 100
    spawn_rate: int = 50
    run_time: str = "120s"
    target_utilization: float = 0.5
    min_replicas: Optional[int] = None
    max_replicas: Optional[int] = None
    fixed_replicas: Optional[int] = None
    schedule: Optional[List[list]] = None  # [[t_s, replicas], ...]
    initial_replicas: Optional[int] = None
    extra_replicas: Optional[dict] = None  # fixed per-service overrides, e.g. {"gateway":2,"ms-other":2}
    control_period_s: float = 5.0
    variant: Optional[str] = None
    web_port: int = 8089
    tag: Optional[str] = None
    label: Optional[str] = None            # parameter-sweep suffix in the tag (keeps rep)
    repetition: int = 0
    uopt_method: str = "scip"
    hpa_tolerance: float = 0.10
    hpa_downscale_s: float = 60.0
    # --- normalized throughput ---
    rps_per_user: float = 1.0              # iterations/s per user (constant_throughput)
    # --- capacity test (breaking point) ---
    capacity: bool = False                 # stepped ramp + breaking-point detection
    fail_threshold: float = 0.02           # max failure rate before "breaking"
    sla_p95_ms: Optional[float] = None     # p95 latency SLA (optional)
    break_samples: int = 3                 # consecutive measurements above the threshold
    stop_on_break: bool = True             # stop the run at the breaking point
    keep_up: bool = False                  # do not teardown at the end
    dry_run: bool = False


# --- synthetic signal for --dry-run ----------------------------------------

class SyntheticSignal(SignalSource):
    """Bell-shaped load: CPU rises then falls, to exercise scaling."""

    def __init__(self, backend, infra, period_s: float = 6.0):
        self.backend = backend
        self.infra = infra
        self.t0 = time.time()
        self.period = period_s

    def sample(self) -> Signal:
        rep = self.backend.replicas(self.infra.scalable_service)
        el = time.time() - self.t0
        # bell: peak at half of the window
        frac = min(1.0, el / self.period)
        util = 0.9 * math.sin(math.pi * frac) + 0.05
        users = 100 * util
        thr = max(1.0, users)
        return Signal(replicas=rep, cpu_util_per_replica=round(util, 3),
                      arrival_rate=round(thr, 2), throughput=round(thr, 2),
                      response_time=0.02, active_users=round(users, 1),
                      service_time=0.02)


def _tag(spec: ExperimentSpec, infra) -> str:
    if spec.tag:
        return spec.tag
    shape = Path(spec.loadshape).stem if spec.loadshape else "noshape"
    variant = spec.variant or infra.default_variant
    lbl = f"{spec.label}__" if spec.label else ""
    return f"{infra.name}__{spec.controller}__{variant}__{shape}__{lbl}rep{spec.repetition}"


def _initial_replicas(spec: ExperimentSpec, infra) -> int:
    if spec.initial_replicas is not None:
        return spec.initial_replicas
    if spec.controller in ("manual", "manual-fixed", "fixed") and spec.fixed_replicas:
        return spec.fixed_replicas
    if spec.controller in ("manual-sched", "schedule", "sched") and spec.schedule:
        return int(spec.schedule[0][1])
    # Honour an explicit min_replicas floor for the INITIAL deploy: a controller
    # asked to never run below N must not be deployed at 1 (on v4/Swarm a single
    # `node` replica never becomes reachable, so uopt reads util=0 -> service_time=0
    # -> never scales -> 100% ConnectionRefused). Falls back to the infra floor.
    if spec.min_replicas is not None:
        return max(int(spec.min_replicas), infra.min_replicas)
    return infra.min_replicas


def _apply_db_fixups(infra, backend, cfg: BenchConfig,
                     container_timeout_s: float = 60.0,
                     ready_timeout_s: float = 60.0) -> None:
    """Re-apply the infra's DB fixups on the fresh deploy (see infra.DbFixup).

    The DB container is recreated on every run, so seeded data that has gone stale
    (e.g. v4's expired ``plagesession`` window, which makes every login fail) must
    be corrected each time, right after deploy and before the load starts. Runs
    ``psql`` inside the container, so no DB port needs to be exposed. Best-effort:
    a failure is logged loudly (the run would show all-failures) but does not abort.
    """
    for fx in getattr(infra, "db_fixups", None) or []:
        # 1) wait for the service container to be scheduled (swarm deploys async)
        deadline = time.time() + container_timeout_s
        cid = None
        while time.time() < deadline:
            ids = backend.containers(fx.service)
            if ids:
                cid = ids[0]
                break
            time.sleep(2)
        if not cid:
            logger.warning("DB fixup skipped: no container for service %r after %.0fs",
                           fx.service, container_timeout_s)
            continue
        # 2) wait for the DB to accept connections
        deadline = time.time() + ready_timeout_s
        while time.time() < deadline:
            res = exec_in_container(cid, ["pg_isready", "-U", fx.user, "-d", fx.db],
                                    cfg, check=False, capture=True)
            if res.returncode == 0:
                break
            time.sleep(2)
        else:
            logger.warning("DB fixup: %s/%s not ready after %.0fs — applying anyway",
                           fx.service, fx.db, ready_timeout_s)
        # 3) apply the SQL
        res = exec_in_container(
            cid, ["psql", "-U", fx.user, "-d", fx.db, "-v", "ON_ERROR_STOP=1",
                  "-c", fx.sql], cfg, check=False, capture=True)
        if res.returncode == 0:
            logger.info("DB fixup applied on %s/%s: %s", fx.service, fx.db,
                        (res.stdout or "").strip() or "ok")
        else:
            logger.warning("DB fixup FAILED on %s/%s (rc=%d): %s", fx.service, fx.db,
                           res.returncode, (res.stderr or res.stdout or "").strip())


def _ensure_service_scheduled(infra, backend, scales: dict, cfg: BenchConfig,
                              settle_timeout_s: float = 120.0,
                              max_heals: int = 2) -> dict:
    """Guarantee the scalable service actually has RUNNING containers after deploy.

    On the v4 remote Swarm the dispatcher can wedge (tasks stuck ``New``, 0 running):
    ``stack deploy`` "succeeds" but no ``node`` container starts, so the whole run is
    100 % ConnectionRefused — and, unattended, every subsequent run too (this is exactly
    what killed the overnight ``v4uopt`` campaign: 43 consecutive 0-node runs). This
    detects the wedge (0 running containers for the scalable service after
    ``settle_timeout_s``) and self-heals by restarting docker on the app host, then
    re-deploying and re-scaling — up to ``max_heals`` times.

    Requires the FULL desired replica count (``want``, from ``scales``) to be running
    before declaring victory — not just "at least 1". A partial recovery (e.g. 2 of 6
    replicas up) used to be accepted as "healed", starting the load against an
    under-provisioned deploy and inflating its failure rate; now it keeps healing (up to
    ``max_heals``) until the full count is reached or gives up.

    Returns an event record (``{heals, healed, running_after}``) for ``result.json`` so
    a healed run is traceable. No-op for backends without a ``heal`` capability (compose
    infras never wedge this way) or when disabled via ``SOY_SWARM_HEAL=0``.
    """
    svc = infra.scalable_service
    want = int(scales.get(svc, 1)) or 1
    events = {"heals": 0, "healed": False, "running_after": None, "want": want, "ok": False}
    can_heal = callable(getattr(backend, "heal", None)) and _heal_enabled()

    if hasattr(backend, "wait_running"):
        running = backend.wait_running(svc, min_count=want, timeout_s=settle_timeout_s)
    else:
        running = want  # backend can't report (dry-run/compose) → assume fine
    events["running_after"] = running

    if running >= want or not can_heal:
        events["ok"] = running >= want
        if running < want:
            logger.error("Service %r has only %d/%d running containers and healing is "
                         "unavailable/disabled — this run will likely fail or be "
                         "under-provisioned.", svc, running, want)
        return events

    # fewer than wanted running => wedged/degraded dispatcher: heal loop
    for attempt in range(1, max_heals + 1):
        logger.error("⚠️  Swarm wedge detected: %r has %d/%d running containers after "
                     "%.0fs. Self-heal attempt %d/%d…",
                     svc, running, want, settle_timeout_s, attempt, max_heals)
        if not backend.heal():
            logger.error("Swarm heal attempt %d/%d could not restore docker.",
                         attempt, max_heals)
            continue
        events["heals"] = attempt
        # re-apply DB fixups and re-scale on the fresh daemon, then re-check
        try:
            _apply_db_fixups(infra, backend, cfg)
        except Exception as e:
            logger.warning("post-heal DB fixup: %s", e)
        try:
            backend.scale_many(scales)
        except Exception as e:
            logger.warning("post-heal scale: %s", e)
        running = backend.wait_running(svc, min_count=want, timeout_s=settle_timeout_s)
        events["running_after"] = running
        if running >= want:
            logger.warning("✅ Swarm healed: %r now has %d/%d running container(s) after "
                           "%d restart(s).", svc, running, want, attempt)
            events["healed"] = True
            events["ok"] = True
            return events

    logger.error("❌ Swarm still wedged after %d heal attempt(s): %r has %d/%d running "
                 "containers. Proceeding — this run will likely fail or be "
                 "under-provisioned.", max_heals, svc, running, want)
    return events


def _wait_for_app_ready(host: str, timeout_s: float = 120.0,
                        interval_s: float = 2.0) -> bool:
    """Poll the app entry URL until it accepts connections (any HTTP reply).

    The stack deploys asynchronously and the app (e.g. v4 `node` waiting on its DB)
    can take longer than the fixed post-deploy sleep to start listening. Without
    this, Locust hits a not-yet-ready app, every request fails with ConnectionRefused
    and a capacity run misreads it as an instant breaking point. Any HTTP status
    (even 404/401/500) means the app is LISTENING → ready. Returns False if the host
    never answers in time (the run starts anyway, so this is best-effort).
    """
    import urllib.error
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.time() + timeout_s
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            opener.open(host, timeout=5)
            logger.info("App ready at %s (%d probe(s)).", host, attempt)
            return True
        except urllib.error.HTTPError:
            # an HTTP error status still means the listener is up → ready
            logger.info("App ready at %s (HTTP error but listening, %d probe(s)).",
                        host, attempt)
            return True
        except (urllib.error.URLError, OSError):
            time.sleep(interval_s)
    logger.warning("App not ready at %s after %.0fs — starting load anyway.",
                   host, timeout_s)
    return False


def run_experiment(spec: ExperimentSpec, cfg: Optional[BenchConfig] = None) -> dict:
    cfg = cfg or CFG
    infra = get_infra(spec.infra)
    min_r = spec.min_replicas if spec.min_replicas is not None else infra.min_replicas
    max_r = spec.max_replicas if spec.max_replicas is not None else infra.max_replicas
    variant = spec.variant or infra.default_variant
    tag = _tag(spec, infra)
    host = spec.host or infra.host(cfg)
    locustfile = spec.locustfile or infra.locustfile()
    loadshape_rel = spec.loadshape or ("bench/loadshapes/capacity.py" if spec.capacity else None)
    loadshape = infra.path(loadshape_rel) if loadshape_rel else None

    run_dir = cfg.results_path(tag)
    run_dir.mkdir(parents=True, exist_ok=True)
    logger.info("=== Experiment %s (infra=%s, ctrl=%s, variant=%s) ===",
                tag, infra.name, spec.controller, variant)

    # config.json
    config = {
        "spec": asdict(spec),
        "resolved": {
            "tag": tag, "host": host, "locustfile": locustfile, "loadshape": loadshape,
            "variant": variant, "min_replicas": min_r, "max_replicas": max_r,
            "scalable_service": infra.scalable_service,
            "compose_files": infra.compose_files_for(variant)
            if infra.backend_kind == "compose" else [infra.path(infra.compose_file)],
        },
        "config": cfg.to_dict(),
    }
    (run_dir / "config.json").write_text(json.dumps(config, indent=2))

    # energy preflight
    probe = energy_probe(2.0, cfg)
    logger.info("Energy preflight: sources=%s", probe.get("labels") or "(none)")
    (run_dir / "energy_probe.json").write_text(json.dumps(probe, indent=2))

    backend = (StubBackend(start_replicas=_initial_replicas(spec, infra))
               if spec.dry_run else infra.make_backend(cfg, variant))
    controller = make_controller(
        spec.controller, target_utilization=spec.target_utilization,
        min_replicas=min_r, max_replicas=max_r, fixed_replicas=spec.fixed_replicas,
        schedule=spec.schedule, tolerance=spec.hpa_tolerance,
        downscale_stabilization_s=spec.hpa_downscale_s, uopt_method=spec.uopt_method)

    phase = None
    loop = None
    locust = None
    probe = None
    summary = {"tag": tag}
    try:
        # PRELIMINARY cleanup: start from a clean state even if a previous run
        # was interrupted before its teardown (otherwise `up -d` would reuse the existing one).
        if not spec.dry_run:
            try:
                backend.teardown()
                time.sleep(2)
            except Exception as e:
                logger.debug("pre-cleanup: %s", e)
        backend.deploy(wait=not spec.dry_run)
        initial = _initial_replicas(spec, infra)
        if not spec.dry_run:
            # re-open the seeded DB session window etc. before any load (v4 login)
            _apply_db_fixups(infra, backend, cfg)
            # Scale the scalable service AND all fixed per-service overrides in ONE
            # call: a per-service `up --scale X=n X` reconciles X's depends_on back to
            # 1, which would silently reset an earlier-scaled dependency (e.g. scaling
            # checkoutservice resets productcatalog/currency/cart back to 1).
            scales = {infra.scalable_service: initial}
            for svc, n in (spec.extra_replicas or {}).items():
                if svc != infra.scalable_service:
                    scales[svc] = int(n)
            backend.scale_many(scales)
            logger.info("Fixed replicas: %s",
                        ", ".join(f"{s}={n}" for s, n in scales.items()))
            # Guard against a wedged remote Swarm dispatcher (v4): if the scalable
            # service scheduled 0 containers, restart docker on the app host and retry
            # (self-heal) so a stuck daemon does not silently turn the run — and every
            # subsequent run — into 100 % ConnectionRefused. Best-effort; recorded below.
            heal_events = _ensure_service_scheduled(infra, backend, scales, cfg)
            if heal_events.get("heals") or not heal_events.get("ok"):
                summary["swarm_heal"] = heal_events
            time.sleep(5)
            # wait for the app to actually listen before the load starts, else the
            # first requests fail with ConnectionRefused (misread as a breaking point)
            _wait_for_app_ready(host)

        # In dry-run we measure the local machine (psutil); otherwise the resolved source
        # (docker stats on the remote app) filtered on the infra's project.
        sys_src = "psutil" if spec.dry_run else None
        phase = Phase("load", tag, cfg, system_source=sys_src,
                      name_filter="" if spec.dry_run else infra.project).start()

        if spec.controller != "none":
            if spec.dry_run:
                signal: SignalSource = SyntheticSignal(
                    backend, infra, period_s=min(parse_seconds(spec.run_time, 6), 8))
            else:
                signal = make_signal(infra, backend,
                                     locust_web_url=f"http://localhost:{spec.web_port}",
                                     cfg=cfg)
            loop = ScalingLoop(infra, backend, signal, controller, tag,
                               target_utilization=spec.target_utilization,
                               control_period_s=spec.control_period_s, cfg=cfg).start()

        # --- load ---
        if spec.dry_run:
            secs = min(parse_seconds(spec.run_time, 6), 8)
            logger.info("[dry-run] simulating load for %.1fs", secs)
            time.sleep(secs)
        else:
            # normalized throughput: the Locust subprocess inherits this variable
            os.environ["BENCH_RPS_PER_USER"] = str(spec.rps_per_user)
            # per-infra login fixtures (v4 DB uses @yopmail.com, v5 @yopmail.fr).
            # set OR clear so the value never leaks from one infra to the next.
            if infra.users_csv:
                os.environ["SOY_USERS_CSV"] = infra.path(infra.users_csv)
            else:
                os.environ.pop("SOY_USERS_CSV", None)
            csv_prefix = str(run_dir / "locust")
            cmd = build_locust_cmd(
                locustfile, loadshape, host, csv_prefix,
                run_time=spec.run_time, users=spec.users, spawn_rate=spec.spawn_rate,
                web_port=spec.web_port)
            locust = LocustRunner(cmd, cwd=str(REPO_ROOT),
                                  log_path=str(run_dir / "locust.log")).start()
            # capacity probe: detects the breaking point (and stops if requested)
            web_url = f"http://localhost:{spec.web_port}"
            probe = CapacityProbe(
                web_url, tag, infra.scalable_service,
                fail_threshold=spec.fail_threshold, sla_p95_ms=spec.sla_p95_ms,
                break_samples=spec.break_samples,
                control_period_s=min(spec.control_period_s, 2.0),
                # only capacity tests stop at the breaking point; normal runs go the
                # full run_time even if the failure rate briefly exceeds the threshold.
                on_break=(locust.stop if (spec.capacity and spec.stop_on_break) else None),
                cfg=cfg).start()
            locust.wait(timeout=parse_seconds(spec.run_time, 120) + 180)
    finally:
        if loop:
            loop.stop()
        if probe:
            summary["capacity"] = probe.stop()
        if phase:
            summary["metrics"] = phase.stop()
        if backend is not None and not spec.keep_up:
            try:
                backend.teardown()
            except Exception as e:
                logger.error("teardown: %s", e)

    if spec.dry_run and isinstance(backend, StubBackend):
        summary["scale_history"] = backend.history
    (run_dir / "result.json").write_text(json.dumps(summary, indent=2))
    logger.info("=== Finished %s → %s ===", tag, run_dir)
    return summary
