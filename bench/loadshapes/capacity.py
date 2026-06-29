"""Capacity ramp: **stepwise** ramp-up of the offered throughput up to the
`--users` ceiling, to find the limit. Designed with ``bench.capacity.CapacityProbe``
which stops the run at the breaking point.

  SHAPE_STEPS   number of steps up to the ceiling (default 10)
  SHAPE_STEP_S  duration of a step in s (default 30)
"""
import os
from locust import LoadTestShape


def _f(name, d):
    try:
        return float(os.environ.get(name, d))
    except (TypeError, ValueError):
        return d


class CustomLoadShape(LoadTestShape):
    use_common_options = True

    def tick(self):
        opts = self.runner.environment.parsed_options
        ceiling = int(getattr(opts, "num_users", 0) or 100)
        steps = max(1, int(_f("SHAPE_STEPS", 10)))
        step_s = _f("SHAPE_STEP_S", 30)
        total = steps * step_s
        t = self.get_run_time()
        if t > total:
            return None
        level = min(steps, int(t // step_s) + 1)
        users = max(1, int(round(level * ceiling / steps)))
        spawn = max(1, ceiling / steps)
        return users, spawn
