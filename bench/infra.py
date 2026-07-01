"""Registry of the infrastructures under test + backend factory.

Three infras, all driven via Docker (Compose primary):

  * ``monolith-v4``        — single-service ``node`` monolith (port 5001).
  * ``monolith-v5``        — split services, gateway-nginx entry point (port 80),
                             scalable service ``ms-exercise``.
  * ``microservices-demo`` — Online Boutique, ``frontend`` entry point (port 8080).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .backends import Backend, ComposeBackend, SwarmBackend
from .config import CFG, BenchConfig

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class DbFixup:
    """A SQL statement re-applied inside a service's DB container after deploy.

    Seeded images ship fixed data that can go stale: v4's ``plagesession`` window
    (``end_date``) has expired since the image was built, so every login fails.
    The DB is recreated on each fresh deploy, so the fix must run every run — this
    re-applies it without touching the image. ``psql`` is invoked inside the
    container, so no DB port needs to be exposed.
    """

    service: str               # service whose container runs the DB (e.g. "postgres")
    sql: str                   # SQL executed via `psql -c`
    db: str = "postgres"       # database name (psql -d)
    user: str = "postgres"     # psql role (-U)


@dataclass
class Infra:
    """Description of a target infrastructure."""

    name: str
    backend_kind: str            # "compose" | "swarm"
    compose_file: str            # path (repo-relative) of the compose/stack file
    project: str                 # compose project name / swarm stack name
    scalable_service: str        # service to scale
    host_port: int               # HTTP entry port of the app (on app_host)
    default_locustfile: str      # load-only locustfile
    cpu_limit_cores: float = 1.0  # cores/replica (util normalization)
    min_replicas: int = 1
    max_replicas: int = 8
    env_file: Optional[str] = None
    users_csv: Optional[str] = None     # per-infra login fixtures (None → soymono2/users.csv)
    signal_kind: str = "docker_stats"   # "docker_stats" | "prometheus"
    prometheus_port: int = 9090
    locust_metrics_url: str = "http://localhost:9646/metrics"  # gauge active_users
    # variants: name -> list of override compose files to layer.
    # Used to show the impact of a reimplementation (e.g. currencyservice by language).
    variants: Dict[str, List[str]] = field(default_factory=dict)
    default_variant: str = "default"
    # SQL re-applied inside the DB container right after each deploy (see DbFixup).
    db_fixups: List[DbFixup] = field(default_factory=list)
    notes: str = ""

    def path(self, rel: str) -> str:
        """Resolve a repo-relative path to an absolute one."""
        p = Path(rel)
        return str(p if p.is_absolute() else (REPO_ROOT / p))

    def host(self, cfg: Optional[BenchConfig] = None) -> str:
        """App entry URL (Locust target) on the app_host machine."""
        cfg = cfg or CFG
        return f"http://{cfg.app_host}:{self.host_port}"

    @property
    def host_url(self) -> str:
        return self.host()

    def prometheus(self, cfg: Optional[BenchConfig] = None) -> str:
        cfg = cfg or CFG
        return f"http://{cfg.app_host}:{self.prometheus_port}"

    def variant_names(self) -> List[str]:
        return [self.default_variant] + [v for v in self.variants if v != self.default_variant]

    def compose_files_for(self, variant: Optional[str]) -> List[str]:
        """Compose files (base + overrides) for the requested variant."""
        files = [self.path(self.compose_file)]
        v = variant or self.default_variant
        for override in self.variants.get(v, []):
            files.append(self.path(override))
        return files

    def make_backend(self, cfg: Optional[BenchConfig] = None,
                     variant: Optional[str] = None) -> Backend:
        cfg = cfg or CFG
        env_file = self.path(self.env_file) if self.env_file else None
        if self.backend_kind == "compose":
            # bench = NO storage: volumes always purged at teardown.
            # build=False: reuse pre-built images (e.g. currencyservice:<lang>); compose
            # still builds a service whose image is missing. Avoids rebuilding the variant
            # on every run (overhead) and re-hitting build-time network issues on the app host.
            return ComposeBackend(compose_files=self.compose_files_for(variant),
                                  project=self.project, env_file=env_file,
                                  remove_volumes=True, build=False, cfg=cfg)
        if self.backend_kind == "swarm":
            return SwarmBackend(stack_file=self.path(self.compose_file),
                                stack_name=self.project, cfg=cfg)
        raise ValueError(f"unknown backend_kind: {self.backend_kind}")

    def locustfile(self) -> str:
        return self.path(self.default_locustfile)


INFRA: Dict[str, Infra] = {
    "monolith-v4": Infra(
        name="monolith-v4",
        backend_kind="swarm",                # swarm stack: overlay net + ingress mesh on :5001
        compose_file="sou/monotloth-v4.yml",
        project="soy_v4",
        scalable_service="node",
        host_port=5001,
        default_locustfile="locust_file/load_monolith.py",
        users_csv="resources/soymono2/users_com.csv",   # v4 DB seeded with @yopmail.com
        cpu_limit_cores=1.0,
        min_replicas=1,
        max_replicas=8,
        signal_kind="docker_stats",
        # The seeded DB ships a `plagesession` whose window expired (end_date in the
        # past) → the login flow rejects every user. Re-open it on each fresh deploy.
        # Mirrors the proven manual runbook `sou/fix.sh` (which the human ran by hand):
        # bump BOTH plagesession.end_date AND studentstatement.deadline_date, on ALL
        # rows (no WHERE) — the blocking session is not guaranteed to be ps_id=1, and
        # the exercise step (request_3) needs an open deadline too. Date pushed far out.
        db_fixups=[
            DbFixup(
                service="postgres", db="plagedb", user="plagedba",
                sql="UPDATE plagesession SET end_date='2030-12-31';",
            ),
            DbFixup(
                service="postgres", db="plagedb", user="plagedba",
                sql="UPDATE studentstatement SET deadline_date='2030-12-31';",
            ),
        ],
        notes="Single-service `node` monolith. Image from private GitLab registry "
              "(auth required to pull).",
    ),
    "monolith-v5": Infra(
        name="monolith-v5",
        backend_kind="compose",
        compose_file="sou/monotloth-v5.yml",
        project="soy_v5",
        scalable_service="ms-exercise",
        host_port=80,
        default_locustfile="test.py",   # v5's own scenario (login→exercise flow, FastHttpUser)
        cpu_limit_cores=1.0,
        min_replicas=1,
        max_replicas=8,
        signal_kind="docker_stats",
        notes="Split services behind gateway-nginx (port 80). nginx-vts + "
              "cAdvisor + Prometheus available (signal_kind='prometheus' possible).",
    ),
    "microservices-demo": Infra(
        name="microservices-demo",
        backend_kind="compose",
        compose_file="microservices-demo/docker-compose.yml",
        project="onlineboutique",
        scalable_service="frontend",
        host_port=8080,
        # the Online Boutique's OWN load generator (the locustfile shipped with the stack)
        default_locustfile="microservices-demo/src/loadgenerator/locustfile.py",
        cpu_limit_cores=1.0,
        min_replicas=1,
        max_replicas=10,
        signal_kind="docker_stats",
        # Two variant axes (mutually exclusive here):
        #  - currencyservice language (energy/perf impact): node|go|python|java|csharp.
        #  - gRPC load-balancing proxy for real horizontal scaling (default = none):
        #    'envoy'/'nginx' add a per-service sidecar so scaling actually spreads load
        #    (plain compose pins each gRPC connection to one replica). Use these to
        #    compare no-proxy vs Envoy vs nginx (overhead + load spread).
        default_variant="node",
        variants={
            "node": [],  # official image (server.js), NO proxy = baseline
            "go": ["microservices-demo/compose.currency-go.yml"],
            "python": ["microservices-demo/compose.currency-python.yml"],
            "java": ["microservices-demo/compose.currency-java.yml"],
            "csharp": ["microservices-demo/compose.currency-csharp.yml"],
            "envoy": ["microservices-demo/compose.envoy.yml"],   # per-service Envoy gRPC LB
            "nginx": ["microservices-demo/compose.nginx.yml"],   # per-service nginx gRPC LB (lighter)
        },
        notes="Online Boutique (internal gRPC). No nginx-vts → λ/RT via the Locust "
              "web API; HPA (CPU via docker stats) fully supported. "
              "currencyservice variants: node|go|python|java|csharp. "
              "gRPC-scaling variants: envoy|nginx (per-service sidecar LB).",
    ),
}


def get_infra(name: str) -> Infra:
    if name not in INFRA:
        raise KeyError(f"unknown infra: {name!r}. Choices: {', '.join(INFRA)}")
    return INFRA[name]


def list_infra() -> List[str]:
    return list(INFRA)
