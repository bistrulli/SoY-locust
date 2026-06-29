"""Breaking-point (capacity) detection during a load ramp-up.

Watches the **Locust web API** (``/stats/requests``) live: throughput (RPS),
**instantaneous failure rate** ("lost messages") and p95 latency. Identifies:

  * the **knee** (``knee_rps``): max throughput sustained under the failure
    threshold / the SLA;
  * the **breaking point** (``breaking_rps``): first throughput where the failure
    rate exceeds the ``fail_threshold`` threshold for ``break_samples`` consecutive
    measurements.

When the breaking point is reached, it can **stop the run** (``on_break``) to avoid
wasting time. Writes a time series ``capacity/<service>.csv``.
"""
from __future__ import annotations

import csv
import logging
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import requests

from .config import CFG, BenchConfig

logger = logging.getLogger(__name__)


def _p95_ms(data: dict) -> Optional[float]:
    cp = data.get("current_response_time_percentiles") or {}
    for k in ("response_time_percentile_0.95", "0.95", "95"):
        if cp.get(k) is not None:
            return float(cp[k])
    for k in ("current_response_time_percentile_0.95", "current_response_time_percentile_1.0"):
        if data.get(k) is not None:
            return float(data[k])
    for row in data.get("stats", []) or []:
        if row.get("name") in ("Aggregated", "Total"):
            v = row.get("95%")
            return float(v) if v is not None else None
    return None


class CapacityProbe:
    def __init__(self, web_url: str, run_tag: str, service: str,
                 fail_threshold: float = 0.02, sla_p95_ms: Optional[float] = None,
                 break_samples: int = 3, control_period_s: float = 2.0,
                 on_break: Optional[Callable[[], None]] = None,
                 cfg: Optional[BenchConfig] = None):
        self.web_url = web_url.rstrip("/")
        self.run_tag = run_tag
        self.service = service
        self.fail_threshold = fail_threshold
        self.sla_p95_ms = sla_p95_ms
        self.break_samples = break_samples
        self.control_period_s = control_period_s
        self.on_break = on_break
        self.cfg = cfg or CFG

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.csv_path = self.cfg.results_path(run_tag, "capacity", f"{service}.csv")
        self.result = {
            "fail_threshold": fail_threshold, "sla_p95_ms": sla_p95_ms,
            "broken": False, "breaking_rps": None, "breaking_users": None,
            "breaking_elapsed_s": None, "knee_rps": 0.0, "knee_users": 0.0,
            "max_rps": 0.0, "samples": 0,
        }

    def start(self) -> "CapacityProbe":
        self._thread = threading.Thread(target=self.run, name="capacity-probe", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> dict:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.control_period_s * 2 + 5)
        return self.result

    def _sample(self) -> Optional[dict]:
        try:
            r = requests.get(self.web_url + "/stats/requests", timeout=self.cfg.http_timeout_s)
            r.raise_for_status()
            return r.json()
        except (requests.exceptions.RequestException, ValueError):
            return None

    def run(self) -> None:
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        consec = 0
        with open(self.csv_path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["ts", "elapsed_s", "users", "rps", "good_rps", "fail_per_sec",
                        "fail_ratio_inst", "cum_fail_ratio", "p95_ms", "over_limit"])
            t0 = time.time()
            last_hb = -1e9
            hb_every = max(self.control_period_s, 10.0)   # heartbeat cadence (s)
            while not self._stop.is_set():
                data = self._sample()
                if data is not None:
                    el = time.time() - t0
                    users = float(data.get("user_count", 0) or 0)
                    rps = float(data.get("total_rps", 0) or 0)
                    fps = float(data.get("total_fail_per_sec", 0) or 0)
                    cum = float(data.get("fail_ratio", 0) or 0)
                    p95 = _p95_ms(data)
                    # total_rps already includes failures → ratio = fps/rps
                    fr = min(1.0, max(0.0, fps / rps)) if rps > 0 else (1.0 if fps > 0 else 0.0)
                    good_rps = max(0.0, rps - fps)
                    over = (fr > self.fail_threshold) or (
                        self.sla_p95_ms is not None and p95 is not None and p95 > self.sla_p95_ms)

                    self.result["samples"] += 1
                    self.result["max_rps"] = max(self.result["max_rps"], round(good_rps, 2))
                    if not over and good_rps > self.result["knee_rps"]:
                        self.result["knee_rps"] = round(good_rps, 2)
                        self.result["knee_users"] = round(users, 1)

                    if over and rps > 0:
                        consec += 1
                        if consec >= self.break_samples and not self.result["broken"]:
                            self.result.update(broken=True, breaking_rps=round(good_rps, 2),
                                               breaking_users=round(users, 1),
                                               breaking_elapsed_s=round(el, 1))
                            logger.warning("Breaking point: %.1f req/s @ %.0f users "
                                           "(fail=%.1f%%, p95=%s ms)", rps, users,
                                           fr * 100, p95)
                            if self.on_break:
                                try:
                                    self.on_break()
                                except Exception as e:
                                    logger.error("on_break: %s", e)
                    else:
                        consec = 0

                    # periodic heartbeat so the screen shows the live load
                    if el - last_hb >= hb_every:
                        last_hb = el
                        logger.info(
                            "load @%.0fs: %.0f users | %.1f req/s (good %.1f) | "
                            "fail %.1f%% | p95 %s ms%s",
                            el, users, rps, good_rps, fr * 100,
                            int(p95) if p95 is not None else "n/a",
                            "  OVER-LIMIT" if over else "")

                    w.writerow([round(time.time(), 2), round(el, 1), users, round(rps, 2),
                                round(good_rps, 2), round(fps, 2), round(fr, 4),
                                round(cum, 4), round(p95, 1) if p95 is not None else "",
                                int(over)])
                    fh.flush()
                self._stop.wait(self.control_period_s)
        logger.info("Capacity probe stopped (knee=%.1f req/s, breaking=%s) → %s",
                    self.result["knee_rps"], self.result["breaking_rps"], self.csv_path)
