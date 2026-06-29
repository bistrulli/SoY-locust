"""Harness configuration, overridable via environment variables.

Same env names as ``promisebench/config.py`` to stay compatible with the
metrics capture docs (RAPL + power meter). Any source whose URL is empty is
disabled.

    # System
    METRICS_SAMPLE_S=1.0                         # sampling step (s)

    # RAPL (Scaphandre, Prometheus exporter on the host under test)
    SCAPHANDRE_URL=http://localhost:9999/metrics

    # Tasmota power meter (HTTP)
    WATTMETER_HTTP=http://192.168.3.131
    WATTMETER_HTTP_USER=   WATTMETER_HTTP_PASS=

    # Remote Docker (optional) — otherwise local daemon
    DOCKER_HOST=tcp://192.168.3.102:2375

    # Outputs
    RESULTS_ROOT=results
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _env_f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() not in ("0", "false", "no", "off", "")


@dataclass
class BenchConfig:
    """Global settings resolved from the environment."""

    # --- metrics sampling ---
    metrics_sample_s: float = 1.0

    # --- RAPL (Scaphandre) ---
    scaphandre_url: str = "http://localhost:9999/metrics"
    rapl_sysfs: str = "/sys/class/powercap"  # fallback if Scaphandre is absent

    # --- Tasmota power meter (HTTP) ---
    wattmeter_http: str = ""  # empty => disabled
    wattmeter_http_user: str = ""
    wattmeter_http_pass: str = ""

    # --- energy source toggles (run cleanly with no endpoint) ---
    rapl_enabled: bool = True       # False => no Scaphandre AND no sysfs RAPL
    wattmeter_enabled: bool = True  # False => no Tasmota wattmeter

    # --- Docker ---
    docker_host: str = ""  # e.g. tcp://192.168.3.102:2375 ; empty => local daemon

    # --- topology: machine hosting the app (target of Locust + Scaphandre) ---
    app_host: str = "localhost"   # e.g. 192.168.3.102

    # --- system metrics source ---
    # auto: docker stats (remote app) if docker_host, otherwise psutil (local machine)
    system_source: str = "auto"   # auto | docker | psutil

    # --- outputs ---
    results_root: str = "results"

    # --- misc ---
    http_timeout_s: float = 5.0

    @classmethod
    def from_env(cls) -> "BenchConfig":
        return cls(
            metrics_sample_s=_env_f("METRICS_SAMPLE_S", 1.0),
            scaphandre_url=_env("SCAPHANDRE_URL", "http://localhost:9999/metrics"),
            rapl_sysfs=_env("RAPL_SYSFS", "/sys/class/powercap"),
            wattmeter_http=_env("WATTMETER_HTTP", ""),
            wattmeter_http_user=_env("WATTMETER_HTTP_USER", ""),
            wattmeter_http_pass=_env("WATTMETER_HTTP_PASS", ""),
            rapl_enabled=_env_bool("RAPL_ENABLED", True),
            wattmeter_enabled=_env_bool("WATTMETER_ENABLED", True),
            docker_host=_env("DOCKER_HOST", ""),
            app_host=_env("BENCH_APP_HOST", "localhost"),
            system_source=_env("SYS_SOURCE", "auto"),
            results_root=_env("RESULTS_ROOT", "results"),
            http_timeout_s=_env_f("BENCH_HTTP_TIMEOUT_S", 5.0),
        )

    def resolved_system_source(self) -> str:
        """'auto' → 'docker' if remote Docker, otherwise 'psutil'."""
        if self.system_source != "auto":
            return self.system_source
        return "docker" if self.docker_host else "psutil"

    # --- helpers ---
    def docker_env(self) -> dict:
        """Env variables to pass to ``docker`` subprocesses (remote DOCKER_HOST)."""
        env = dict(os.environ)
        if self.docker_host:
            env["DOCKER_HOST"] = self.docker_host
        return env

    def results_path(self, *parts: str) -> Path:
        return Path(self.results_root).joinpath(*parts)

    def to_dict(self) -> dict:
        return asdict(self)


# Default instance, read at import time. Rebuild with BenchConfig.from_env()
# if the environment changes at runtime.
CFG = BenchConfig.from_env()
