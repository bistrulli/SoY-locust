"""Interchangeable scaling controllers — the heart of the comparison.

All implement the same interface ``decide(ctx: ControlContext) -> int`` (desired
replica count). This is the **swap point uopt ↔ hpa ↔ manual**: the scaling
loop (``bench.scaling``) calls ``decide`` without knowing anything about the strategy.

  * ``UoptController``  — adapts the ``OPTCTRL`` optimization model ("uopt"),
                         with fallback to an M/M/S queuing formula if casadi/scip
                         is missing.
  * ``HPAController``   — reimplementation of the Kubernetes HPA v2 algorithm
                         (target utilization, tolerance, stabilization windows).
  * ``ManualFixed``     — constant replica count.
  * ``ManualSchedule``  — replica schedule (step function of time).
  * ``NoneController``  — changes nothing (no autoscaler).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ControlContext:
    """State passed to the controller at each tick."""

    elapsed_s: float = 0.0
    current_replicas: int = 1
    cpu_util_per_replica: float = 0.0   # fraction 0..1 of the CPU budget per replica
    target_utilization: float = 0.5     # target 0..1
    arrival_rate: float = 0.0           # req/s (λ)
    service_time: float = 0.0           # s/req
    active_users: float = 0.0
    min_replicas: int = 1
    max_replicas: int = 8


def _clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(int(n), hi))


class Controller:
    """Controller interface."""

    kind = "base"

    def decide(self, ctx: ControlContext) -> int:  # pragma: no cover - interface
        raise NotImplementedError

    def __str__(self) -> str:
        return self.kind


# =============================================================================
# No autoscaler
# =============================================================================

class NoneController(Controller):
    kind = "none"

    def decide(self, ctx: ControlContext) -> int:
        return ctx.current_replicas


# =============================================================================
# Manual — fixed replicas
# =============================================================================

class ManualFixed(Controller):
    kind = "manual"

    def __init__(self, replicas: int, min_replicas: int = 1, max_replicas: int = 10 ** 6):
        self.replicas = int(replicas)
        self.min_replicas = min_replicas
        self.max_replicas = max_replicas

    def decide(self, ctx: ControlContext) -> int:
        return _clamp(self.replicas, self.min_replicas, self.max_replicas)


# =============================================================================
# Manual — programmed schedule (step function)
# =============================================================================

class ManualSchedule(Controller):
    kind = "manual-sched"

    def __init__(self, schedule: List[Tuple[float, int]],
                 min_replicas: int = 1, max_replicas: int = 10 ** 6):
        # list of (t_seconds, replicas), sorted by time
        self.schedule = sorted((float(t), int(r)) for t, r in schedule)
        if not self.schedule:
            raise ValueError("ManualSchedule: empty schedule")
        self.min_replicas = min_replicas
        self.max_replicas = max_replicas

    def decide(self, ctx: ControlContext) -> int:
        target = self.schedule[0][1]
        for t, r in self.schedule:
            if ctx.elapsed_s >= t:
                target = r
            else:
                break
        return _clamp(target, self.min_replicas, self.max_replicas)


# =============================================================================
# HPA — Kubernetes Horizontal Pod Autoscaler v2 (reimplemented)
# =============================================================================

class HPAController(Controller):
    """HPA v2 algorithm: ``desired = ceil(current * util/target)``.

    - tolerance: no scaling if ``|util/target − 1| ≤ tolerance`` (def. 0.10);
    - stabilization windows: on **scale-down**, we keep the **max** of the
      recommendations over ``downscale_stabilization_s`` (avoids flapping); on
      **scale-up**, ``upscale_stabilization_s`` (def. 0 → immediate reaction);
    - bounds [min, max].
    """

    kind = "hpa"

    def __init__(self, target_utilization: float = 0.5,
                 min_replicas: int = 1, max_replicas: int = 8,
                 tolerance: float = 0.10,
                 upscale_stabilization_s: float = 0.0,
                 downscale_stabilization_s: float = 60.0):
        self.target = target_utilization
        self.min_replicas = min_replicas
        self.max_replicas = max_replicas
        self.tolerance = tolerance
        self.up_window = upscale_stabilization_s
        self.down_window = downscale_stabilization_s
        self._recs: List[Tuple[float, int]] = []  # (elapsed_s, raw_desired)

    def _raw_desired(self, ctx: ControlContext) -> int:
        cur = max(1, ctx.current_replicas)
        target = self.target if 0 < self.target < 1 else (ctx.target_utilization or 0.5)
        if ctx.cpu_util_per_replica <= 0:
            return self.min_replicas
        ratio = ctx.cpu_util_per_replica / target
        if abs(ratio - 1.0) <= self.tolerance:
            return cur  # within tolerance → don't move
        return math.ceil(cur * ratio)

    def decide(self, ctx: ControlContext) -> int:
        cur = max(1, ctx.current_replicas)
        raw = _clamp(self._raw_desired(ctx), self.min_replicas, self.max_replicas)
        self._recs.append((ctx.elapsed_s, raw))
        # purge beyond the largest window
        horizon = max(self.up_window, self.down_window)
        self._recs = [(t, r) for (t, r) in self._recs if ctx.elapsed_s - t <= horizon]

        if raw > cur:  # scale-up
            window = [r for (t, r) in self._recs if ctx.elapsed_s - t <= self.up_window]
            candidate = max(window) if window else raw
        elif raw < cur:  # scale-down: conservative → max over the window
            window = [r for (t, r) in self._recs if ctx.elapsed_s - t <= self.down_window]
            candidate = max(window) if window else raw
        else:
            candidate = cur
        return _clamp(candidate, self.min_replicas, self.max_replicas)


# =============================================================================
# uopt — OPTCTRL optimization model (with M/M/S formula fallback)
# =============================================================================

class UoptController(Controller):
    """Adapts the optimal controller ``OPTCTRL``.

    Calls ``OPTCTRL.OPTController([service_time], [target], [users])`` (SCIP) or
    ``OPTControllerCasadi`` depending on ``method``. If ``controller.controlqueuing``
    cannot be imported (casadi/scip absent) or fails, falls back to the queuing
    formula ``ceil(λ · service_time / target)``.
    """

    kind = "uopt"

    def __init__(self, target_utilization: float = 0.2,
                 min_replicas: int = 1, max_replicas: int = 8,
                 method: str = "scip"):
        self.target = target_utilization
        self.min_replicas = min_replicas
        self.max_replicas = max_replicas
        self.method = method
        self._opt = None
        try:
            from controller.controlqueuing import OPTCTRL
            self._opt = OPTCTRL(init_cores=min_replicas, min_cores=min_replicas,
                                max_cores=max_replicas, st=target_utilization)
            logger.info("UoptController: OPTCTRL loaded (method=%s).", method)
        except Exception as e:  # casadi/scip missing → formula fallback
            logger.warning("UoptController: OPTCTRL unavailable (%s) → falling back to M/M/S.", e)

    def _formula(self, ctx: ControlContext) -> int:
        target = self.target if 0 < self.target < 1 else 0.2
        if ctx.arrival_rate <= 0 or ctx.service_time <= 0:
            return self.min_replicas
        return math.ceil((ctx.arrival_rate * ctx.service_time) / target)

    def decide(self, ctx: ControlContext) -> int:
        replicas: Optional[int] = None
        if self._opt is not None and ctx.active_users > 0 and ctx.service_time > 0:
            try:
                if self.method == "casadi":
                    s = self._opt.OPTControllerCasadi(
                        [ctx.service_time], [self.target], [ctx.active_users])
                else:
                    s = self._opt.OPTController(
                        [ctx.service_time], [self.target], [ctx.active_users])
                s = s[0] if isinstance(s, (list, tuple)) else s
                replicas = math.ceil(float(s))
            except Exception as e:
                logger.debug("OPTCTRL failed (%s) → falling back to formula.", e)
        if replicas is None:
            replicas = self._formula(ctx)
        return _clamp(replicas, self.min_replicas, self.max_replicas)


# =============================================================================
# OpenClass — M/M/S formula (explicit alternative)
# =============================================================================

class OpenClassController(Controller):
    kind = "openclass"

    def __init__(self, target_utilization: float = 0.2,
                 min_replicas: int = 1, max_replicas: int = 8):
        self.target = target_utilization
        self.min_replicas = min_replicas
        self.max_replicas = max_replicas

    def decide(self, ctx: ControlContext) -> int:
        target = self.target if 0 < self.target < 1 else 0.2
        if ctx.arrival_rate <= 0 or ctx.service_time <= 0:
            return _clamp(self.min_replicas, self.min_replicas, self.max_replicas)
        replicas = math.ceil((ctx.arrival_rate * ctx.service_time) / target)
        return _clamp(replicas, self.min_replicas, self.max_replicas)


# =============================================================================
# Factory
# =============================================================================

def make_controller(kind: str, *, target_utilization: float = 0.5,
                    min_replicas: int = 1, max_replicas: int = 8,
                    fixed_replicas: Optional[int] = None,
                    schedule: Optional[List[Tuple[float, int]]] = None,
                    tolerance: float = 0.10,
                    upscale_stabilization_s: float = 0.0,
                    downscale_stabilization_s: float = 60.0,
                    uopt_method: str = "scip") -> Controller:
    """Builds a controller from a name and parameters."""
    kind = (kind or "none").lower()
    if kind == "none":
        return NoneController()
    if kind in ("manual", "manual-fixed", "fixed"):
        if fixed_replicas is None:
            raise ValueError("controller 'manual' requires fixed_replicas")
        return ManualFixed(fixed_replicas, min_replicas=min_replicas, max_replicas=max_replicas)
    if kind in ("manual-sched", "manual-schedule", "schedule", "sched"):
        if not schedule:
            raise ValueError("controller 'manual-sched' requires schedule")
        return ManualSchedule(schedule, min_replicas=min_replicas, max_replicas=max_replicas)
    if kind == "hpa":
        return HPAController(target_utilization=target_utilization,
                             min_replicas=min_replicas, max_replicas=max_replicas,
                             tolerance=tolerance,
                             upscale_stabilization_s=upscale_stabilization_s,
                             downscale_stabilization_s=downscale_stabilization_s)
    if kind == "uopt":
        return UoptController(target_utilization=target_utilization,
                              min_replicas=min_replicas, max_replicas=max_replicas,
                              method=uopt_method)
    if kind == "openclass":
        return OpenClassController(target_utilization=target_utilization,
                                   min_replicas=min_replicas, max_replicas=max_replicas)
    raise ValueError(f"unknown controller: {kind!r}")


CONTROLLER_KINDS = ["none", "manual", "manual-sched", "hpa", "uopt", "openclass"]
