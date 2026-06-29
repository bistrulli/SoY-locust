"""Control signal: what the controller reads at each tick.

Two sources behind the same interface:

  * ``DockerStatsSignal`` (primary, works everywhere) — CPU per service via
    ``docker stats`` + replica count via the backend; throughput/users/RT
    via the Locust web API (``/stats/requests``).
  * ``PrometheusSignal`` — wraps the existing ``estimator.monitoring.Monitoring``
    (nginx-vts + cAdvisor) for monoliths; falls back to DockerStats if unavailable.

The HPA only needs ``cpu_util_per_replica`` + ``replicas`` → DockerStats is enough.
``uopt`` additionally uses ``service_time``/``active_users``.
"""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from typing import List, Optional

import requests

from .backends import Backend
from .config import CFG, BenchConfig
from .infra import Infra

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    replicas: int = 0
    cpu_util_per_replica: float = 0.0   # fraction 0..1 of the CPU budget per replica
    arrival_rate: float = 0.0           # req/s (λ)
    throughput: float = 0.0             # req/s
    response_time: float = 0.0          # s
    active_users: float = 0.0
    service_time: float = 0.0           # s/req (estimated CPU demand)


def _parse_cpuperc(s: str) -> float:
    """'12.50%' -> 12.5 (float)."""
    try:
        return float(s.strip().rstrip("%"))
    except (ValueError, AttributeError):
        return 0.0


def docker_stats_cpu(container_ids: List[str], cfg: BenchConfig) -> float:
    """Sum of CPU% (``docker stats``) for the given containers. 0 if none."""
    if not container_ids:
        return 0.0
    cmd = ["docker", "stats", "--no-stream", "--format", "{{json .}}"] + container_ids
    try:
        res = subprocess.run(cmd, env=cfg.docker_env(), check=False,
                             capture_output=True, text=True, timeout=cfg.http_timeout_s + 10)
    except subprocess.TimeoutExpired:
        logger.debug("docker stats timeout")
        return 0.0
    if res.returncode != 0:
        return 0.0
    total = 0.0
    for line in res.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            total += _parse_cpuperc(d.get("CPUPerc", "0%"))
        except json.JSONDecodeError:
            continue
    return total


def locust_stats(web_url: Optional[str], cfg: BenchConfig) -> dict:
    """Aggregated stats via the Locust web API. ``{}`` if unavailable/headless."""
    if not web_url:
        return {}
    try:
        r = requests.get(web_url.rstrip("/") + "/stats/requests", timeout=cfg.http_timeout_s)
        r.raise_for_status()
        return r.json()
    except (requests.exceptions.RequestException, ValueError):
        return {}


class SignalSource:
    def sample(self) -> Signal:  # pragma: no cover - interface
        raise NotImplementedError


class DockerStatsSignal(SignalSource):
    def __init__(self, infra: Infra, backend: Backend,
                 locust_web_url: Optional[str] = None,
                 cfg: Optional[BenchConfig] = None):
        self.infra = infra
        self.backend = backend
        self.locust_web_url = locust_web_url
        self.cfg = cfg or CFG

    def sample(self) -> Signal:
        svc = self.infra.scalable_service
        ids = self.backend.containers(svc)
        replicas = len(ids) or self.backend.replicas(svc)
        total_cpu_pct = docker_stats_cpu(ids, self.cfg)

        # CPU% sum -> fraction per replica of the CPU budget (cpu_limit_cores).
        denom = max(1, replicas) * 100.0 * max(self.infra.cpu_limit_cores, 1e-9)
        cpu_util_per_replica = total_cpu_pct / denom if denom else 0.0

        ls = locust_stats(self.locust_web_url, self.cfg)
        users = float(ls.get("user_count", 0) or 0)
        throughput = float(ls.get("total_rps", 0) or 0)
        # aggregated response time (ms -> s): we look for the "Aggregated" row.
        rt_ms = 0.0
        for row in ls.get("stats", []) or []:
            if row.get("name") in ("Aggregated", "Total"):
                rt_ms = float(row.get("avg_response_time", 0) or 0)
                break
        response_time = rt_ms / 1000.0

        # service_time ≈ CPU demand per request = util*replicas / throughput
        per_replica_rps = throughput / max(1, replicas)
        if per_replica_rps > 0:
            service_time = cpu_util_per_replica / per_replica_rps
        else:
            service_time = response_time

        return Signal(
            replicas=replicas,
            cpu_util_per_replica=round(cpu_util_per_replica, 4),
            arrival_rate=round(throughput, 3),
            throughput=round(throughput, 3),
            response_time=round(response_time, 4),
            active_users=users,
            service_time=round(service_time, 5),
        )


class PrometheusSignal(SignalSource):
    """Wraps ``estimator.monitoring.Monitoring`` (best-effort).

    Automatic fallback to ``DockerStatsSignal`` if Monitoring cannot be
    imported/instantiated (missing dependencies or Prometheus unavailable).
    """

    def __init__(self, infra: Infra, backend: Backend,
                 locust_web_url: Optional[str] = None,
                 cfg: Optional[BenchConfig] = None):
        self.infra = infra
        self.backend = backend
        self.cfg = cfg or CFG
        self._fallback = DockerStatsSignal(infra, backend, locust_web_url, cfg)
        self._mon = None
        try:
            from estimator.monitoring import Monitoring
            self._mon = Monitoring(
                window=30, sla=1.0, serviceName=infra.scalable_service,
                stack_name=infra.project,
                promHost=(self.cfg.app_host or "localhost"),
                promPort=infra.prometheus_port, sysfile="")
            logger.info("PrometheusSignal: Monitoring loaded for %s.", infra.name)
        except Exception as e:
            logger.warning("PrometheusSignal unavailable (%s) → DockerStats.", e)

    def sample(self) -> Signal:
        if self._mon is None:
            return self._fallback.sample()
        try:
            replicas = self.backend.replicas(self.infra.scalable_service)
            util = float(self._mon.get_service_cpu_utilization())
            arrival = float(self._mon.getArrivalRate())
            throughput = float(self._mon.getTroughput())
            rt = float(self._mon.getResponseTime())
            users = float(self._mon.get_active_users())
            cpu_pr = (util / max(1, replicas)) / max(self.infra.cpu_limit_cores, 1e-9)
            stime = (util / throughput) if throughput > 0 else rt
            return Signal(replicas=replicas, cpu_util_per_replica=round(cpu_pr, 4),
                          arrival_rate=round(arrival, 3), throughput=round(throughput, 3),
                          response_time=round(rt, 4), active_users=users,
                          service_time=round(stime, 5))
        except Exception as e:
            logger.debug("PrometheusSignal sample failed (%s) → DockerStats.", e)
            return self._fallback.sample()


def make_signal(infra: Infra, backend: Backend,
                locust_web_url: Optional[str] = None,
                cfg: Optional[BenchConfig] = None) -> SignalSource:
    if infra.signal_kind == "prometheus":
        return PrometheusSignal(infra, backend, locust_web_url, cfg)
    return DockerStatsSignal(infra, backend, locust_web_url, cfg)
