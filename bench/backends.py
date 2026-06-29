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
import subprocess
import time
from typing import List, Optional

from .config import CFG, BenchConfig

logger = logging.getLogger(__name__)


class Backend:
    """Actuation interface."""

    scalable_default: str = ""

    def deploy(self, wait: bool = True) -> None: ...
    def scale(self, service: str, replicas: int) -> None: ...
    def replicas(self, service: str) -> int: ...
    def containers(self, service: str) -> List[str]: ...
    def teardown(self) -> None: ...


def _run(cmd: List[str], cfg: BenchConfig, check: bool = True,
         capture: bool = False) -> subprocess.CompletedProcess:
    logger.debug("exec: %s", " ".join(cmd))
    return subprocess.run(cmd, env=cfg.docker_env(), check=check,
                          capture_output=capture, text=True)


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

    def teardown(self) -> None:
        cmd = self._base() + ["down", "--remove-orphans"]
        if self.remove_volumes:
            cmd.append("-v")
        _run(cmd, self.cfg, check=False)
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
        _run(["docker", "stack", "deploy", "--detach=true",
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

    def teardown(self) -> None:
        _run(["docker", "stack", "rm", self.stack_name], self.cfg, check=False)
        logger.info("Swarm stack '%s' removed.", self.stack_name)


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
