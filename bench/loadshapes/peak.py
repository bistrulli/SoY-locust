"""Peak: ramp-up (SHAPE_RAMP_S) → plateau `--users` (SHAPE_PEAK_S) → ramp-down."""
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
        ramp = _f("SHAPE_RAMP_S", 120)
        peak = _f("SHAPE_PEAK_S", 60)
        total = ramp + peak + ramp
        t = self.get_run_time()
        if t > total:
            return None
        if t < ramp:                                  # ramp-up
            cur = int((t / ramp) * users)
            spawn = users / ramp
        elif t < ramp + peak:                         # plateau
            cur = users
            spawn = users
        else:                                         # ramp-down
            down = t - ramp - peak
            cur = int(users * (1 - down / ramp))
            spawn = users / ramp
        return max(1, cur), max(1, spawn)
