"""Capture system & energy metrics around a load — a "phase window".

Three streams, each optional and resilient (we collect whatever responds):

  * **System** (psutil)    : CPU, memory, disk IO, network IO of the target machine,
                             sampled every ``metrics_sample_s`` s.
  * **RAPL** (Scaphandre)  : ``scaph_*_energy_microjoules`` counters read at the
                             boundaries (start/end) → Δ µJ → Joules per domain. Fallback
                             to sysfs ``/sys/class/powercap`` if Scaphandre is absent.
  * **Wall** (Tasmota HTTP): instantaneous power (W) sampled then integrated
                             ``Σ wᵢ·Δt`` → Joules + peak watts.

Usage:

    from bench import metrics
    ph = metrics.Phase("mon_xp", "run5")
    ph.start()
    ...   # run the load
    m = ph.stop()   # -> results/run5/metrics/mon_xp.metrics.json (+ .power.csv, .resources.csv)

Mirrors ``promisebench/metrics.py`` but targets Docker/machine (psutil instead of
``kubectl top``).
"""
from __future__ import annotations

import csv
import json
import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

from .config import CFG, BenchConfig

logger = logging.getLogger(__name__)

try:  # psutil is optional: we degrade gracefully if it is missing
    import psutil
except Exception:  # pragma: no cover - depends on the install
    psutil = None  # type: ignore


# =============================================================================
# RAPL — Scaphandre (counter snapshot) + sysfs fallback
# =============================================================================

def parse_scaphandre(text: str) -> Dict[str, float]:
    """Extract energy counters (µJ) from Scaphandre's Prometheus page.

    Returns a dict ``{domain: microjoules}`` aggregated for the domains
    ``host``, ``package`` (socket), ``cores``, ``dram``. Multiple sockets
    are summed.
    """
    totals: Dict[str, float] = {}

    def add(key: str, val: float) -> None:
        totals[key] = totals.get(key, 0.0) + val

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # form: metric_name{labels} value  (or: metric_name value)
        try:
            if "}" in line:
                head, value_str = line.rsplit("}", 1)
                head += "}"
            else:
                head, value_str = line.rsplit(" ", 1)
            value = float(value_str.strip())
        except (ValueError, IndexError):
            continue

        name = head.split("{", 1)[0]
        labels = head[head.find("{") + 1: head.rfind("}")] if "{" in head else ""

        if name == "scaph_host_energy_microjoules":
            add("host", value)
        elif name == "scaph_socket_energy_microjoules":
            add("package", value)
        elif name == "scaph_domain_energy_microjoules":
            dom = ""
            for part in labels.split(","):
                if "domain_name" in part:
                    dom = part.split("=", 1)[1].strip().strip('"').lower()
                    break
            if "dram" in dom:
                add("dram", value)
            elif "core" in dom:
                add("cores", value)
            elif "package" in dom and "package" not in totals:
                add("package", value)
    return totals


def read_scaphandre(cfg: BenchConfig) -> Dict[str, float]:
    """Read a snapshot of RAPL counters via Scaphandre. ``{}`` if unreachable."""
    if not cfg.scaphandre_url:
        return {}
    last_exc = None
    for _ in range(3):  # the Prometheus page may be partial
        try:
            r = requests.get(cfg.scaphandre_url, timeout=cfg.http_timeout_s)
            r.raise_for_status()
            parsed = parse_scaphandre(r.text)
            if parsed:
                return parsed
        except requests.exceptions.RequestException as e:
            last_exc = e
            time.sleep(0.2)
    if last_exc:
        logger.debug("Scaphandre unreachable (%s): %s", cfg.scaphandre_url, last_exc)
    return {}


def read_rapl_sysfs(cfg: BenchConfig) -> Dict[str, float]:
    """Linux fallback: reads ``/sys/class/powercap/intel-rapl:*`` (µJ).

    Returns ``{domain: microjoules}`` (key = RAPL domain name: package-0,
    core, dram, ...). ``{}`` outside Linux / without powercap.
    """
    base = Path(cfg.rapl_sysfs)
    if not base.exists():
        return {}
    out: Dict[str, float] = {}
    try:
        for zone in sorted(base.glob("intel-rapl:*")):
            ej = zone / "energy_uj"
            nf = zone / "name"
            if not ej.exists():
                continue
            try:
                name = nf.read_text().strip() if nf.exists() else zone.name
                val = float(ej.read_text().strip())
            except (OSError, ValueError):
                continue
            key = name.lower()
            if key.startswith("package"):
                out["package"] = out.get("package", 0.0) + val
            elif "dram" in key:
                out["dram"] = out.get("dram", 0.0) + val
            elif "core" in key:
                out["cores"] = out.get("cores", 0.0) + val
            else:
                out[key] = out.get(key, 0.0) + val
    except OSError:
        return {}
    return out


