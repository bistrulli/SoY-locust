# Method — launch & resume a run with `screen` (SoY-locust)

A full run (matrix: infra × controllers × variants × loadshapes × repetitions from
`experiments.yaml`) takes several hours. The harness relies on **`screen`** to make
execution **detachable** (survives closing the terminal / SSH drop) and on
**auto-resume** (a present `result.json` means the run is skipped) to make the work
**resumable** without re-measuring or duplicating.

These are **two complementary notions**:

| "Resume" in the sense of… | Mechanism | How |
|---|---|---|
| resume the **session** (the detached window) | `screen` | `./xp.sh watch` / `screen -r soy-xp-<RUN_TAG>` |
| resume the **work** after a crash/stop | auto-resume (default) | relaunch `start`/`go` with the **same `RUN_TAG`** |

> ⚠️ Here **the run lives INSIDE the screen** (the screen *is* the executor). Detach
> without stopping it: **`Ctrl-A` then `D`**. `Ctrl-C` / `exit` / closing the screen
> **stops** the run. The full log is mirrored (`tee`) to `results/<RUN_TAG>/console.log`
> anyway, so `follow`/`status` work even if the screen dies.

---

## 1. Detachable launch — `start` (and `go`)

```bash
RUN_TAG=run1 ./xp.sh go                  # all-in-one: check → start  (recommended)
RUN_TAG=run1 ./xp.sh start               # the whole matrix (experiments.yaml)
RUN_TAG=run1 ./xp.sh start run --infra microservices-demo --controller hpa --variant go
RUN_TAG=run1 ./xp.sh start --force       # re-measure EVERYTHING (ignore already-done)
```

- `start [args]` runs `run_experiment.py` **inside a detached `screen` session**: the
  run keeps going even if the terminal is closed.
- `go` is the all-in-one: `check` (energy/CPU/mem preflight) **→** `start`. If `check`
  fails, `go` aborts (you can bypass via `start`).

Under the hood (`xp.sh:start`):

```bash
screen -dmS "$SCREEN_NAME" bash -c \
  '<PY> run_experiment.py <ARGS>  2>&1 | tee results/<RUN_TAG>/console.log'
```

- **`-dmS`**: create the session **d**etached (`-d -m`) and **n**ame it (`-S`).
- Session name: **`soy-xp-<RUN_TAG>`** (or `soy-xp` without RUN_TAG).
  Overridable: `SOY_SCREEN=... ./xp.sh start`.
- All output is **duplicated by `tee`** into `results/<RUN_TAG>/console.log`: following
  the run does not depend on being attached.
- **Fallback without `screen`**: if the `screen` binary is missing, `start` falls back
  to a **detached `setsid`** process (non-interactive, followed via `console.log`).

---

## 2. Follow, attach, detach

```bash
RUN_TAG=run1 ./xp.sh status    # screen -ls + last run + nb of results + tail of the log
RUN_TAG=run1 ./xp.sh watch     # join the session  (= screen -r soy-xp-run1)
RUN_TAG=run1 ./xp.sh follow    # tail -f results/run1/console.log  (read-only)
```

- `status`: tells whether the `soy-xp-<RUN_TAG>` session is alive, the current run and
  the number of produced `result.json` — a quick glance without attaching.
- `watch`: joins the **live executor**. **Detach without killing the run:
  `Ctrl-A` then `D`**.
- `follow`: tails the log **read-only** (never touches the run); `Ctrl-C` only quits
  the viewer.
- Raw `screen` equivalents:
  ```bash
  screen -ls                              # list sessions
  screen -r soy-xp-run1                    # reattach the executor
  tail -f results/run1/console.log         # follow the log without attaching
  ```

---

## 3. Resuming the work — auto-resume (on by default)

Resume is the **default behaviour** (`run_experiment.py:cmd_matrix`). Concretely:

> Relaunching `start`/`go` with the **same `RUN_TAG`** resumes where it stopped, by
> **skipping the runs already measured** in `results/<RUN_TAG>/`, without re-running.

