# Run plan — `monolith-v4`, uopt-focused campaign

Config file: **`experiments_v4_uopt.yaml`**. Goal: a clean, favourable comparison for the
**`uopt` (MPC) controller** on v4 — the stack with the *honest* load-balancer (Docker Swarm
ingress mesh on `:5001`, which really spreads traffic across `node` replicas, so scaling moves
throughput). Where uopt should win: **replica-seconds at equal QoS** + **anticipation** on
cyclical/peak.

> ⚠️ **Read the "Blockers" section at the bottom before launching.** `uopt` currently fails
> 100 % on v4 (ConnectionRefused) — this must be root-caused first, or the campaign wastes a night.

---

## 1. Load calibration (VU) — derived from brk / cap

Measured at **max_replicas = 8, spawn 200** (`results/results-brk/brk/monolith-v4__ramp__manual__u*`):

| users | rps | fail % | p95 (ms) | state |
|------:|----:|-------:|---------:|-------|
| 125 | 993 | 0.0 | 290 | OK |
| **150** | 1135 | 0.2 | 660 | **break** (`breaking_users=150`, ~824 rps) |
| **175** | 1317 | 0.1 | 700 | **knee / max throughput** (`knee_rps≈1366`) |
| **200** | 987 ↓ | 8.2 | 1000 | **rupture** (throughput collapses, `knee→0`) |

Reference points: **break = 150**, **rupture = 200** (both at 8 replicas).

### VU levels chosen (×1.5 / ×2 of break & rupture)
| multiplier | of break (150) | of rupture (200) |
|---|---:|---:|
| ×1.5 | **225** | **300** |
| ×2   | **300** | **400** |

→ deduped user levels: **{225, 300, 400}**.
- **PRIMARY = 300** (= 2×break = 1.5×rupture): at the shape's peak, 8 replicas are *just* saturated,
  so the controller that right-sizes fastest wins → best signal for uopt. **This is what the YAML is set to.**
- **225** (milder, 1.5×break): 8 replicas comfortably cover the peak → tests down-sizing / efficiency.
- **400** (overload, 2×rupture): even 8 replicas can't serve the peak → stress / robustness test.

> The `users:` value is the **peak** of each load shape (cyclical/step/peak ramp up to it).

---

## 2. Full parameter set (what the YAML encodes)

| Parameter | Value |
|---|---|
| Infra | `monolith-v4` (Docker **Swarm** stack, ingress mesh `:5001`, no reverse proxy) |
| Scaled service | `node` (single monolith) |
| Users (peak) | **300** (primary); sensitivity {225, 400} |
| spawn_rate | 50 /s |
| run_time | 600 s (peak shape ~130 s) |
| Load shapes | `cyclical`, `step`, `peak` (`bench/loadshapes/`) |
| Reps | **2** (bump to 3 for tighter CIs; costs +50 % time) |
| max_replicas | 8 (v4 ceiling; cap/brk measured at r8) |
| manual baseline | `fixed_replicas: 6` |
| none (frozen) | `initial_replicas: 4` |
| manual-sched | schedule `[[0,1],[120,3],[300,6],[480,3]]` |
| control_period | 5 s |
| Isolation | `up --renew-anon-volumes` then `down -v` (fresh DB/cache per run) |

### Controller grid (12 configs)
| Family | Configs |
|---|---|
| baselines | `none`, `manual` (6 repl), `manual-sched` |
| `hpa` (reactive) | `hpa-u25`, `hpa-u50`, `hpa-u75` |
| **`uopt` (expanded)** | `uopt-t25-min1`, `uopt-t25-min4`, `uopt-t50-min1`, `uopt-t50-min4`, `uopt-t70-min1`, `uopt-t70-min4` |

**uopt grid rationale**: `target_utilization ∈ {0.25, 0.50, 0.70}` × `min_replicas ∈ {1, 4}`.
Higher target → replicas run hotter → fewer of them (efficiency); `min_replicas=4` gives a warm
floor for bursts (peak). This brackets uopt's operating point to find where it is Pareto-best
(holds QoS at fewest replica-seconds) — vs the previous sweep which used `t10` (forces max-out,
no efficiency) and only 4 combos.

---

## 3. Run count & duration

**Primary (users=300):** 12 configs × 3 shapes × 2 reps = **72 runs** ≈ **14 h** (~12 min/run incl. up/down)
→ fits one overnight campaign (101 → 102).

- Sensitivity per extra level (225 or 400), full grid: +72 runs each (~14 h).
- All three levels, full grid: 216 runs (~43 h). **Recommend one user level per night**, primary first.
- reps 2 → 3: ×1.5 on all the above.

---

## 4. Launch (on host **101**, driving the app on **102**)

The runs execute on the Linux host **101** via `xp.sh` inside a `screen` session (NOT from the mac
mirror). On 101:

