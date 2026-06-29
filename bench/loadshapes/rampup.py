"""Linear ramp-up 0 → `--users` over SHAPE_RAMP_S (default = total duration)."""
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
        ramp = _f("SHAPE_RAMP_S", total)
        t = self.get_run_time()
        if t > total:
            return None
        cur = max(1, int(min(1.0, t / ramp) * users)) if ramp > 0 else users
        spawn = max(1, users / ramp) if ramp > 0 else users
        return cur, spawn