def _rapl_delta_joules(start: Dict[str, float], end: Dict[str, float]) -> Dict[str, float]:
    """Δ counters (µJ) → Joules per domain. Ignores negative deltas (wrap)."""
    out: Dict[str, float] = {}
    for dom in set(start) | set(end):
        if dom in start and dom in end:
            delta = end[dom] - start[dom]
            if delta >= 0:
                out[f"{dom}_J"] = round(delta / 1e6, 3)
    return out


# =============================================================================
# Wattmeter — Tasmota (HTTP)
# =============================================================================

def read_tasmota_power(cfg: BenchConfig) -> Optional[float]:
    """Instantaneous power (W) read from the Tasmota plug. ``None`` if unreachable."""
    if not cfg.wattmeter_http:
        return None
    url = cfg.wattmeter_http.rstrip("/") + "/cm?cmnd=Status%2010"
    auth = None
    if cfg.wattmeter_http_user:
        auth = (cfg.wattmeter_http_user, cfg.wattmeter_http_pass)
    try:
        r = requests.get(url, timeout=cfg.http_timeout_s, auth=auth)
        r.raise_for_status()
        data = r.json()
        energy = data.get("StatusSNS", {}).get("ENERGY", {})
        power = energy.get("Power")
        if power is None:
            return None
        return float(power)
    except (requests.exceptions.RequestException, ValueError, KeyError) as e:
        logger.debug("Tasmota unreachable (%s): %s", url, e)
        return None


def _integrate_power(samples: List[Tuple[float, float]]) -> Tuple[float, float]:
    """``Σ wᵢ·(tᵢ−tᵢ₋₁)`` (left Riemann sum). Returns (energy_J, peak_watts)."""
    if not samples:
        return 0.0, 0.0
    energy = 0.0
    peak = max(w for _, w in samples)
    for (t0, w0), (t1, _w1) in zip(samples, samples[1:]):
        energy += w0 * (t1 - t0)
    return round(energy, 3), round(peak, 3)


# =============================================================================
# System — psutil
# =============================================================================

def _read_system_sample() -> Optional[dict]:
    """One machine sample via psutil (LOCAL machine). ``None`` if psutil is absent."""
    if psutil is None:
        return None
    vm = psutil.virtual_memory()
    disk = psutil.disk_io_counters()
    net = psutil.net_io_counters()
    return {
        "cpu_pct": psutil.cpu_percent(interval=None),  # since the last call
        "mem_used_mi": round(vm.used / (1024 * 1024), 1),
        "mem_avail_mi": round(vm.available / (1024 * 1024), 1),
        "disk_read_bytes": disk.read_bytes if disk else 0,
        "disk_write_bytes": disk.write_bytes if disk else 0,
        "net_sent_bytes": net.bytes_sent if net else 0,
        "net_recv_bytes": net.bytes_recv if net else 0,
    }


_UNITS = {"b": 1, "kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12,
          "kib": 1024, "mib": 1024 ** 2, "gib": 1024 ** 3, "tib": 1024 ** 4}


def _to_bytes(s: str) -> float:
    """'1.5GiB' / '512MB' / '0B' -> bytes."""
    s = s.strip()
    num = ""
    i = 0
    while i < len(s) and (s[i].isdigit() or s[i] in ".-"):
        num += s[i]
        i += 1
    unit = s[i:].strip().lower()
    try:
        return float(num) * _UNITS.get(unit, 1)
    except ValueError:
        return 0.0


def _pair(s: str) -> Tuple[float, float]:
    """'1.2GB / 3.4GB' -> (left_bytes, right_bytes)."""
    if "/" not in s:
        return 0.0, 0.0
    a, b = s.split("/", 1)
    return _to_bytes(a), _to_bytes(b)


