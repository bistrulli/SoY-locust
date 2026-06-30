"""Launch of the Locust subprocess (load).

Runs with the web API enabled (``--autostart --autoquit``) so that the scaling
loop can read ``/stats/requests`` (throughput, users, RT) for uopt. The
process is launched in a new *process group* for a clean termination
(like ``run_load_test.py``).
"""
from __future__ import annotations

import logging
import os
import signal
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


def build_locust_cmd(locustfile: str, loadshape: Optional[str], host: str,
                     csv_prefix: str, run_time: Optional[str] = None,
                     users: Optional[int] = None, spawn_rate: int = 50,
                     web_port: int = 8089, headless: bool = False) -> List[str]:
    """Build the Locust command.

    If ``loadshape`` is provided, it is passed as a second file ``-f a,b`` and
    drives the number of users (``--users`` becomes a cap).
    """
    f_arg = f"{locustfile},{loadshape}" if loadshape else locustfile
    # Invoke via `python -m locust` (not the bare `locust` binary) so it runs even when
    # ~/.local/bin is not on PATH (non-interactive shells / inside screen). --csv-full-history:
    # time series (RPS, percentiles, failures) for the figures.
    cmd = [sys.executable, "-m", "locust", "-f", f_arg, "--host", host,
           "--csv", csv_prefix, "--csv-full-history"]
    # Distribute the load over several CPU cores (master + N local workers) so the
    # GENERATOR is not the bottleneck at high user counts (single-process Locust is
    # ~1 core). The master still aggregates stats on the web API, so the signal /
    # capacity probe are unaffected. LOCUST_PROCESSES=1 disables it.
    procs = int(os.environ.get("LOCUST_PROCESSES", "6"))
    if procs > 1:
        cmd += ["--processes", str(procs)]
    if headless:
        cmd.append("--headless")
    else:
        # web API available + automatic start/stop
        cmd += ["--web-port", str(web_port), "--autostart", "--autoquit", "3"]
    if run_time:
        cmd += ["--run-time", run_time]
    if users:
        cmd += ["--users", str(users), "--spawn-rate", str(spawn_rate)]
    return cmd


class LocustRunner:
    def __init__(self, cmd: List[str], cwd: Optional[str] = None,
                 log_path: Optional[str] = None):
        self.cmd = cmd
        self.cwd = cwd
        self.log_path = log_path
        self.proc: Optional[subprocess.Popen] = None

    def start(self) -> "LocustRunner":
        logger.info("Locust: %s", " ".join(self.cmd))
        self._fh = None
        self._tee = None
        echo = os.environ.get("BENCH_LOCUST_ECHO", "1").lower() not in ("0", "false", "no")
        if self.log_path:
            Path(self.log_path).parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(self.log_path, "w")
        if self.log_path and echo:
            # mirror Locust output to BOTH the file AND our stdout (→ visible in the
            # screen / console.log). Each line is prefixed so it stands out.
            self.proc = subprocess.Popen(
                self.cmd, cwd=self.cwd, preexec_fn=os.setsid, text=True, bufsize=1,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self._tee = threading.Thread(target=self._pump, daemon=True)
            self._tee.start()
        else:
            out = self._fh  # None → inherits our stdout/err
            self.proc = subprocess.Popen(
                self.cmd, cwd=self.cwd, preexec_fn=os.setsid, stdout=out, stderr=out)
        return self

    def _pump(self) -> None:
        """Stream Locust output line-by-line to the log file and to stdout."""
        try:
            for line in self.proc.stdout:
                if self._fh:
                    self._fh.write(line)
                    self._fh.flush()
                sys.stdout.write("[locust] " + line)
                sys.stdout.flush()
        except Exception:
            pass

    def wait(self, timeout: Optional[float] = None) -> int:
        if not self.proc:
            return -1
        try:
            return self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.warning("Locust exceeds the timeout (%.0fs) → stopping.", timeout or 0)
            self.stop()
            return -1

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
                self.proc.wait(timeout=15)
            except Exception as e:
                logger.error("Stopping Locust: %s", e)
                try:
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
                except Exception:
                    pass
        if getattr(self, "_tee", None):
            self._tee.join(timeout=5)
        if getattr(self, "_fh", None):
            self._fh.close()
