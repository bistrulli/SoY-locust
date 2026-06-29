# SoY-locust — Autoscaling & energy comparison harness

A test bench to **compare scaling strategies** for containerized applications, with
**identical** infrastructure and actuation, measuring **performance** (latency,
throughput) **and energy** (RAPL + wall power meter). Built around Locust for the load,
remote Docker for deploy/scaling, Scaphandre for RAPL and a Tasmota plug for wall power.

We compare these strategies, all behind a single `decide(ctx) -> replicas` interface so
only the **decisions** differ (same infra, same signal, same actuation):

| Strategy | Description |
|---|---|
| `none` | no autoscaler (replicas frozen at `initial_replicas`) — baseline |
| `manual` | manual scaling at **fixed replicas** (`fixed_replicas`) |
| `manual-sched` | **scheduled** manual scaling (a `t:replicas` staircase aligned with the load) |
| `uopt` | **optimization model** `OPTCTRL` (SCIP/CasADi); the "optimal" controller |
| `hpa` | **Kubernetes HPA-style** autoscaler reimplemented in Python (CPU vs target) |

…on **3 stacks**: `monolith-v4`, `monolith-v5`, `microservices-demo` (Online Boutique).
For Online Boutique you can also **measure the language impact**: `currencyservice` is
rewritten in `go`, `python`, `java`, `csharp` (vs `node` by default).

> The `bench/` package + `xp.sh` + `run_experiment.py` are the **restructured** path.
> The legacy flow (`run_load_test.py`, `1_run_xps.py`, `0_auto-run.py`) is still present;
> the old README is kept in `README.bkp.md`.

---

## Table of contents

