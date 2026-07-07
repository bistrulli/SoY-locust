"""Actuation backends: deployment & scaling of the infra under test.

Two implementations behind the same interface:

  * ``ComposeBackend`` (primary) — ``docker compose``: ``up -d`` / ``up -d --scale``
    / ``down``. This is the target of the HPA and of microservices-demo.
  * ``SwarmBackend`` — ``docker stack deploy`` / ``docker service scale`` / ``stack rm``
    (compat with the historical Swarm stacks).

Both honor a remote ``DOCKER_HOST`` via ``BenchConfig.docker_env()``.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from typing import Dict, List, Optional

from .config import CFG, BenchConfig

logger = logging.getLogger(__name__)


def _heal_enabled() -> bool:
    """Whether the Swarm self-heal (remote docker restart) is allowed. On by default."""
    v = os.environ.get("SOY_SWARM_HEAL", "1").strip().lower()
    return v not in ("0", "false", "no", "off", "")


def restart_remote_docker(cfg: BenchConfig, settle_s: float = 45.0,
                          ready_timeout_s: float = 180.0) -> bool:
    """Restart the Docker daemon on the app host to un-wedge a stuck Swarm dispatcher.

    The v4 stack runs on a REMOTE Swarm (``DOCKER_HOST=tcp://<app>:2375``). That
    dispatcher intermittently wedges: service tasks stay in state ``New`` (0 running)
    indefinitely, so ``stack deploy`` "succeeds" but no container ever starts and every
    request is ConnectionRefused — and, unattended, so does every subsequent run. The
    only known remedy is a daemon restart on the app host (passwordless
    ``sudo systemctl restart docker`` is provisioned there). This SSHes in, restarts it,
    and waits for the daemon + Swarm manager to come back active.

    Overridable via env:
      ``SOY_APP_SSH``            ssh target (default: ``cfg.app_host``)
      ``SOY_DOCKER_RESTART_CMD`` remote command (default: ``sudo systemctl restart docker``)
      ``SOY_SWARM_HEAL=0``       disable healing entirely (checked by callers)

    Returns True if the daemon came back with an active Swarm node, else False.
    """
    ssh_target = os.environ.get("SOY_APP_SSH") or cfg.app_host
    if not ssh_target or ssh_target in ("localhost", "127.0.0.1"):
        logger.error("Swarm heal: no remote app host to SSH into (app_host=%r) — cannot "
                     "restart docker. Set SOY_APP_SSH or a remote DOCKER_HOST.",
                     cfg.app_host)
        return False
    remote_cmd = os.environ.get("SOY_DOCKER_RESTART_CMD", "sudo systemctl restart docker")
    ssh_cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
               ssh_target, remote_cmd]
    logger.warning("Swarm heal: restarting docker on %s (`%s`)…", ssh_target, remote_cmd)
    try:
        res = subprocess.run(ssh_cmd, check=False, capture_output=True,
                             text=True, timeout=120)
    except Exception as e:
        logger.error("Swarm heal: ssh restart failed to launch: %s", e)
        return False
    if res.returncode != 0:
        # The daemon may still be bouncing (ssh can drop as docker restarts); log and
        # still wait below to see if it recovers.
        logger.error("Swarm heal: remote restart returned %d: %s", res.returncode,
                     (res.stderr or res.stdout or "").strip())
    time.sleep(settle_s)   # let the daemon socket + swarm reconciler come back up
    deadline = time.time() + ready_timeout_s
    while time.time() < deadline:
        info = subprocess.run(
            ["docker", "info", "--format", "{{.Swarm.LocalNodeState}}"],
            env=cfg.docker_env(), check=False, capture_output=True, text=True)
        if info.returncode == 0 and "active" in (info.stdout or ""):
            logger.warning("Swarm heal: docker on %s is back (Swarm active).", ssh_target)
            time.sleep(5)   # small grace for the dispatcher to resume scheduling
            return True
        time.sleep(3)
    logger.error("Swarm heal: docker on %s did not become Swarm-active within %.0fs.",
                 ssh_target, ready_timeout_s)
    return False


class Backend:
    """Actuation interface."""

    scalable_default: str = ""

    def deploy(self, wait: bool = True) -> None: ...
    def scale(self, service: str, replicas: int) -> None: ...
    def replicas(self, service: str) -> int: ...
    def containers(self, service: str) -> List[str]: ...
    def teardown(self) -> None: ...

    def scale_many(self, services: Dict[str, int]) -> None:
        """Scale several services at once (default: one call each)."""
        for svc, n in services.items():
            self.scale(svc, int(n))


def _run(cmd: List[str], cfg: BenchConfig, check: bool = True,
         capture: bool = False) -> subprocess.CompletedProcess:
    logger.debug("exec: %s", " ".join(cmd))
    return subprocess.run(cmd, env=cfg.docker_env(), check=check,
                          capture_output=capture, text=True)


def exec_in_container(container_id: str, argv: List[str], cfg: BenchConfig,
                      check: bool = True, capture: bool = False
                      ) -> subprocess.CompletedProcess:
    """Run a command inside a running container (honors remote DOCKER_HOST)."""
    return _run(["docker", "exec", container_id, *argv], cfg,
                check=check, capture=capture)


def _registry_of(image: str) -> str:
    """Registry host of an image ref ('gitlab.x:5050/a/b' -> 'gitlab.x:5050')."""
    host = image.split("/", 1)[0]
    if "." in host or ":" in host or host == "localhost":
        return host
    return "docker.io"  # bare 'name' / 'org/name' resolve to Docker Hub


_PUBLIC_REGISTRIES = {
    "docker.io", "index.docker.io", "registry-1.docker.io", "",
    "gcr.io", "ghcr.io", "quay.io", "registry.k8s.io", "k8s.gcr.io",
    "public.ecr.aws", "mcr.microsoft.com", "registry.gitlab.com",
}


def _is_private_registry(host: str) -> bool:
    return host not in _PUBLIC_REGISTRIES


# =============================================================================
# Docker Compose
# =============================================================================

class ComposeBackend(Backend):
    """Actuation via ``docker compose`` (scaling through ``--scale service=N``).

    Accepts several compose files (``-f base -f override ...``) to layer
    variants (e.g. currencyservice rewritten in another language).
    """

    def __init__(self, compose_files, project: str,
                 env_file: Optional[str] = None,
                 remove_volumes: bool = True,
                 build: bool = True,
                 cfg: Optional[BenchConfig] = None):
        if isinstance(compose_files, str):
            compose_files = [compose_files]
        self.compose_files = list(compose_files)
        self.compose_file = self.compose_files[0]
        self.project = project
        self.env_file = env_file
        self.remove_volumes = remove_volumes
        self.build = build  # build local images (variants) at deployment time
        self.cfg = cfg or CFG

    def _base(self) -> List[str]:
        cmd = ["docker", "compose"]
        for f in self.compose_files:
            cmd += ["-f", f]
        cmd += ["-p", self.project]
        if self.env_file:
            cmd += ["--env-file", self.env_file]
        return cmd

    def _up_cmd(self, wait: bool) -> List[str]:
        # --renew-anon-volumes: no anonymous volume reused between runs (clean state)
        cmd = self._base() + ["up", "-d", "--remove-orphans", "--renew-anon-volumes"]
        if self.build:
            cmd.append("--build")
        if wait:
            cmd.append("--wait")
        return cmd

    def deploy(self, wait: bool = True) -> None:
        err = self._try_up(wait)
        if err is not None and wait:
            # --wait may fail if a service has no healthcheck: retry without it
            logger.warning("compose up --wait failed, retrying without --wait")
            err = self._try_up(False)
        # OVERLAY-network projects (e.g. monotloth-v5.yml's `driver: overlay`) can hit a
        # brief Swarm control-plane race right after teardown recreates the network:
        # `compose up` fails fast with a transient "not a swarm manager" / network-create
        # error even though the daemon genuinely is a manager (confirmed via `docker node
        # ls` during this exact failure) — a settle-timing hiccup, not a real auth/config
        # problem. A few seconds' backoff + retry clears it every time observed.
        retry = 0
        while err is not None and retry < 3:
            retry += 1
            logger.warning("compose up failed (attempt %d) — retrying in 5s "
                           "(possible overlay-network settle race)…", retry)
            time.sleep(5)
            err = self._try_up(False)
        if err is not None:
            self._explain_and_raise(err)
        logger.info("Compose '%s' deployed (%s).", self.project,
                    ", ".join(self.compose_files))

    def _try_up(self, wait: bool) -> Optional[subprocess.CalledProcessError]:
        try:
            _run(self._up_cmd(wait), self.cfg)
            return None
        except subprocess.CalledProcessError as e:
            return e

    def _compose_images(self) -> List[str]:
        """Images resolved by compose (best-effort), to point at the failing pull."""
        res = _run(self._base() + ["config", "--images"], self.cfg,
                   check=False, capture=True)
        if res.returncode != 0 or not res.stdout:
            return []
        return [ln.strip() for ln in res.stdout.splitlines() if ln.strip()]

    def _explain_and_raise(self, err: subprocess.CalledProcessError) -> None:
        """Turn a raw compose failure into an actionable message (registry auth)."""
        images = self._compose_images()
        registries = sorted({r for r in (_registry_of(i) for i in images)
                             if _is_private_registry(r)})
        bar = "─" * 72
        lines = ["", bar,
                 f"❌ Deployment of '{self.project}' failed: `docker compose up` "
                 f"returned {err.returncode}.",
                 f"   compose : {', '.join(self.compose_files)}"]
        if images:
            lines.append(f"   images  : {', '.join(images)}")
        lines += ["", "Two common causes (see the docker output above for the exact one):"]
        lines += [
            "  A) PULL denied ('access forbidden'/'denied'/'unauthorized'):",
            "       - private registry not logged in → docker login <registry>",
            "       - daemon-wide mirror/proxy: docker info | grep -iE 'Mirror|Proxy'"]
        if registries:
            lines.append("       private registries here: " + ", ".join(registries))
        lines += [
            "  B) BIND-MOUNT error ('not a directory' / 'no such file' on a *.yml/*.conf):",
            "       compose bind-mounts resolve on the DAEMON's host (the app machine),",
            "       not where compose runs. The mounted files must exist THERE.",
            "       → mirror the repo to the app host:  ./xp.sh sync   (pushes both hosts)",
            bar]
        logger.error("\n".join(lines))
        raise RuntimeError(
            f"docker compose up failed for '{self.project}' — see the hint above "
            f"(likely registry auth; try `docker login`)") from err

    def scale(self, service: str, replicas: int) -> None:
        replicas = max(0, int(replicas))
        cmd = self._base() + ["up", "-d", "--no-recreate",
                              "--scale", f"{service}={replicas}", service]
        _run(cmd, self.cfg)
        logger.info("Compose: %s scaled to %d replica(s).", service, replicas)

    def scale_many(self, services: Dict[str, int]) -> None:
        """Scale several services in ONE `up` call so none resets another's replicas.

        A per-service ``up --scale X=n X`` reconciles X's ``depends_on`` services back
        to their default scale (1); scaling a service whose dependency was already
        scaled therefore silently resets that dependency. Passing every ``--scale`` in
        a single ``up`` (no positional service) avoids the reset.
        """
        services = {s: max(0, int(n)) for s, n in services.items() if n is not None}
        if not services:
            return
        cmd = self._base() + ["up", "-d", "--no-recreate", "--remove-orphans"]
        for svc, n in services.items():
            cmd += ["--scale", f"{svc}={n}"]
        _run(cmd, self.cfg)
        logger.info("Compose: scaled %s in one call.",
                    ", ".join(f"{s}={n}" for s, n in services.items()))

    def replicas(self, service: str) -> int:
        return len(self.containers(service))

    def containers(self, service: str) -> List[str]:
        """IDs of the service's *running* containers (for ``docker stats``)."""
        res = _run(self._base() + ["ps", "-q", service], self.cfg,
                   check=False, capture=True)
        if res.returncode != 0:
            return []
        return [line.strip() for line in res.stdout.splitlines() if line.strip()]

    def ps(self) -> list:
        """Detailed service state (list of dicts), best-effort."""
        res = _run(self._base() + ["ps", "--format", "json"], self.cfg,
                   check=False, capture=True)
        if res.returncode != 0 or not res.stdout.strip():
            return []
        out = []
        text = res.stdout.strip()
        try:  # recent compose: one JSON object per line
            for line in text.splitlines():
                out.append(json.loads(line))
        except json.JSONDecodeError:
            try:  # old compose: JSON array
                out = json.loads(text)
            except json.JSONDecodeError:
                return []
        return out

    def _overlay_networks(self) -> str:
        res = _run(["docker", "network", "ls", "--filter", f"name={self.project}_",
                   "--filter", "driver=overlay", "-q"], self.cfg, check=False, capture=True)
        return (res.stdout or "").strip()

    def teardown(self) -> None:
        had_overlay = bool(self._overlay_networks())
        cmd = self._base() + ["down", "--remove-orphans"]
        if self.remove_volumes:
            cmd.append("-v")
        _run(cmd, self.cfg, check=False)
        # `compose down` is ASYNC for OVERLAY networks (e.g. monotloth-v5.yml's
        # `driver: overlay, attachable: true`): the Swarm control-plane can still be
        # finishing internal cleanup (VXLAN/routing mesh teardown) even after the network
        # is gone from `docker network ls` — so the NEXT `compose up`, issued right after,
        # can race that and fail ("not a swarm manager" on network-create, a misleading
        # error for what's really a control-plane settle race — confirmed a genuine
        # manager throughout). Same class of bug as the v4 Swarm ghost-network wedge
        # (SwarmBackend.teardown), just with a settle-timing flavor instead of a stuck
        # listing. Plain bridge-network projects don't have this and skip the wait.
        if had_overlay:
            deadline = time.time() + 90
            while time.time() < deadline:
                time.sleep(3)
                if not self._overlay_networks():
                    break
            else:
                logger.warning("Compose '%s': overlay network(s) still listed after "
                               "90s wait — the next deploy may race a ghost network.",
                               self.project)
            # Even once gone from `network ls`, empirically the control-plane needs a
            # few more seconds before it reliably accepts a same-name overlay re-create
            # (a plain 2s post-teardown pause, as runner.py used, was NOT enough and hit
            # this ~100% of the time in testing). Settle before returning.
            time.sleep(8)
        logger.info("Compose '%s' stopped.", self.project)


# =============================================================================
# Docker Swarm
# =============================================================================

class SwarmBackend(Backend):
    """Actuation via Docker Swarm (``docker stack`` / ``docker service scale``)."""

    def __init__(self, stack_file: str, stack_name: str,
                 cfg: Optional[BenchConfig] = None):
        self.stack_file = stack_file
        self.stack_name = stack_name
        self.cfg = cfg or CFG

    def _ensure_swarm(self) -> None:
        info = _run(["docker", "info", "--format", "{{.Swarm.LocalNodeState}}"],
                    self.cfg, check=False, capture=True)
        if "active" not in (info.stdout or ""):
            _run(["docker", "swarm", "init"], self.cfg, check=False)

    def deploy(self, wait: bool = True) -> None:
        self._ensure_swarm()
        _run(["docker", "stack", "deploy", "--detach=true", "--with-registry-auth",
              "-c", self.stack_file, self.stack_name], self.cfg)
        logger.info("Swarm stack '%s' deployed.", self.stack_name)
        if wait:
            time.sleep(20)

    def scale(self, service: str, replicas: int) -> None:
        replicas = max(0, int(replicas))
        target = f"{self.stack_name}_{service}={replicas}"
        _run(["docker", "service", "scale", "--detach", target], self.cfg)
        logger.info("Swarm: %s scaled to %d replica(s).", service, replicas)

    def replicas(self, service: str) -> int:
        full = f"{self.stack_name}_{service}"
        res = _run(["docker", "service", "ps", full, "--filter",
                    "desired-state=running", "-q"], self.cfg,
                   check=False, capture=True)
        if res.returncode != 0:
            return 0
        return len([x for x in res.stdout.splitlines() if x.strip()])

    def containers(self, service: str) -> List[str]:
        full = f"{self.stack_name}_{service}"
        res = _run(["docker", "ps", "--filter", f"name={full}", "-q"],
                   self.cfg, check=False, capture=True)
        if res.returncode != 0:
            return []
        return [x.strip() for x in res.stdout.splitlines() if x.strip()]

    def wait_running(self, service: str, min_count: int = 1,
                     timeout_s: float = 120.0, interval_s: float = 3.0) -> int:
        """Poll until at least ``min_count`` of the service's containers are RUNNING.

        Uses ``containers()`` (real running containers via ``docker ps``), NOT
        ``replicas()`` — the latter counts *desired-state* tasks and so stays > 0 even
        when the dispatcher is wedged and nothing actually runs. Returns the running
        count reached (may be < ``min_count`` on timeout).
        """
        deadline = time.time() + timeout_s
        n = len(self.containers(service))
        while n < min_count and time.time() < deadline:
            time.sleep(interval_s)
            n = len(self.containers(service))
        return n

    def heal(self, settle_s: float = 45.0) -> bool:
        """Un-wedge the remote Swarm: restart the app-host daemon, re-init swarm, re-deploy.

        Called by the runner when the scalable service scheduled 0 containers (the wedge
        signature). Returns True once the stack has been re-deployed on a recovered
        daemon; the caller then re-scales and re-checks. No-op-safe: returns False if
        healing is disabled (``SOY_SWARM_HEAL=0``) or the restart failed.
        """
        if not _heal_enabled():
            logger.warning("Swarm heal requested but disabled (SOY_SWARM_HEAL=0).")
            return False
        if not restart_remote_docker(self.cfg, settle_s=settle_s):
            return False
        try:
            self._ensure_swarm()
            self.deploy(wait=True)   # idempotent re-reconcile of the stack
        except Exception as e:
            logger.error("Swarm heal: re-deploy after restart failed: %s", e)
            return False
        return True

    def teardown(self) -> None:
        _run(["docker", "stack", "rm", self.stack_name], self.cfg, check=False)
        # `stack rm` is ASYNC: it returns before the services and the overlay network
        # are actually gone. Wait for full removal, otherwise the NEXT `stack deploy`
        # collides ("network is in use by task" / "already exists") and the run fails.
        deadline = time.time() + 90
        while time.time() < deadline:
            time.sleep(3)
            ps = _run(["docker", "stack", "ps", self.stack_name, "-q"],
                      self.cfg, check=False, capture=True)
            net = _run(["docker", "network", "ls", "--filter",
                        f"name={self.stack_name}_", "-q"],
                       self.cfg, check=False, capture=True)
            tasks_gone = ps.returncode != 0 or not (ps.stdout or "").strip()
            nets_gone = not (net.stdout or "").strip()
            if tasks_gone and nets_gone:
                break
        logger.info("Swarm stack '%s' removed (fully torn down).", self.stack_name)


# =============================================================================
# Stub backend — for --dry-run (no Docker required)
# =============================================================================

class StubBackend(Backend):
    """Simulates actuation in memory; records the scaling decisions."""

    def __init__(self, start_replicas: int = 1):
        self._replicas: dict = {}
        self._start = start_replicas
        self.history: list = []

    def deploy(self, wait: bool = True) -> None:
        logger.info("[dry-run] deploy")

    def scale(self, service: str, replicas: int) -> None:
        replicas = max(0, int(replicas))
        self._replicas[service] = replicas
        self.history.append((service, replicas))
        logger.info("[dry-run] scale %s -> %d", service, replicas)

    def replicas(self, service: str) -> int:
        return self._replicas.get(service, self._start)

    def containers(self, service: str) -> List[str]:
        return [f"stub-{service}-{i}" for i in range(self.replicas(service))]

    def teardown(self) -> None:
        logger.info("[dry-run] teardown")
