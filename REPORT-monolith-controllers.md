# Controller comparison on the monolith — performance & energy report

**Scope.** Which scaling controller is the most performant on the monolithic
application (`monolith-v4`): **HPA**, **uOPT** (the optimization model), or the
**hand-tuned / manual** policy. Metrics follow the ICWS 2024 *SoY load-tests* paper
(availability, performance, resource & energy usage).

**Data.** Campaign `run3`, infra `monolith-v4`, 4 controllers × 3 repetitions
(12 complete runs). Loadshape `cyclical` (5 × 120 s = 600 s), peak 200 virtual users.
Scenario **R** = the 10-request login→verify→exercise→logout sequence (same as the paper).

> The plain `manual` (fixed replicas) controller is not present in `run3`; the
> **`none`** controller (frozen replicas) is its static equivalent and is reported as
> the static baseline alongside **`manual-sched`** (scheduled hand-tuned staircase).
> `monolith-v5` is still being measured (`run5`, in progress) — see §6.

---

## 1. Results (mean over 3 repetitions)

| Controller | Replicas mean/max | **FR** (%) | **Throughput** ST (ok/s) | RT avg (ms) | **p95** (ms) | <800 ms (%) | **Apdex** | CPU avg (%) | Mem (MiB) | **Energy** (W·h) | Avg power (W) | **J / ok-req** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **none** (static) | fixed | **12.4** | **500** | 208 | **423** | 100 | **1.00** | 57 | 238 | 26.6 | 158 | **0.316** |
| **manual-sched** | 3.1 / 6 | **12.4** | **498** | 209 | **427** | 100 | **1.00** | 70 | 380 | 26.7 | 159 | **0.319** |
| **hpa** | 3.7 / 5 | 17.8 | 405 | 252 | 653 | 94.4 | 0.97 | 73 | 568 | 26.6 | 158 | 0.391 |
| **uopt** | 1.4 / 3 | 23.5 | 306 | 303 | 1000 | 86.5 | 0.93 | 49 | 595 | 26.0 | 155 | 0.505 |

Metric definitions (ICWS): **FR** = failures / total requests; **ST** (System Throughput)
= successful requests / s; **<800 ms** = share of successful requests answered under
800 ms; **Apdex** (T = 800 ms) over successful requests; **Energy** = wall-plug energy
over the 600 s run (Tasmota), **J/ok-req** = wall energy per successful request.

---

## 2. Availability — Failure Rate (FR)

The monolith saturates well below the 200-VU peak (the capacity probe breaks at
~46 VUs / ~90 req/s), so every controller drops requests. The question is *how many*:

- **Static (none / manual-sched): 12.4 %** — the lowest, and rock-stable across reps.
- **hpa: 17.8 %** — worse, and inconsistent (per-rep 12.4 % → 25.6 %): reactive scale-up
  lags the fast cyclical ramps, so requests are dropped during each climb.
- **uopt: 23.5 %** — the worst: the optimizer **under-provisions** (mean 1.4, max 3
  replicas) and cannot absorb the peaks.

**Availability ranking: manual ≈ none > hpa > uopt.**

## 3. Performance — throughput, latency, Apdex

- **Throughput (ST):** static **500 ok/s** ≫ hpa 405 ≫ uopt 306. Serving more successful
  requests is a direct consequence of the lower failure rate.
- **Latency:** static keeps p95 ≈ **425 ms** with **100 %** of answers < 800 ms
  (Apdex 1.00). hpa degrades to p95 653 ms (94 % < 800 ms), uopt collapses to
  p95 1000 ms (only 86 % < 800 ms, Apdex 0.93).
- The story is consistent: **enough replicas, held steady, win**; reactive (hpa) and
  optimizer-driven (uopt) scaling both pay a penalty under this fast-oscillating load.

**Performance ranking: manual ≈ none > hpa > uopt.**

## 4. Resource & energy usage

- **Wall energy is essentially flat: ~26–27 W·h (~155–159 W average) for every
  controller.** The machine's baseline power dominates, so the *total* energy bill barely
  depends on the controller. (RAPL was not captured in this campaign — `rapl: {}` — so
  only the physical wall meter is used, which the paper also considers more reliable.)
- Because energy is ~constant but throughput is not, the meaningful efficiency metric is
  **energy per successful request**: static **0.32 J/req** < hpa 0.39 < **uopt 0.51 J/req**.
  uOPT spends ~**60 % more energy per served request** than the static policy — it pays
  the same wall power but serves far fewer requests.
- CPU/memory: uopt runs the fewest replicas (lowest CPU 49 %) yet is the least useful;
  hpa and manual-sched use more replicas/CPU and memory for better service.

**Efficiency (J per served request) ranking: manual ≈ none > hpa > uopt.**

---

## 5. Verdict

On `monolith-v4`, under the cyclical 200-VU load, **the hand-tuned / static policy is the
most performant AND the most energy-efficient per request**, by every ICWS metric:

| Rank | Controller | Why |
|---|---|---|
| 🥇 | **manual (manual-sched ≈ none)** | lowest FR (12.4 %), highest throughput (≈500 ok/s), p95 ≈ 425 ms, Apdex 1.00, 0.32 J/req |
| 🥈 | **hpa** | reactive scaling lags the ramps → FR 17.8 %, p95 653 ms, 0.39 J/req |
| 🥉 | **uopt** | under-provisions (1.4 repl) → FR 23.5 %, p95 1000 ms, 0.51 J/req |

**Why the optimizer loses here.** The monolith breaks at ~46 VUs; the cyclical load swings
to 200 VUs every 120 s. A controller must keep replicas high *ahead* of each ramp. The
hand-tuned schedule does exactly that; HPA reacts a step late; uOPT optimizes toward a
lower replica count that minimizes cost but cannot serve the peaks. For a workload this
spiky on a bottlenecked monolith, **proactive static over-provisioning beats reactive and
optimal-cost control.**

---

## 6. Caveats & next steps

- **RAPL missing** in `run3` (`rapl: {}`); energy is wall-plug only. The current `run5`
  campaign records RAPL too (verdict ✅ at launch) — re-run this report on `run5` for the
  RAPL/package breakdown.
- **monolith-v5** is being measured now (`run5`): so far `none` and `manual` are done
  (0 % failures, ST ≈ 368 ok/s, p95 ≈ 2050 ms, ~31.7 W·h); `manual-sched`, `uopt`, `hpa`
  are pending. v5 (split services behind the gateway) does **not** saturate like v4 —
  0 % failures so far — so its controller ranking may differ and will hinge on
  energy/replica efficiency rather than failure rate.
- Tighter HPA/uOPT tuning (shorter control period, higher target headroom, predictive
  schedule) could close the gap with the hand-tuned policy — a natural follow-up experiment.
