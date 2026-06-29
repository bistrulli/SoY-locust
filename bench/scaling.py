"""Scaling loop: sample → decide → act → log.

Independent of the controller (uopt / hpa / manual / none): it calls
``controller.decide(ctx)`` and applies the result via the backend. Runs in a
daemon thread; one CSV row per tick documents the decision.
"""
from __future__ import annotations

import csv
import logging
import threading
import time
from pathlib import Path
from typing import Optional

from .backends import Backend
from .config import CFG, BenchConfig
from .controllers import ControlContext, Controller
from .infra import Infra
from .signals import SignalSource

logger = logging.getLogger(__name__)


class ScalingLoop:
    def __init__(self, infra: Infra, backend: Backend, signal: SignalSource,
                 controller: Controller, run_tag: str,
                 target_utilization: float = 0.5,
                 control_period_s: float = 5.0,
                 cfg: Optional[BenchConfig] = None):
        self.infra = infra
        self.backend = backend
        self.signal = signal
        self.controller = controller
        self.run_tag = run_tag
        self.target_utilization = target_utilization
        self.control_period_s = control_period_s
        self.cfg = cfg or CFG

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.csv_path = self.cfg.results_path(run_tag, "scaling",
                                              f"{infra.scalable_service}.csv")

    # --- lifecycle ---
    def start(self) -> "ScalingLoop":
        self._thread = threading.Thread(target=self.run, name=f"scaling-{self.infra.name}",
                                        daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.control_period_s * 2 + 5)

    # --- loop ---
    def run(self) -> None:
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.csv_path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow([
                "ts", "elapsed_s", "controller", "replicas_cur", "replicas_desired",
                "cpu_util_per_replica", "target_util", "arrival_rate",
                "throughput", "response_time", "service_time", "active_users",
            ])
            t0 = time.time()
            svc = self.infra.scalable_service
            while not self._stop.is_set():
                try:
                    sig = self.signal.sample()
                    elapsed = time.time() - t0
                    ctx = ControlContext(
                        elapsed_s=elapsed,
                        current_replicas=sig.replicas or self.backend.replicas(svc),
                        cpu_util_per_replica=sig.cpu_util_per_replica,
                        target_utilization=self.target_utilization,
                        arrival_rate=sig.arrival_rate,
                        service_time=sig.service_time,
                        active_users=sig.active_users,
                        min_replicas=self.infra.min_replicas,
                        max_replicas=self.infra.max_replicas,
                    )
                    desired = self.controller.decide(ctx)
                    if desired != ctx.current_replicas and desired > 0:
                        try:
                            self.backend.scale(svc, desired)
                        except Exception as e:
                            logger.error("scale %s->%d failed: %s", svc, desired, e)
                    w.writerow([
                        round(time.time(), 3), round(elapsed, 2), self.controller.kind,
                        ctx.current_replicas, desired,
                        sig.cpu_util_per_replica, self.target_utilization,
                        sig.arrival_rate, sig.throughput, sig.response_time,
                        sig.service_time, sig.active_users,
                    ])
                    fh.flush()
                except Exception as e:  # a tick must never kill the loop
                    logger.exception("scaling tick errored: %s", e)
                self._stop.wait(self.control_period_s)
        logger.info("Scaling loop stopped (%s).", self.csv_path)