```bash
# primary campaign (users=300, full grid)
RUN_TAG=v4uopt ./xp.sh start matrix --file experiments_v4_uopt.yaml --infra monolith-v4

# monitor / attach / stop
RUN_TAG=v4uopt ./xp.sh status
RUN_TAG=v4uopt ./xp.sh follow      # tail -f results/v4uopt/console.log
RUN_TAG=v4uopt ./xp.sh watch       # attach to the live executor (screen)
RUN_TAG=v4uopt ./xp.sh stop        # stop + teardown

# sensitivity levels (later nights): edit users: 300 -> 225 (or 400) in the yaml, new RUN_TAG
RUN_TAG=v4uopt_u225 ./xp.sh start matrix --file experiments_v4_uopt.yaml --infra monolith-v4
```

`start` auto-resumes (skips runs already present in `results/v4uopt/`); use `--force` to redo all.

---

## 5. ⚠️ Blockers — resolve before / instead of launching

1. **`uopt` 100 % failure on v4 — ROOT CAUSE FOUND + FIX APPLIED** (systematic across all 18
   uopt/v4 cells; evidence in `results/results-run1/sweep/monolith-v4__uopt__*`).

   **Cause (a cold-start bug, not a uopt-algorithm bug):** `bench/runner.py::_initial_replicas`
   fell back to `infra.min_replicas` (=1) and **ignored `spec.min_replicas`**, so every uopt cell
   (even `uopt-min4`) deployed `node` at **1 replica**. Evidence — uopt scaling trace:
   `cpu_util_per_replica = 0.0` and `service_time = 0.0` for the **entire run** (throughput is just
   fast ConnectionRefused fails at ~12 ms), so the queueing law `S = ⌈λ·service_time / target⌉`
   yields 1 → uopt **never scales** → `node` stays at 1 → app never reachable → **100 % fail,
   CPU 0 %, 0 node containers** (vs 9 for a healthy hpa run). `none`/`manual` survive (deploy at
   4/6), `hpa` reads real util and scales fast.

   **Fix applied (two complementary, both safe):**
   - **Code** — `bench/runner.py::_initial_replicas` now honours an explicit `spec.min_replicas`
     floor for the initial deploy (`max(spec.min_replicas, infra.min_replicas)`).
   - **Config** — `experiments_v4_uopt.yaml` sets `initial_replicas: 4` on every `hpa`/`uopt`
     cell (warm start; uopt may then scale *down* to `min_replicas`, which is the down-sizing
     efficiency we want to measure).

   **⚠️ VALIDATION REQUIRED before the full campaign** (cannot be done from the mac — needs 101):
   run **one** uopt cell live and confirm the controller reads **`util > 0`** and `node` holds
   **≥ 4 replicas** and serves (0 % fail):
   ```bash
   RUN_TAG=v4uopt_probe ./xp.sh start matrix --file experiments_v4_uopt.yaml \
       --infra monolith-v4 --controller uopt --shape step
   RUN_TAG=v4uopt_probe ./xp.sh follow     # watch: util>0, node scaled to 4+, fail~0
   ```
   If util is still 0 at ≥4 replicas, the residual issue is the *signal* (how `node` CPU is read
   on Swarm) — then also check `bench/signals.py` / `estimator/monitoring.py`
   (`get_service_cpu_utilization` filters on the **Compose** label
   `container_label_com_docker_compose_service`, which Swarm containers do **not** carry — they use
   `container_label_com_docker_swarm_service_name="soy_v4_node"`). Only relevant if v4 is switched
   to `signal_kind="prometheus"`; with the current `docker_stats` signal the warm start should suffice.
2. **Runs execute on host 101, not this mac.** This checkout is the analysis *mirror*
   (`/Users/benoit/…`); the real runs ran on `/home/benoit/…` (Linux) against `DOCKER_HOST=…:102`.
   The launch command above must be run **on 101**.
3. **Sweep-dir state is changing.** `results/results/sweep/` lost its `monolith-v4__uopt__*` (and
   other) run dirs during this session, and a new `results/results-run1/` appeared — a campaign may
   be **archiving / re-running** right now. Confirm nothing is live (`./xp.sh status`) before
   launching a new `RUN_TAG` to avoid collision.

## 6. Live validation outcome (2026-07-03, on 101/102)

The fix was **synced to 101** and probed live (`v4probe`, `v4probe2`):
- ✅ **Fix works mechanically** — `Fixed replicas: node=4` at start (warm start); with `min4` uopt holds
  `node` at 4 (honours the floor).
- ❌ **Blocked by a host-102 infra problem, not uopt.** Swarm tasks for `node` (and
  `cadvisor`/`node-exporter`/`prometheus`) stay stuck in state **"New" — 0 running** (only `postgres`
  starts), so `:5001` is unreachable (`curl` refused) → **100 % ConnectionRefused at any replica count**.
  Reproduced on a **clean manual `docker stack deploy`** → persistent, not caused by rapid cycling.
  Disk (9 %), RAM (84 GB free), image (present), swarm node (Ready/Leader) are all fine → **wedged Swarm
  dispatcher on 102**. Likely the real cause of the archived uopt/v4 100 % failures too.