def docker_running_count(cfg: BenchConfig) -> Optional[int]:
    """Number of running containers on the (remote) Docker host.

    ``None`` if the daemon is unreachable; ``0`` if it answers but nothing runs.
    Lets the preflight tell "docker down" apart from "app not deployed yet".
    """
    try:
        res = subprocess.run(["docker", "ps", "-q"], env=cfg.docker_env(),
                             check=False, capture_output=True, text=True,
                             timeout=cfg.http_timeout_s + 5)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if res.returncode != 0:
        return None
    return len([ln for ln in res.stdout.splitlines() if ln.strip()])


def read_docker_system_sample(cfg: BenchConfig, name_filter: str = "") -> Optional[dict]:
    """System sample of the app via ``docker stats`` (REMOTE machine = DOCKER_HOST).

    Sums CPU%, memory, network/block IO over the containers (filtered by ``name_filter``
    if provided). This is the right source when the harness runs on the load machine
    but the app runs elsewhere.
    """
    cmd = ["docker", "stats", "--no-stream", "--format", "{{json .}}"]
    try:
        res = subprocess.run(cmd, env=cfg.docker_env(), check=False,
                             capture_output=True, text=True,
                             timeout=cfg.http_timeout_s + 15)
    except subprocess.TimeoutExpired:
        return None
    if res.returncode != 0:
        return None
    cpu = mem_used = dr = dw = ns = nr = 0.0
    n = 0
    for line in res.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if name_filter and name_filter not in d.get("Name", ""):
            continue
        n += 1
        try:
            cpu += float(d.get("CPUPerc", "0%").rstrip("%"))
        except ValueError:
            pass
        mem_used += _pair(d.get("MemUsage", "0B / 0B"))[0]
        r, w = _pair(d.get("BlockIO", "0B / 0B"))
        dr += r
        dw += w
        rx, tx = _pair(d.get("NetIO", "0B / 0B"))
        nr += rx
        ns += tx
    if n == 0:
        return None
    return {
        "cpu_pct": round(cpu, 1),
        "mem_used_mi": round(mem_used / (1024 * 1024), 1),
        "mem_avail_mi": 0.0,  # unknown via docker stats
        "disk_read_bytes": dr,
        "disk_write_bytes": dw,
        "net_sent_bytes": ns,
        "net_recv_bytes": nr,
        "containers": n,
    }


def _aggregate_resources(samples: List[dict]) -> dict:
    """Aggregate psutil samples: peak/avg CPU & mem, IO totals over the window."""
    if not samples:
        return {"samples": 0}
    cpu = [s["cpu_pct"] for s in samples]
    mem_used = [s["mem_used_mi"] for s in samples]
    mem_avail = [s["mem_avail_mi"] for s in samples]

    def io_delta(key: str) -> float:
        vals = [s[key] for s in samples if s.get(key)]
        if len(vals) < 2:
            return 0.0
        return round((vals[-1] - vals[0]) / (1024 * 1024), 2)  # MB over the window

    return {
        "cpu_pct_peak": round(max(cpu), 1),
        "cpu_pct_avg": round(sum(cpu) / len(cpu), 1),
        "mem_used_mi_peak": round(max(mem_used), 1),
        "mem_used_mi_avg": round(sum(mem_used) / len(mem_used), 1),
        "mem_avail_mi_min": round(min(mem_avail), 1),
        "disk_read_mb": io_delta("disk_read_bytes"),
        "disk_write_mb": io_delta("disk_write_bytes"),
        "net_sent_mb": io_delta("net_sent_bytes"),
        "net_recv_mb": io_delta("net_recv_bytes"),
        "samples": len(samples),
    }


# =============================================================================
# Phase — measurement window
# =============================================================================

