"""Constant load: holds `--users` until the end. Infra-agnostic."""
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
        if self.get_run_time() > total:
            return None
        spawn = int(getattr(opts, "spawn_rate", 0) or users)
        return users, max(1, spawn)