- **Granularity = one matrix run**: the key is the experiment *tag*
  `<infra>__<controller>__<variant>__<shape>__rep<N>`. A run whose
  `results/<RUN_TAG>/<tag>/result.json` exists is skipped; the others run.
  > Unlike bench-v2, resume is **not** sub-run (not "per request / per step"): an
  > interrupted run **restarts from scratch** — but cleanly, see below.
- **`RUN_TAG` is the idempotency key**: it is the name of the results directory
  (`results/<RUN_TAG>/`, via `RESULTS_ROOT`) that decides what is already done. Keep
  the **same tag** to resume; change it to start a fresh campaign.
- **Clean resume by construction**: `result.json` is written only **at the very end**
  of a run (`runner.py`). A run that crashes mid-way therefore leaves **no**
  `result.json` ⇒ it is not skipped ⇒ it is re-measured in full. No half-measurement
  taken at face value.
- **Force a full re-run**: `./xp.sh start --force` (re-measure everything, overwrite).

### Typical scenario "the run crashed / the machine rebooted"

```bash
RUN_TAG=run1 ./xp.sh status     # see where it stopped (how many result.json)
RUN_TAG=run1 ./xp.sh start      # relaunch: already-done runs are skipped
RUN_TAG=run1 ./xp.sh watch      # check it resumes at the right place
```

---

## 4. Full life cycle (summary)

```
go ─┬─ check ─┐
    │         ▼
    └────  start  ──►  screen -dmS soy-xp-<RUN_TAG>  ──►  run_experiment.py (detached)
                                  │                          │ tee
            watch / status ◄──────┘                          ▼
            (Ctrl-A D to detach)         results/<RUN_TAG>/console.log
                                                          +  <tag>/result.json (per run)

   crash / stop  ──►  start (same RUN_TAG)  ──►  skips present result.json  ──►  resume
```

---

## 5. Things to watch

1. **One campaign = one `RUN_TAG`**. It names **both** the `results/<RUN_TAG>/`
   directory **and** the `soy-xp-<RUN_TAG>` session, so two campaigns with distinct
   `RUN_TAG` run **in parallel** without colliding.
2. **`console.log` is overwritten** on every `start` (`tee` without `-a`): after a
   resume, the log only contains the current session. The measurement history is
   preserved in `results/<RUN_TAG>/<tag>/` (it is what drives resume).
3. **`status`/`watch`/`follow` need the `RUN_TAG`** to find the right session and the
   right `console.log` — prefix it as for `start`.
4. **The run lives in the screen**: `Ctrl-A D` to detach, never `Ctrl-C` (which stops
   the run). Without `screen`, detached `setsid` fallback.
5. **Edit on the dev box, run on the load machine**: after every change, push the
   source with `./xp.sh sync` (from the dev box) before relaunching on `192.168.3.101`,
   otherwise the old code runs (the remote `results/` are excluded from the sync).

---

### Code reference

| Item | Location |
|---|---|
| `start` (screen `-dmS` + `tee`), `setsid` fallback | `xp.sh` → case `start` |
| `go` (check → start) | `xp.sh` → case `go` |
| `watch` (`screen -r`) / `status` (`screen -ls` + tail) / `follow` | `xp.sh` → cases `watch`,`status`,`follow` |
| `stop` (`screen -X quit` + teardown) | `xp.sh` → case `stop` |
| `RUN_TAG` → `RESULTS_ROOT` + `SCREEN_NAME` + `console.log` | `xp.sh` (top of the script) |
| Resume (skip present `result.json`), `--force` | `run_experiment.py` → `cmd_matrix` |
| Experiment tag (per-run idempotency key) | `bench/runner.py` → `_tag()` |
| `RESULTS_ROOT` / `results_path()` | `bench/config.py` |
| Energy/CPU/mem preflight (`check`) | `bench/metrics.py` → `energy_probe()` + `run_experiment.py` → `_format_check()` |
| Orchestration smoke test | `tests/test_xp_orchestration.sh` (real resume + RUN_TAG mapping + dispatch) |
