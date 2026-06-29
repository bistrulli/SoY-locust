"""Staircase: +SHAPE_STEP_USERS every SHAPE_STEP_S, capped at `--users`."""
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
        users = int(getattr(opts, "num_users", 0) or 100)
        total = _f("SHAPE_TOTAL_S", float(getattr(opts, "run_time", 0) or 300))
        step_s = _f("SHAPE_STEP_S", 60)
        step_u = int(_f("SHAPE_STEP_USERS", max(1, users // 4)))
        t = self.get_run_time()
        if t > total:
            return None
        n = int(t // step_s) + 1
        cur = min(users, n * step_u)
        return max(1, cur), max(1, step_u)
