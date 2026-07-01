# Scaling the Online Boutique (gRPC) + per-container metrics

This documents two related additions to the bench:

1. **gRPC load-balancing proxy variants** for `microservices-demo`, so that
   scaling its backend services actually adds capacity.
2. **Per-container resource metrics** (CPU / RAM / network / block IO), so the
   overhead of those proxies — and the load spread across replicas — can be
   measured.

---

## 1. Why the Online Boutique does not scale out of the box

The Boutique's services talk over **gRPC** (persistent HTTP/2). A gRPC client
opens **one** connection and pins it to a **single** backend replica; Docker
Compose DNS (and any L4 balancer — Swarm VIP, k8s ClusterIP) never re-spreads an
established connection. Measured directly: scaling a service to 4 replicas left
only **one** replica doing work — the others received **zero** traffic.

Consequence: adding replicas (or autoscaling) the Boutique **as-is is a no-op**.
You measure replica *count*, not replica *capacity*. (See `results/results/brk_synthesis.pdf`.)

The fix is **per-request** load balancing (not per-connection): a proxy in front
of each backend that resolves all replica IPs and round-robins each request.

> This is *not* a problem for the SoY monoliths: v4 is a single service, and v5's
> services sit behind **nginx (HTTP/1.1)**, which opens a connection per request
> and therefore already distributes.

---

## 2. The three variants

Selected via the `microservices-demo` infra `--variant` (see `bench/infra.py`):

| `--variant` | Proxy | What it is | Weight (9 sidecars) |
|-------------|-------|------------|---------------------|
| `node` (default) | none | baseline — shows the pinning | lightest |
| `envoy` | per-service Envoy | `STRICT_DNS` + `ROUND_ROBIN` + HTTP/2, re-resolves replicas dynamically | ~450–540 MB RAM |
| `nginx` | per-service nginx | Docker `resolver` + variable `grpc_pass` (DNS round-robin) | ~70–110 MB RAM |

Each proxy variant adds one sidecar per gRPC backend and repoints every
`*_SERVICE_ADDR` of the clients (frontend, checkoutservice, recommendationservice)
at its sidecar. **No application code changes.**

**Envoy vs nginx**
- **Envoy** — robust: native request-level `round_robin`, health checks, and
  dynamic endpoint discovery (picks up scale up/down automatically). Heavier;
  more overhead on the measured host.
- **nginx** — ~5× lighter (less pollution of the energy/CPU measurement) and
  consistent with v5. But its gRPC LB is DNS round-robin (with a short cache
  window), without active health checks — fine for **fixed** replicas under
  steady load, but the spread should be **verified empirically** (per-container
  CPU) on first deploy.

---

## 3. How to run

Through the bench (recommended):

```bash
# baseline (pinning), then Envoy, then nginx — scaling a few backends
run --infra microservices-demo --variant node  --scale-extra productcatalogservice=4,currencyservice=4
run --infra microservices-demo --variant envoy --scale-extra productcatalogservice=4,currencyservice=4
run --infra microservices-demo --variant nginx --scale-extra productcatalogservice=4,currencyservice=4
```

Raw docker compose (from the repo root):

```bash
docker compose -f microservices-demo/docker-compose.yml -f proxy/compose.envoy.yml up -d
docker compose -f microservices-demo/docker-compose.yml -f proxy/compose.envoy.yml up -d --scale productcatalogservice=4
```

> The proxy sidecars only help when you **scale** the backends. `--variant node`
> with scaled backends is the baseline that still pins to one replica.

---

## 4. Regenerating the proxy configs

The sidecar configs and compose overrides are **generated** into `proxy/` (in
the SoY-locust repo, so they are versioned with the harness) and distributed to
the hosts via `./xp.sh sync`:

```bash
python3 proxy/envoy/gen_envoy.py    # -> proxy/envoy/*.yaml + proxy/compose.envoy.yml
python3 proxy/nginx/gen_nginx.py    # -> proxy/nginx/*.conf + proxy/compose.nginx.yml
```

Each generator holds the single source of truth for the service→port map and the
client→target wiring. Edit the generator, re-run, then `./xp.sh sync`.

---

## 5. Per-container metrics (measuring the overhead)

`bench/metrics.py` now records **per-container** resource usage during each load
phase (docker source only; reuses the same `docker stats` call — no extra cost):

- **`<phase>.containers.csv`** — one row per container per sample:
  `ts, container, cpu_pct, mem_used_mi, net_recv_bytes, net_sent_bytes, disk_read_bytes, disk_write_bytes`
- **`<phase>.metrics.json` → `containers`** — per-container summary over the phase:
  `cpu_mean_pct, cpu_peak_pct, mem_mean_mi, mem_peak_mi, net_recv_mb, net_sent_mb, samples`

The aggregated `<phase>.resources.csv` is unchanged (sum over the project's
containers), so this is fully backward compatible.

Because the container filter is the compose project name (`onlineboutique`), the
proxy sidecars (`onlineboutique-envoy-…`, `onlineboutique-nginx-…`) are captured
too. Use it to:
- isolate each **proxy sidecar's** CPU/RAM/network cost (Envoy vs nginx), and
- verify the **load spread**: after the fix, every replica of a scaled service
  should show non-zero CPU (a live check is `svc_replicas.py`-style per-replica CPU).