class Phase:
    """Frames a load: ``start()`` opens the sources, ``stop()`` aggregates+writes."""

    def __init__(self, name: str, run_tag: str, cfg: Optional[BenchConfig] = None,
                 system_source: Optional[str] = None, name_filter: str = ""):
        self.name = name
        self.run_tag = run_tag
        self.cfg = cfg or CFG
        self.system_source = system_source or self.cfg.resolved_system_source()
        self.name_filter = name_filter

        self._stop = threading.Event()
        self._threads: List[threading.Thread] = []
        self._res_samples: List[dict] = []
        self._power_samples: List[Tuple[float, float]] = []
        self._rapl_start: Dict[str, float] = {}
        self._rapl_source = "none"
        self.t_start = 0.0
        self.t_end = 0.0

        self._dir = self.cfg.results_path(run_tag, "metrics")
        self._res_csv: Optional[csv.writer] = None
        self._res_fh = None
        self._pow_csv: Optional[csv.writer] = None
        self._pow_fh = None

    # --- output paths ---
    @property
    def metrics_json(self) -> Path:
        return self._dir / f"{self.name}.metrics.json"

    @property
    def resources_csv(self) -> Path:
        return self._dir / f"{self.name}.resources.csv"

    @property
    def power_csv(self) -> Path:
        return self._dir / f"{self.name}.power.csv"

    # --- lifecycle ---
    def start(self) -> "Phase":
        self._dir.mkdir(parents=True, exist_ok=True)
        self.t_start = time.time()

        # RAPL: starting snapshot (Scaphandre preferred, otherwise sysfs) — unless disabled
        if self.cfg.rapl_enabled:
            snap = read_scaphandre(self.cfg)
            if snap:
                self._rapl_start, self._rapl_source = snap, "scaphandre"
            else:
                snap = read_rapl_sysfs(self.cfg)
                if snap:
                    self._rapl_start, self._rapl_source = snap, "sysfs"

        # System: choose the source (remote docker stats vs local psutil)
        self._sys_sampler = self._pick_sys_sampler()
        if self._sys_sampler is not None:
            if self.system_source == "psutil" and psutil is not None:
                psutil.cpu_percent(interval=None)  # prime the relative measurement
            self._res_fh = open(self.resources_csv, "w", newline="")
            self._res_csv = csv.writer(self._res_fh)
            self._res_csv.writerow([
                "ts", "cpu_pct", "mem_used_mi", "mem_avail_mi",
                "disk_read_bytes", "disk_write_bytes", "net_sent_bytes", "net_recv_bytes",
            ])
            self._spawn(self._sample_system)
        else:
            logger.warning("No system source available (source=%s)", self.system_source)

        # Wattmeter: CSV + poll thread — unless disabled or no endpoint
        if self.cfg.wattmeter_enabled and self.cfg.wattmeter_http:
            self._pow_fh = open(self.power_csv, "w", newline="")
            self._pow_csv = csv.writer(self._pow_fh)
            self._pow_csv.writerow(["ts", "label", "watts"])
            self._spawn(self._sample_power)

        logger.info("Phase '%s' started (rapl=%s, wattmeter=%s, system=%s)",
                    self.name, self._rapl_source,
                    bool(self.cfg.wattmeter_enabled and self.cfg.wattmeter_http),
                    self.system_source if self._sys_sampler else "off")
        return self

    def _pick_sys_sampler(self):
        """Returns the system sampling function, or None."""
        if self.system_source == "docker":
            return lambda: read_docker_system_sample(self.cfg, self.name_filter)
        if self.system_source == "psutil":
            return _read_system_sample if psutil is not None else None
        return None

    def stop(self) -> dict:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=self.cfg.metrics_sample_s * 3 + 2)
        self.t_end = time.time()
        for fh in (self._res_fh, self._pow_fh):
            if fh:
                fh.close()

        # RAPL: Δ at the boundaries
        rapl: Dict[str, float] = {}
        if self._rapl_start:
            end = (read_scaphandre(self.cfg) if self._rapl_source == "scaphandre"
                   else read_rapl_sysfs(self.cfg))
            rapl = _rapl_delta_joules(self._rapl_start, end)

        # Wattmeter: integration
        wattmeter: Dict[str, float] = {}
        if self._power_samples:
            energy_j, peak = _integrate_power(self._power_samples)
            wattmeter = {
                "wall_energy_J": energy_j,
                "watts_peak": peak,
                "samples": len(self._power_samples),
            }

        result = {
            "phase": self.name,
            "run_tag": self.run_tag,
            "t_start": round(self.t_start, 2),
            "t_end": round(self.t_end, 2),
            "duration_s": round(self.t_end - self.t_start, 2),
            "resources": _aggregate_resources(self._res_samples),
            "rapl": rapl,
            "rapl_source": self._rapl_source,
            "wattmeter": wattmeter,
        }
        if rapl.get("package_J") and wattmeter.get("wall_energy_J"):
            try:
                result["wall_over_rapl"] = round(
                    wattmeter["wall_energy_J"] / rapl["package_J"], 3)
            except ZeroDivisionError:
                pass

        self.metrics_json.parent.mkdir(parents=True, exist_ok=True)
        self.metrics_json.write_text(json.dumps(result, indent=2))
        logger.info("Phase '%s' stopped → %s", self.name, self.metrics_json)
        return result

    # --- threads ---
    def _spawn(self, target) -> None:
        t = threading.Thread(target=target, name=f"phase-{self.name}-{target.__name__}",
                             daemon=True)
        t.start()
        self._threads.append(t)

    def _sample_system(self) -> None:
        while not self._stop.is_set():
            s = self._sys_sampler() if self._sys_sampler else None
            if s is not None:
                ts = time.time()
                s["ts"] = ts
                self._res_samples.append(s)
                if self._res_csv:
                    self._res_csv.writerow([
                        round(ts, 3), s["cpu_pct"], s["mem_used_mi"], s["mem_avail_mi"],
                        s["disk_read_bytes"], s["disk_write_bytes"],
                        s["net_sent_bytes"], s["net_recv_bytes"],
                    ])
                    if self._res_fh:
                        self._res_fh.flush()
            self._stop.wait(self.cfg.metrics_sample_s)

    def _sample_power(self) -> None:
        while not self._stop.is_set():
            w = read_tasmota_power(self.cfg)
            if w is not None:
                ts = time.time()
                self._power_samples.append((ts, w))
                if self._pow_csv:
                    self._pow_csv.writerow([round(ts, 3), "wall", w])
                    if self._pow_fh:
                        self._pow_fh.flush()
            self._stop.wait(self.cfg.metrics_sample_s)