**Unblock → then validate:** restart the docker daemon on 102 (`ssh 192.168.3.102 'sudo systemctl restart
docker'`; 101→102 SSH works) — **shared node, get an OK first** — then:
```bash
RUN_TAG=v4probe3 ./xp.sh start matrix --file experiments_v4_probe.yaml --infra monolith-v4   # on 101
```
Expect: `node` holds ≥4, `util > 0`, `fail ~ 0`. Then run the full campaign (`experiments_v4_uopt.yaml`).
Keep uopt `min_replicas >= 2` on v4 (a single `node` replica may be unreachable via the ingress mesh).

## 7. Wedge SELF-HEAL now in place (2026-07-04)

The overnight `v4uopt` run (dumped to `results/results-v4/results/v4uopt/`) confirmed the swarm
dispatcher on 102 **re-wedged ~17:30 and never recovered → 43 consecutive 0-node / 100 %-fail runs,
all 36 uopt cells lost.** The harness now auto-recovers so a night runs unattended:

- `bench/runner.py::_ensure_service_scheduled` — after deploy+scale, if the scalable service has
  **0 running containers**, it restarts docker on the app host, re-deploys, re-fixes-up, re-scales
  (≤2 heals), and records `swarm_heal` in `result.json`. Backed by `bench/backends.py`
  (`restart_remote_docker`, `SwarmBackend.wait_running` / `.heal`). Disable with `SOY_SWARM_HEAL=0`.
- `tools/prune_failed_runs.py results/v4uopt --apply` — delete the dead 0-node dirs so the re-launch
  redoes only them (auto-resume skips existing `result.json`). Dry-run by default.
- `tools/swarm_watchdog.sh` — optional standalone safety net (run in a 2nd screen on 101).

**Re-run:** `./xp.sh sync` (from dev box) → on 101: `python3 tools/prune_failed_runs.py
results/v4uopt --apply` → `RUN_TAG=v4uopt ./xp.sh start matrix --file experiments_v4_uopt.yaml
--infra monolith-v4`. Optionally `screen -dmS soy-watchdog ./tools/swarm_watchdog.sh` alongside.

## 8. Two-level design (decided 2026-07-04): EFFICIENCY @300 + OVERLOAD @400

To test uopt/hpa optimally AND get failures on the static baselines, the campaign runs at TWO
user levels. Host 102 (lscpu) = **10 physical cores / 20 logical** (2 threads/core, 1 socket);
the ×2 headroom is on **physical** cores → **20**:

| level | file | max_replicas | regime | baselines | hpa / uopt |
|------:|------|:---:|--------|-----------|----------|
| **300** | `experiments_v4_uopt.yaml` | **8** | **efficiency / Pareto** | hold ~0 % fail (latency-degraded, p95 2–3 s) | 8 just saturated at peak → uopt wins on **replica-seconds at equal QoS** |
| **400** | `experiments_v4_uopt_u400.yaml` | **20** (autoscalers; 10 physical ×2) | **overload, room to scale** | **FAIL 8–15 %** — can't grow (ref `REF_fail_baselines`) | SAME ceiling 20 (fair) → both scale into the overload; winner = **fewer replica-seconds + anticipation**, not more headroom |

> Decision (2026-07-04): at 400 the two autoscalers share **max_replicas=20** (10 PHYSICAL cores ×2 —
> lscpu on 102 = 10 cores/socket × 1 socket, 2 threads/core = 20 logical; ×2 on physical = 20 = 2×
> physical oversubscription). Comparison stays honest — uopt must win on intelligence, not on ceiling.
> Static baselines keep fixed/frozen replicas (4/6) → they fail. 300 keeps max_replicas=8 (intrinsic
> to its "8 replicas just saturated" design — do NOT raise it there).

**Runbook (both levels, on 101 after `./xp.sh sync`):**
```bash
# LEVEL 300 — recover the lost uopt data (self-heal now protects it)
python3 tools/prune_failed_runs.py results/v4uopt --apply        # delete the 44 dead cells
RUN_TAG=v4uopt    ./xp.sh start matrix --file experiments_v4_uopt.yaml      --infra monolith-v4

# LEVEL 400 — overload: static baselines fail, controllers degrade gracefully
RUN_TAG=v4uopt400 ./xp.sh start matrix --file experiments_v4_uopt_u400.yaml --infra monolith-v4

# optional safety net, in a 2nd screen, for either level
screen -dmS soy-watchdog ./tools/swarm_watchdog.sh
```
Each level ≈ 72 runs ≈ 14 h (one night). The self-heal keeps them alive unattended.

---
*Generated 2026-07-03. Sources: `results/results-brk/brk` (break curve), `results/results-cap/capreg`
(capacity r8), `bench/infra.py` (topology). See `IMPROVEMENTS_per_stack.md` (Stack 1) for the wider v4 plan.*
