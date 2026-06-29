"""Cyclical: N cycles of [ramp-up SHAPE_RAMP_S → plateau SHAPE_PLATEAU_S at
`--users` → pause SHAPE_PAUSE_S]. Replaces the old cyclical_shape.py which
depended on undeclared custom CLI options."""
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
        ramp = _f("SHAPE_RAMP_S", 30)
        plateau = _f("SHAPE_PLATEAU_S", 60)
        pause = _f("SHAPE_PAUSE_S", 30)
        cycles = int(_f("SHAPE_CYCLES", 4))
        cycle = ramp + plateau + pause
        total = cycle * cycles
        t = self.get_run_time()
        if t > total or cycle <= 0:
            return None
        ct = t % cycle
        if ct < ramp:                                 # ramp-up
            cur = int((ct / ramp) * users) if ramp > 0 else users
            spawn = users / ramp if ramp > 0 else users
        elif ct < ramp + plateau:                     # plateau
            cur = users
            spawn = users
        else:                                         # pause
            cur = 1
            spawn = users
        return max(1, cur), max(1, spawn)
