# Per-stack improvement plan

> Cross-cutting goal: **make `uopt` come out as the most suitable controller** — honestly
> (no p-hacking; we set up the conditions where its real strength shows).
> Basis: sweep `results/results/sweep/` (2026-07-01 → 2026-07-03), **175 runs** (v4:61, v5:60, shop:54),
> 2 reps/cell. Report: `results/results/REPORT_sweep_v4_v5.pdf`.

## Priority legend
- 🔴 **Blocking** — result is invalid until fixed
- 🟠 **Methodology** — biases the comparison (often against `uopt`)
- 🟢 **Re-run** — re-execute once the fix is in place
- 🟡 **Nice-to-have** — completeness / cleanliness

## Where `uopt` wins *honestly* (what to highlight)
1. **Pareto efficiency**: same QoS as the best HPA at **fewer replica-seconds**.
2. **Anticipation (MPC)**: pre-scales ahead of the load on `cyclical`/`peak` (structural edge over reactive HPA).
   → On `peak`, `uopt-t25-min4` (warm floor) already absorbs the burst best.
- ❌ Do NOT claim "best p95 on *step*" — that is **confounded** by a run-level bistability (see shop).

---

## Stack 1 — `monolith-v4`  (Docker **Swarm**, ingress mesh `:5001`)

### Verified setup (`bench/infra.py`, `sou/monotloth-v4.yml`)
- `backend_kind = "swarm"` → traffic on `:5001` is **load-balanced by the Swarm ingress routing mesh**
  (NOT Traefik, NO separate reverse proxy).
- Scaled service: `node` (single monolith). DB: `postgres`. Load: 200 users, spawn 50/s.
- ✅ This is the **most honest LB** of the three stacks (the mesh genuinely spreads traffic across replicas
  → scaling really moves throughput).

### Problems (evidence)
- 🔴 **`uopt` = 100 % failures on v4** (verified step rep0, all 3 labels):
  ```
  uopt-t10-min1  fail=100.0%  rps=340  p95=26ms  cpu=0%   ← ConnectionRefused(111) on /api/user/login
  uopt-t25-min4  fail=100.0%  rps=340  cpu=0%
  uopt-t50-min1  fail=100.0%  rps=340  cpu=0%
  ```
  The other controllers are fine (`none` 355 / `manual` 690 / `hpa-u25` 852 rps, 0 % fail). So the app is healthy:
  this is **uopt-specific** (the app is never reached, node CPU at 0 %).
- 🟠 Load sits at the knee: `knee_users≈200`, `knee_rps≈630` — 200 users inflates p95 but does not break hard.

### Actions
- [ ] 🔴 **Root-cause the uopt/v4 crash** — inspect `monolith-v4__uopt__default__step__*/`
  (`locust.log`, `locust_exceptions.csv`, root `console.log`): why does only uopt break `:5001` reachability?
  Hypotheses: the uopt actuator issues a `docker service scale`/`update` that drops the ingress port publication;
  or the uopt estimator (QNEstimator) needs proxy-level metrics v4 doesn't expose and errors out;
  or min/initial replicas resolve to a value that leaves the service unpublished.
- [ ] 🟢 **Re-run uopt/v4** once fixed (v4 is the ideal uopt showcase — honest LB).
- [ ] 🟠 Raise the load (200 → ~400 users) to spread the controllers apart.
- [ ] 🟡 Update report caveat §2.1 when resolved.

### uopt benefit
> **The #1 lever**: uopt is currently **absent** from an entire stack. Unblocking it on the cleanest LB is
> the best chance to show it scaling correctly.

---

## Stack 2 — `monolith-v5`  (Docker Compose, **nginx-vts** `:80`)

### Verified setup
- `backend_kind = "compose"`, entry `:80` (`gateway-nginx`). Scaled service: `ms-exercise`
  (fronted by `ms-exercise-nginx`). Load: 200 users.

### Problems (evidence)
- 🔴 **Degenerate LB** (verified manual step rep0) — nginx pins all traffic to **one** replica:
  ```
  ms-exercise-1  216.6% CPU        ms-exercise-2..6  ~0.0% CPU
  ```
  Cause: `upstream { server ms-exercise:5001; }` with no `resolver` → nginx resolves the name **once** at
  start-up and pins traffic. Same DNS-staleness class as the Envoy fix in commit `11fc8f8`, **not yet ported**
  to the v5 nginx config.
- Consequences: (i) throughput capped by 1 replica (~420 rps) regardless of replica count;
  (ii) autoscalers **scale down** (mean util ~0.36 looks falsely low);
  (iii) the "−40..−80 % replica-seconds" savings are **fake** (removing already-idle replicas).

### Actions
- [ ] 🔴 **Fix v5 nginx**: add `resolver` + variable `proxy_pass` (or `tasks.ms-exercise`, or port the
  Envoy path of `11fc8f8`) so traffic spreads across all replicas.