# =============================================================================
# Preflight — check the measurement chain before a run
# =============================================================================

def energy_probe(seconds: float = 4.0, cfg: Optional[BenchConfig] = None) -> dict:
    """Brief probe confirming we receive RAPL and/or wattmeter and system.

    Returns a diagnostic dict (reachable sources, labels, RAPL energy
    estimated over the window). ``labels`` empty ⇒ no source responds.
    """
    cfg = cfg or CFG
    labels: List[str] = []
    sys_src = cfg.resolved_system_source()
    out: dict = {
        "scaphandre_url": cfg.scaphandre_url if cfg.rapl_enabled else "(disabled)",
        "wattmeter_http": (cfg.wattmeter_http if cfg.wattmeter_enabled else "") or "(disabled)",
        "app_host": cfg.app_host,
        "docker_host": cfg.docker_host or "(local)",
        "system_source": sys_src,
        "psutil": psutil is not None,
    }

    rapl_start: Dict[str, float] = {}
    rapl_source = "none" if cfg.rapl_enabled else "disabled"
    if cfg.rapl_enabled:
        rapl_start = read_scaphandre(cfg)
        rapl_source = "scaphandre" if rapl_start else "none"
        if not rapl_start:
            rapl_start = read_rapl_sysfs(cfg)
            rapl_source = "sysfs" if rapl_start else "none"
    if rapl_start:
        labels += [f"rapl_{d}" for d in rapl_start]

    power_samples: List[Tuple[float, float]] = []
    t0 = time.time()
    while time.time() - t0 < seconds:
        if cfg.wattmeter_enabled:
            w = read_tasmota_power(cfg)
            if w is not None:
                power_samples.append((time.time(), w))
                if "wall" not in labels:
                    labels.append("wall")
        time.sleep(cfg.metrics_sample_s)

    system_sample: Optional[dict] = None
    if sys_src == "docker":
        n_containers = docker_running_count(cfg)
        out["docker_reachable"] = n_containers is not None
        out["docker_containers"] = n_containers if n_containers is not None else 0
        if n_containers:
            system_sample = read_docker_system_sample(cfg)
        if system_sample is not None:
            labels.append("system_docker")
    elif psutil is not None:
        psutil.cpu_percent(interval=None)   # prime the relative CPU measurement
        time.sleep(0.2)
        system_sample = _read_system_sample()
        if system_sample is not None:
            labels.append("system_psutil")

    rapl_energy: Dict[str, float] = {}
    if rapl_start:
        end = read_scaphandre(cfg) if rapl_source == "scaphandre" else read_rapl_sysfs(cfg)
        rapl_energy = _rapl_delta_joules(rapl_start, end)

    out.update({
        "rapl_source": rapl_source,
        "labels": labels,
        "power_samples": len(power_samples),
        "rapl_energy_J": rapl_energy,
        "system": system_sample,   # live CPU/mem sample (cpu_pct, mem_used_mi, containers)
    })
    return out