1. [Topology](#1-topology-load--app-split)
2. [Requirements](#2-requirements)
3. [Quick start](#3-quick-start)
4. [Configuration (`config.env`)](#4-configuration-configenv)
5. [The `xp.sh` driver](#5-the-xpsh-driver)
6. [Concepts](#6-concepts)
7. [Per-infrastructure notes](#7-per-infrastructure-notes) ← the stack-specific gotchas
8. [Reproducibility](#8-reproducibility)
9. [Metrics & energy](#9-metrics--energy)
10. [Outputs & aggregation](#10-outputs--aggregation)
11. [CLI reference](#11-cli-reference-run_experimentpy)
12. [Architecture](#12-architecture-bench)
13. [Troubleshooting](#13-troubleshooting)
14. [Methodology](#14-methodology-white-paper)

---

## 1. Topology (load ↔ app split)

The harness **and** Locust run on the **load machine**; the application runs on a
**remote app machine** driven by remote Docker. **Locust is NOT a container of the
stack** — it is a process launched on the load machine (the Online Boutique compose
`loadgenerator` is deliberately excluded; we run its locustfile ourselves).

```
   load machine : 192.168.3.101   ← run ./xp.sh HERE (harness + Locust process)
            │  docker -H 192.168.3.102 :  deploy / scale / docker stats
            │  Locust  --host http://192.168.3.102:<port>
            ▼
   app machine     : 192.168.3.102   ← remote Docker + Scaphandre (RAPL)
   Tasmota meter   : 192.168.3.131   ← wall power (HTTP)
```

Consequences (all wired in `config.env` + `xp.sh`):

- deploy/scaling via `DOCKER_HOST=tcp://192.168.3.102:2375`;
- Locust targets `192.168.3.102` (`BENCH_APP_HOST`);
- **app system metrics via remote `docker stats`** (`SYS_SOURCE=docker`) — *not* psutil,
  which would measure the load machine;
- RAPL via Scaphandre (on the app), wall energy via Tasmota.

> **Two important consequences of the split** (see [Troubleshooting](#13-troubleshooting)):
> 1. `docker login` for a private image must be done **on the load machine** — compose
>    reads the client's credentials and forwards them to the remote daemon.
> 2. compose **bind-mounts resolve on the app machine** (the daemon's host), so config
>    files (`prometheus.yml`, nginx confs…) must exist there too → `./xp.sh sync` pushes
>    the source to **both** machines.

---

## 2. Requirements

**Load machine** (where `xp.sh` runs):

```bash
pip install -r requirements.txt          # locust, prometheus-api-client, docker, scipy,
                                          # casadi, pyscipopt, pandas, matplotlib, faker…
```

`screen` is recommended (detachable runs); without it `xp.sh` falls back to `setsid`.

**App machine** (`192.168.3.102`):

| Component | Role | Absent ⇒ |
|---|---|---|
| Docker + Compose v2, API on `:2375` | deployment & scaling | nothing runs |
| **Scaphandre** (`:9999`, Prometheus exporter) | RAPL counters | no RAPL (Linux sysfs fallback, or `RAPL_ENABLED=0`) |
| **Tasmota** plug (HTTP) | wall energy | no wattmeter (or `WATTMETER_ENABLED=0`) |
| **No `k3s`** on `:80` | — | its Traefik ingress hijacks port 80 → every request 404s (see Troubleshooting) |

```bash
# on the app machine:
scaphandre prometheus --address 0.0.0.0 --port 9999      # -> :9999/metrics
# expose the Docker daemon on tcp://0.0.0.0:2375 (trusted network only)
```

---

## 3. Quick start

```bash
# 1. (dev box) point config.env at your machines if they differ from the defaults
$EDITOR config.env

# 2. push the source to BOTH machines (load + app: the app needs the bind-mounted confs)
./xp.sh sync

# 3. (load machine) preflight + run the whole matrix, inside a screen named soy-xp-run1
RUN_TAG=run1 ./xp.sh go            # go = check (energy/CPU/mem) → start
#   the screen IS the executor → screen -r soy-xp-run1 shows it live
#   AUTO-resume: skips runs whose result.json already exists

# 4. follow / control (always prefix the same RUN_TAG)
RUN_TAG=run1 ./xp.sh watch         # attach the live executor (Ctrl-A D to detach)
RUN_TAG=run1 ./xp.sh status        # progress, current run, nb of results, screen state
RUN_TAG=run1 ./xp.sh follow        # read-only tail of results/run1/console.log
RUN_TAG=run1 ./xp.sh stop          # quit the screen (stops the run) + teardown the infra

# 5. aggregate + report
./xp.sh aggregate                  # -> results/summary.csv
./xp.sh report                     # -> results/report/ (figures + report.pdf)
```

Run **a single** experiment — the one configured in `config.env` (`TEST_*`), or ad-hoc:

```bash
RUN_TAG=t1 ./xp.sh test            # the configured test (TEST_INFRA/TEST_CONTROLLER/…)
./xp.sh start run --infra microservices-demo --controller hpa --variant go \
    --users 300 --run-time 300s    # ad-hoc, full control
```

Validate the logic **without Docker or Locust** (stub backend + synthetic signal):

```bash
python run_experiment.py run --infra monolith-v5 --controller hpa --dry-run
```

---

## 4. Configuration (`config.env`)

**Everything** lives in `config.env` — the two machines, ports, derived endpoints,
measurement, energy toggles, reproducibility and the single-test selection. `xp.sh`
sources it automatically. Every value uses `${VAR:-default}`, so an environment variable
set beforehand still wins (no edit needed for a one-off):

```bash
APP_HOST=10.0.0.9 ./xp.sh go
WATTMETER_ENABLED=0 ./xp.sh test
```

For direct use of `python run_experiment.py` (without `xp.sh`), run `source config.env` first.

| Key | Default | Meaning |
|---|---|---|
| `LOAD_HOST` | `192.168.3.101` | load machine: runs the harness + Locust |
| `APP_HOST` | `192.168.3.102` | app machine: remote Docker daemon + Scaphandre |
| `WATTMETER_HOST` | `192.168.3.131` | Tasmota plug |
| `DOCKER_PORT` / `SCAPHANDRE_PORT` | `2375` / `9999` | ports on the app machine |
| `BENCH_APP_HOST` | `$APP_HOST` | Locust `--host` target |
| `DOCKER_HOST` | `tcp://$APP_HOST:$DOCKER_PORT` | remote Docker (deploy/scale/stats) |
| `SCAPHANDRE_URL` | `http://$APP_HOST:$SCAPHANDRE_PORT/metrics` | RAPL exporter |
| `WATTMETER_HTTP` | `http://$WATTMETER_HOST` | Tasmota endpoint (empty ⇒ disabled) |
| `LOAD_DIR` | `SoY-locust` | dir under `$HOME` on both machines (used by `sync`) |
| `SYS_SOURCE` | `docker` | app system metrics: `docker` \| `psutil` \| `auto` |
| `METRICS_SAMPLE_S` | `1.0` | sampling step (s) |
| `RAPL_ENABLED` | `1` | `0` ⇒ skip Scaphandre **and** sysfs RAPL entirely |
| `WATTMETER_ENABLED` | `1` | `0` ⇒ skip the Tasmota wattmeter entirely |
| `BENCH_SEED` | `42` | seeds `random` + Faker in the locustfiles (reproducibility) |
| `BENCH_RPS_PER_USER` | `1.0` | offered iterations/s per user (constant throughput) |
| `SHAPE_RAMP_S`/`SHAPE_PLATEAU_S`/`SHAPE_PAUSE_S`/`SHAPE_CYCLES` | `30`/`60`/`30`/`5` | cyclical loadshape timing → 5 × 120s = 600s |
| `TEST_INFRA`/`TEST_CONTROLLER`/`TEST_VARIANT`/`TEST_USERS`/`TEST_RUN_TIME` | `monolith-v5`/`none`/``/`100`/`120s` | the single experiment run by `./xp.sh test` |

**No energy endpoint?** Set `RAPL_ENABLED=0` and/or `WATTMETER_ENABLED=0`. The source is
skipped completely (no probing, no sysfs fallback); `check` shows it as `[--] disabled`
and the verdict stays ✅ as long as CPU/mem works.

---

## 5. The `xp.sh` driver

`xp.sh` is the one-command entry point. The run lives **inside a `screen`** so it survives
the terminal closing / an SSH drop.

| Command | What it does |
|---|---|
| `./xp.sh go [matrix …\|run …]` | `check` (preflight) then `start` — recommended |
| `./xp.sh start` | run the whole `experiments.yaml` matrix in a detached screen |
| `./xp.sh start matrix --file X.yaml` | run a specific matrix file |
| `./xp.sh start run --infra … --controller …` | run one ad-hoc experiment |
| `./xp.sh start --force` | re-run everything (ignore already-done runs) |
| `./xp.sh test` | run ONE experiment configured by `TEST_*` (extra args pass through) |
| `./xp.sh watch` | attach the live executor screen (= `screen -r soy-xp-<RUN_TAG>`) |
| `./xp.sh status` | screen state + current run + nb of `result.json` + tail of the log |
| `./xp.sh follow` | read-only `tail -f results/<RUN_TAG>/console.log` |
| `./xp.sh stop` | quit the screen (stops the run) + teardown all infra |
| `./xp.sh check [--json]` | probe the energy/system chain, print an explicit verdict |
| `./xp.sh aggregate` | `results/<RUN_TAG>/` → `summary.csv` |
| `./xp.sh report` | figures + LaTeX/PDF white-paper report |
| `./xp.sh sync` | (from the dev box) rsync the source → load **and** app machines |

### Campaigns & resume — `RUN_TAG`

`RUN_TAG` is the **idempotency key** of a campaign: it names `results/<RUN_TAG>/` **and**
the screen session `soy-xp-<RUN_TAG>`. Two campaigns with distinct tags run in parallel
without colliding.

- **Auto-resume**: relaunching `start`/`go` with the **same `RUN_TAG`** skips the runs
  whose `result.json` already exists. `result.json` is written only at the very end of a
  run, so a crash leaves no file ⇒ that run is re-measured in full (clean resume).
- `--force` re-measures everything.

> ⚠️ **The run lives INSIDE the screen.** Detach without stopping it: `Ctrl-A` then `D`.
> `Ctrl-C` / `exit` / closing the screen **stops** the run. The full log is mirrored to
> `results/<RUN_TAG>/console.log` (via `tee`) so `follow`/`status` work regardless.
> Full guide: **[`METHODE-screen.md`](METHODE-screen.md)**.

### The `check` verdict

`./xp.sh check` (also run by `go`) probes the chain **before** launching and exits `0` if
OK, `1` otherwise:

```
  [OK] RAPL energy (scaphandre)   host_J=… J  package_J=… J
  [OK] Wattmeter (Tasmota)    4 power sample(s)
  [..] CPU/mem (docker)       daemon OK, 0 container — normal before deploy;
                              captured live from `docker stats` during the run
VERDICT: ✅ ALL OK — RAPL + wattmeter + CPU/mem ready to record.
```

`[OK]` confirmed · `[..]` OK but to confirm at run time · `[!!]` problem · `[--]` disabled.

---

## 6. Concepts

### Infrastructures (`bench/infra.py`)

| Infra | Scaled service | App port | Locustfile | Variants |
|---|---|---|---|---|
| `monolith-v4` | `node` | 5001 | `locust_file/load_monolith.py` | — |
| `monolith-v5` | `ms-exercise` | 80 | `test.py` | — |
| `microservices-demo` | `frontend` | 8080 | `microservices-demo/src/loadgenerator/locustfile.py` | `node` (def.) · `go` · `python` · `java` · `csharp` |

See [Per-infrastructure notes](#7-per-infrastructure-notes) for the stack-specific setup.

### Controllers (`bench/controllers.py`)

- **`hpa`**: Kubernetes HPA v2 — `desired = ceil(cur · util/target)`, 10% tolerance,
  stabilization windows (immediate scale-up, conservative scale-down).
- **`uopt`**: `OPTCTRL` wrapper (SCIP/CasADi); falls back to an M/M/S formula if unavailable.
- **`manual`**: N fixed replicas. **`manual-sched`**: a `t:replicas` staircase. **`none`**: frozen.

### Loadshapes (`bench/loadshapes/`)

Standalone, infra-agnostic load profiles. Amplitude is `--users`; timing from `SHAPE_*`.

| Shape | Profile | Variables |
|---|---|---|
| `constant.py` | flat at `--users` | `SHAPE_TOTAL_S` |
| `rampup.py` | ramp 0 → `--users` | `SHAPE_RAMP_S` |
| `step.py` | rising staircase | `SHAPE_STEP_S`, `SHAPE_STEP_USERS` |
| `peak.py` | ramp → peak → ramp-down | `SHAPE_RAMP_S`, `SHAPE_PEAK_S` |
| `cyclical.py` | N cycles ramp/plateau/pause | `SHAPE_RAMP_S`, `SHAPE_PLATEAU_S`, `SHAPE_PAUSE_S`, `SHAPE_CYCLES` |
| `capacity.py` | stepped ramp until break | `SHAPE_STEPS`, `SHAPE_STEP_S` |

### Normalized throughput

Each user triggers its scenario at a **fixed rate**
(`wait_time = constant_throughput(BENCH_RPS_PER_USER)`), independent of response time.
The **offered throughput** = `users × BENCH_RPS_PER_USER` is therefore identical across
infra → energy/perf compared at equal offered load, not at equal user count.

### Capacity test (`--capacity`)

A **stepped ramp** + a **probe** (`bench/capacity.py`) that watches, live, the failure
rate and p95 latency via the Locust web API, and reports the **knee** (`knee_rps`, max
sustained under the threshold) and the **breaking point** (`breaking_rps`, first
throughput where the failure rate exceeds `--fail-threshold`, default 2%) — and stops the
run at the breaking point (unless `--no-stop-on-break`). Normal (non-capacity) runs never
stop on break; they always run the full `run_time`.

---

## 7. Per-infrastructure notes

> These capture the **stack-specific setup** discovered while bringing the three infra up.

### `monolith-v4` (single `node` service, port 5001)

- **Private image**: the `node` image comes from `gitlab.polytech.umontpellier.fr:5050`.
  Run `docker login gitlab.polytech.umontpellier.fr:5050` **on the load machine** before
  the first deploy (compose forwards the client's creds to the remote daemon).
- **Login fixtures**: the scenario logs in, and v4's DB is seeded with `@yopmail.com`
  users → it uses `resources/soymono2/users_com.csv` (wired via `users_csv` in `infra.py`,
  passed to the locustfile as `SOY_USERS_CSV`). Using the `.fr` set here yields 100% login
  failures.

### `monolith-v5` (split services behind gateway-nginx, port 80)

- **Gateway auth routing**: the Express gateway (`v5-gw-mod`) only proxies
  `/api/exercise-production` and `/api/student-statement` to `ms-exercise`. The auth
  routes (`/api/user/*`, `/api/auth/*`) are served by **`ms-other`** but the gateway does
  not route to it, so `sou/nginx-config/gateway.conf` routes those paths to `ms-other`
  at the nginx level. (This is already committed.)
- **Login fixtures**: v5's DB is seeded with `@yopmail.fr` users → the scenario (`test.py`)
  reads `resources/soymshttp1/users.csv` (the default, no `SOY_USERS_CSV` override).
- **⚠️ No `k3s` on the app machine**: a leftover k3s installs a Traefik ingress that
  hijacks port 80 (it answers a Go-style `404 page not found` to everything). Disable it:
  `sudo /usr/local/bin/k3s-killall.sh` then `sudo systemctl disable k3s`.
- **Bind-mounts**: the nginx/prometheus configs are bind-mounted → they must exist on the
  app machine. `./xp.sh sync` pushes the source to both hosts.

### `microservices-demo` (Online Boutique, frontend port 8080)

- **Load generator**: uses the stack's own `src/loadgenerator/locustfile.py` (the official
  Boutique loadgen: browse, cart, setCurrency, checkout).
- **Frontend env**: the `frontend` (v0.10.5) panics at startup if
  `SHOPPING_ASSISTANT_SERVICE_ADDR` is unset → it is set (to a dummy) in
  `microservices-demo/docker-compose.yml`, even though the assistant page is never hit.
- **Polyglot variants**: `currencyservice` is rebuilt from
  `src/currencyservice-alternatives/<lang>` and pushed to
  `registry.gitlab.com/inria-mpl/soy/currencyservice:<lang>`. With `build=False` the
  harness reuses the existing/pulled image (only builds if missing). The compose overrides
  are `compose.currency-*.yml`.

> `microservices-demo/` is a **nested git repo** (the Online Boutique clone); it is ignored
> by the parent and its fixes are committed in its own history.

---

## 8. Reproducibility

The **offered load is deterministic** so a re-run reproduces the same input:

- **`BENCH_SEED`** (default 42) seeds Python `random` and Faker in the locustfiles;
- the login scenario picks users **deterministically by spawn index** (no random pick);
- **`BENCH_RPS_PER_USER`** fixes the per-user rate (constant throughput, independent of RT);
- the cyclical loadshape timing is pinned via `SHAPE_RAMP_S`/`SHAPE_PLATEAU_S`/`SHAPE_PAUSE_S`/`SHAPE_CYCLES`;
- each run starts from a **fresh** infra (`down -v` + `--renew-anon-volumes`).

The app's behaviour under load and the scaling decisions remain physical (not bit-identical),
but the **input load is reproducible**.

---

## 9. Metrics & energy (`bench/metrics.py`)

Each load is framed by a **`Phase` window** (`start()`/`stop()`) collecting 3 streams,
each optional and resilient:

| Stream | Source | Output |
|---|---|---|
| **System** | remote `docker stats` (app) or psutil (local) | CPU %, mem, disk/net IO |
| **RAPL** | Scaphandre (`scaph_*_energy_microjoules`, Δ at boundaries); sysfs fallback | Joules per domain (package/cores/dram/host) |
| **Wall** | **Tasmota** plug (HTTP power, `Σ W·dt`) | Joules + peak watts |

> **RAPL ≠ wattmeter.** RAPL = energy internal to the CPU package (exact counter); the
> wattmeter = consumption at the plug (CPU + RAM + disks + PSU). The `wall_over_rapl`
> ratio separates the CPU cost from the rest of the machine.

A **live heartbeat** is logged every ~10s during the load
(`load @Ns: U users | R req/s (good G) | fail X% | p95 P ms`), and the Locust output is
echoed into the run log (`[locust] …`, disable with `BENCH_LOCUST_ECHO=0`).

Either energy source can be turned off (`RAPL_ENABLED=0`, `WATTMETER_ENABLED=0`) when no
endpoint is available — see [Configuration](#4-configuration-configenv).

---

## 10. Outputs & aggregation

```
results/<RUN_TAG>/
  console.log                  # whole-campaign log (tee of the screen)
  <tag>/
    config.json                # spec + resolved parameters (host, variant, compose…)
    energy_probe.json          # preflight of the measurement sources
    result.json               # run summary (written only at the end → drives resume)
    locust_stats.csv           # latency p50..p100, RPS, failures (aggregated)
    locust_stats_history.csv   # TIME SERIES (--csv-full-history) — for the curves
    locust_failures.csv        # detailed failures
    locust.log                 # raw Locust output
    scaling/<service>.csv      # 1 row/tick: repl_cur, repl_desired, cpu_util, λ, RT, users
    capacity/<service>.csv     # (--capacity) throughput/failures/p95 vs offered load
    metrics/load.metrics.json  # system aggregates + RAPL + wall (+ wall_over_rapl)
    metrics/load.resources.csv # raw system samples
    metrics/load.power.csv     # raw Tasmota power samples
```

`<tag>` = `<infra>__<controller>__<variant>__<loadshape>__rep<N>`.

```bash
./xp.sh aggregate              # results/<RUN_TAG>/ -> summary.csv (1 row per run)
./xp.sh report                 # figures + report.tex/report.pdf in results/report/
```

`summary.csv` cross-tabulates, per run: energy (RAPL package/cores/dram + wall), system
(CPU/mem/IO), scaling (replica·seconds, action count, mean/max replicas), perf (requests,
failures, RPS, p95/p99 latency), capacity (`knee_rps`, `breaking_rps`) and the derived
**energy/request** metrics (`wall_J_per_req`, `rapl_package_J_per_req`). The report needs
`matplotlib` + `pandas`, and a LaTeX distribution for the PDF (`--no-pdf` to skip it).

---

## 11. CLI reference (`run_experiment.py`)

```
run        run ONE experiment
matrix     unroll a YAML matrix (experiments.yaml); auto-resume, --force to re-run all
check      probe the energy/system measurement chain
aggregate  aggregate results/ -> summary.csv
report     figures + LaTeX/PDF report (white paper)
down       teardown of all infra (cleanup)
list       list infra / controllers / variants
```

Useful `run` options: `--infra` `--controller` `--variant` `--loadshape` `--users`
`--run-time` `--target-util` `--min-replicas` `--max-replicas` `--fixed-replicas`
`--schedule 0:1,60:3,120:2` `--control-period` `--hpa-tolerance` `--hpa-downscale`
`--uopt-method {scip,casadi}` `--rps-per-user` `--capacity` `--fail-threshold`
`--sla-p95-ms` `--no-stop-on-break` `--keep-up` `--tag` `--rep` `--dry-run`.

### Comparison matrix (`experiments.yaml`)

```yaml
defaults:
  run_time: 600s
  target_utilization: 0.2
  reps: 3
  fixed_replicas: 4
  schedule: [[0,1],[120,3],[300,6],[480,2]]
  loadshape: bench/loadshapes/cyclical.py
experiments:
  - infra: monolith-v5
    controllers: [none, manual, manual-sched, uopt, hpa]
    users: 200
  - infra: microservices-demo            # language impact, under HPA
    controllers: [hpa]
    variants: [node, go, python, java, csharp]
    users: 300
```

Each entry is multiplied by `controllers × variants × reps`. A focused
`experiments_v5_msdemo.yaml` (v5 + msdemo only) is provided.

---

## 12. Architecture (`bench/`)

| File | Role |
|---|---|
| `config.py` | env-based configuration (`BenchConfig`) |
| `metrics.py` | `Phase` (system + RAPL Scaphandre + Tasmota) + `energy_probe` + heartbeat |
| `backends.py` | `ComposeBackend` (`docker compose --scale`, registry-auth hints), `SwarmBackend`, `StubBackend` |
| `infra.py` | infra + variants registry (per-infra locustfile, login fixtures, build flag) |
| `controllers.py` | `uopt`, `hpa`, `manual`, `manual-sched`, `none` + factory |
| `signals.py` | control signal (docker stats / Locust web API; or Prometheus) |
| `scaling.py` | loop: sample → decide → actuate → log |
| `capacity.py` | capacity probe: breaking-point detection |
| `locustctl.py` | Locust launch (`python -m locust`, log echo) |
| `locustfiles/` | normalized-throughput locustfiles (Online Boutique; monolith via `locust_file/`) |
| `loadshapes/` | standalone profiles (constant/rampup/step/peak/cyclical/capacity) |
| `runner.py` | full life cycle of an experiment |
| `aggregate.py` / `report.py` | `results/` → `summary.csv` / figures + PDF |
| `../run_experiment.py` | CLI · `../xp.sh` driver · `../config.env` central config |

Tests: `python -m unittest bench.tests.test_controllers` and
`./tests/test_xp_orchestration.sh` (orchestration smoke test).

---

## 13. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `check` → `VERDICT: ❌ NOTHING responds` | no source responds | check Scaphandre/Tasmota/network, or disable them (`RAPL_ENABLED=0` / `WATTMETER_ENABLED=0`) |
| `check` → `[!!] CPU/mem (docker) daemon UNREACHABLE` | `DOCKER_HOST` unreachable | check `:2375` / network on the app machine |
| `docker compose up` → `error from registry: access forbidden` | private image not logged in, or a **stale token** forwarded by compose | `docker login <registry>` (e.g. `gitlab.polytech.umontpellier.fr:5050`) **on the load machine**; if it was a stale Hub token, `docker logout` first |
| deploy fails with `not a directory` on a `*.yml`/`*.conf` | bind-mount file missing on the **app machine** (the daemon's host) | `./xp.sh sync` (pushes to both hosts) |
| **every request 404s** with `404 page not found` (Go, no `Server` header) | **k3s/Traefik** hijacking port 80 on the app machine | `sudo /usr/local/bin/k3s-killall.sh` + `sudo systemctl disable k3s` |
| Locust → `No such file or directory: 'locust'` | `~/.local/bin` not on PATH | already handled — the harness runs `python -m locust` |
| Locust → `Address already in use: ('', 8089)` | a ghost Locust from a killed screen holds the web port | `pkill -f '[l]ocust -f'` then relaunch |
| **100% login failures** | wrong user fixtures for the infra's DB | v4 needs `@yopmail.com` (`users_com.csv`), v5 needs `@yopmail.fr` (`soymshttp1`) |
| `FastResponse object has no attribute 'cookies'` | `FastHttpUser` has no `.cookies` | use `HttpUser` (already set in `test.py`) |
| Scaling has no effect | `DOCKER_HOST` unreachable, or wrong scalable service | check `DOCKER_HOST` and `./xp.sh list` (`list` shows the scalable service) |
| `uopt` falls back to M/M/S | `casadi`/`pyscipopt` missing | see `requirements.txt` |

---

## 14. Methodology (white paper)

- **Fair comparison**: uopt/hpa/manual share infra, signal and actuation
  (`docker compose --scale`); only the **decisions** differ.
- **Energy attribution**: RAPL and wall are machine-level → isolate only **one** system
  under load at a time to attribute energy to a controller/language.
- **RAPL counter** cumulative, read at the boundaries (negative wrap deltas ignored).
- **Reproducible load**: deterministic users + seed + pinned rate/shape (§8).
- **No storage (systematic purge)**: the bench persists **nothing**. Each run cleans the
  infra before AND after (`docker compose down -v` → containers **and volumes** removed)
  and deploys with `--renew-anon-volumes` → DB/cache always fresh, even after an
  interruption. This is unconditional. Safety nets: `./xp.sh stop` and
  `python run_experiment.py down` tear down all infra.
```