- [ ] 🟢 **Re-run all v5** after the fix (current numbers are non-representative).
- [ ] 🟠 Raise the load after the fix (the ~420 rps cap disappears → real stress).
- [ ] 🟡 Update report caveat §2.2 when resolved.

### uopt benefit
> While nginx pins to 1 replica, uopt's "savings" are an **artefact** (idle replicas removed). After the fix,
> uopt can show **genuine right-sizing**.

---

## Stack 3 — `shop` / microservices-demo  (Docker Compose, **Envoy** gRPC `:8080`)

### Verified setup
- `backend_kind = "compose"`, entry `:8080`. Scaled service: `recommendationservice` (top-CPU). Other backends
  pinned via `extra_replicas`. Load: **6000 users, spawn 500/s**. Variant: **Envoy** (the working LB, DNS fix
  `11fc8f8`).
- ✅ Only stack where the LB genuinely spreads load → **best uopt showcase**.

### Problems (evidence)
- 🟠 **Run-level bistability under *step*** (see `results/results/fig_shop_step_p95_trace.png`): at 6000 sustained
  users a run either **holds p95≈33 ms / 1310 rps** or **collapses to ~3.6–4.8 s / ~1150 rps** for the rest of the
  plateau, **at constant replica count**. Median plateau p95 per rep:
  ```
                 rep0        rep1
  hpa-u25        33ms/0%     34ms/0%     ← both healthy (luck)
  uopt-t10-min1  4800ms/100% 33ms/0%     ← one healthy, one collapsed
  uopt-t25-min4  3950ms/100% 33ms/0%
  uopt-t50-min1  4200ms/72%  3800ms/80%
  hpa-u75        32ms/0%     3700ms/87%  ← also collapses
  ```
  → **not** a controller property; hpa-u25 "wins" only because its reps happened to stay healthy.
- 🟠 **Collapse locus ≠ recommendationservice**: per-service CPU is near-identical healthy vs collapsed;
  recommendationservice stays at ~0.30 util at 8 replicas. Prime suspect: **`frontend` on 1 replica at ~240 % CPU**
  (un-scaled funnel for 6000 users) → self-sustaining latency avalanche (connection pool / goroutines).
- 🟠 **uopt over-provisions**: climbs to **8 replicas (max) at 0.30 util** while target `t50=0.50` → it does **not**
  show its efficiency edge.
- 🟡 **shop `nginx` variant never run** — the Envoy-vs-nginx comparison (the block's raison d'être) is incomplete.
- 🟡 **RAPL bimodal** (~2× on a subset at equal CPU) → shop RAPL energy unreliable; wattmeter is fine.

### Actions
- [ ] 🟠 **Scale the `frontend`** (≥2–3 replicas) + check the singleton Envoy sidecars (pool/keepalive)
  → kill the bistability.
- [ ] 🟠 **Instrument** the other backends + Envoy during the 6000-user plateau (confirm the real bottleneck).
- [ ] 🟠 **5+ reps + medians** (2 reps too few) → removes the lottery that penalizes uopt.
- [ ] 🟠 **Investigate uopt over-provisioning**: why 8 replicas at 0.30 util? (model's RT/cost term)
  → tune it to hold SLA at **fewer** replicas.
- [ ] 🟡 Run the **shop `nginx` variant** (complete the LB comparison).
- [ ] 🟡 **Fix RAPL**: pin scaphandre to a single socket / verify `node01`'s RAPL topology.

### uopt benefit
> After frontend fix + reps: comparable, stable QoS → finally compare on **replica-seconds at equal QoS**
> (where uopt should win) + **anticipation** on cyclical/peak.

---

## Cross-cutting (all three stacks)
- [ ] 🟠 Move from **2 → 5+ reps** everywhere and report **medians** (not means) — 2-rep means are fragile.
- [ ] 🟡 **Energy narrative**: add a multi-host / consolidation scenario so saved replica-seconds map to real
  Watts (today energy is dominated by the always-on host baseline).
- [ ] 🟡 Headline metrics: **replica-seconds** + **energy from both probes** (RAPL + wattmeter) — they separate
  "allocation saved" from "energy saved".

## Suggested order of work
1. **v4 🔴** unblock the uopt crash (biggest lever: uopt absent from a whole stack) → re-run uopt/v4.
2. **v5 🔴** fix the nginx DNS staleness → re-run v5.
3. **shop 🟠** frontend + reps + uopt tuning → expose efficiency + anticipation.
4. **Cross-cutting**: reps=5, medians, RAPL, shop nginx variant.

---
*Generated 2026-07-03. Evidence: `bench/aggregate.py` aggregation + `scaling/` & `locust_stats_history.csv` traces.
See figure `results/results/fig_shop_step_p95_trace.png` and report `REPORT_sweep_v4_v5.pdf`.*
