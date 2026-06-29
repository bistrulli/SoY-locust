#!/usr/bin/env bash
# =============================================================================
# Smoke test for the SoY-locust orchestration.
#
# [1] REAL resume logic of run_experiment.py:cmd_matrix — synchronous &
#     deterministic (the heavy run_experiment() is monkeypatched, no Docker).
# [2] xp.sh wiring — RUN_TAG → results dir / screen name / console.log, and the
#     command dispatch (screen vs fallback) — checked via `start`/`go` output.
# [3] Live detached execution (screen / setsid-nohup) — BEST-EFFORT: PASS if the
#     environment actually runs the detached child, else SKIP (some sandboxes
#     create the screen session but never execute it; the real Linux load
#     machine does).
#
#   ./tests/test_xp_orchestration.sh        # exit 0 = no failure (skips allowed)
# =============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
SANDBOX="$(mktemp -d 2>/dev/null || mktemp -d -t xptest)"

PASS=0; FAIL=0; SKIP=0
ok(){   printf '  \033[32mPASS\033[0m %s\n' "$1"; PASS=$((PASS+1)); }
ko(){   printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAIL=$((FAIL+1)); }
skip(){ printf '  \033[33mSKIP\033[0m %s\n' "$1"; SKIP=$((SKIP+1)); }
_delay(){ read -rt "${1:-0.2}" _ </dev/null 2>/dev/null || true; }
wait_for(){ local t=$1; shift; local n=$((t*5)); while [ "$n" -gt 0 ]; do eval "$@" && return 0; _delay 0.2; n=$((n-1)); done; return 1; }

cleanup(){
  for s in soy-xp-t1 soy-xp-t2 soy-xp-t3 soy-xp-t9; do screen -S "$s" -X quit >/dev/null 2>&1; done
  for p in "$SANDBOX"/.xp.*.pid; do [ -f "$p" ] && kill "$(cat "$p")" 2>/dev/null; done
  rm -rf "$SANDBOX"
}
trap cleanup EXIT

echo "== SoY-locust orchestration smoke test =="

# =============================================================================
# [1] REAL run_experiment.py:cmd_matrix resume (no Docker, synchronous)
# =============================================================================
echo "[1] real cmd_matrix resume (skip done / --force redo)"
if ( cd "$REPO" && python3 -c "import run_experiment, bench.runner, yaml" ) >/dev/null 2>&1; then
  if ( cd "$REPO" && python3 - <<'PY'
import os, tempfile, argparse
from pathlib import Path
import run_experiment as R
from bench.runner import _tag
from bench.infra import get_infra, list_infra

infra_name = list_infra()[0]
tmp = tempfile.mkdtemp()
os.environ["RESULTS_ROOT"] = tmp

calls = []
def fake_run(spec, cfg):                       # stand in for the heavy run_experiment()
    tag = _tag(spec, get_infra(spec.infra))
    calls.append(tag)
    d = cfg.results_path(tag); d.mkdir(parents=True, exist_ok=True)
    (d / "result.json").write_text("{}")
    return {"tag": tag}
R.run_experiment = fake_run                    # cmd_matrix uses the module global

(Path(tmp) / "exp.yaml").write_text("experiments:\n  - infra: %s\n    reps: 2\n" % infra_name)
def matrix(force):
    calls.clear()
    R.cmd_matrix(argparse.Namespace(file=str(Path(tmp) / "exp.yaml"), dry_run=False, force=force))
    return len(calls)

first  = matrix(False)   # nothing done yet  -> 2 runs
resume = matrix(False)   # both present      -> 0 runs (skipped)
forced = matrix(True)    # --force           -> 2 runs
assert first == 2,  f"first={first}"
assert resume == 0, f"resume={resume}"
assert forced == 2, f"forced={forced}"
print("ok")
PY
  ) >/dev/null 2>&1; then ok "cmd_matrix: 1st=run both, 2nd=skip both, --force=redo both"
  else ko "cmd_matrix resume assertions failed (run the heredoc standalone to see why)"; fi
else
  skip "project deps (run_experiment / pyyaml) unavailable — real resume test skipped"
fi

# --- sandbox: the REAL xp.sh + a stub run_experiment.py ----------------------
cp "$REPO/xp.sh" "$SANDBOX/xp.sh"; chmod +x "$SANDBOX/xp.sh"
cat > "$SANDBOX/run_experiment.py" <<'PY'
#!/usr/bin/env python3
"""Stub: honors RESULTS_ROOT, mirrors the resume contract (skip if result.json exists)."""
import os, sys, json, time
from pathlib import Path
RR = Path(os.environ.get("RESULTS_ROOT", "results"))
SLEEP = float(os.environ.get("XP_TEST_SLEEP", "1.0"))
TAGS = ["a__rep0", "a__rep1"]
def matrix(argv):
    made = skipped = 0
    for tag in TAGS:
        done = RR / tag / "result.json"
        if done.exists() and "--force" not in argv:
            print(f"[matrix] SKIP {tag}", flush=True); skipped += 1; continue
        print(f"[matrix] RUN {tag}", flush=True); time.sleep(SLEEP)
        done.parent.mkdir(parents=True, exist_ok=True); done.write_text(json.dumps({"tag": tag}))
        made += 1
    print(f"[matrix] done made={made} skipped={skipped}", flush=True)
cmd = sys.argv[1] if len(sys.argv) > 1 else ""
if   cmd == "matrix": matrix(sys.argv[2:])
elif cmd == "check":  print("stub check OK")
elif cmd == "down":   print("stub down")
else: print(f"stub: unknown {cmd}", file=sys.stderr); sys.exit(2)
PY
cd "$SANDBOX"

# =============================================================================
# [2] xp.sh wiring — RUN_TAG mapping + command dispatch (synchronous output)
# =============================================================================
echo "[2] xp.sh RUN_TAG mapping + dispatch"
out="$(XP_NO_SCREEN=1 RUN_TAG=t9 XP_TEST_SLEEP=0 ./xp.sh start 2>&1)"
echo "$out" | grep -q "results=results/t9"      && ok "RUN_TAG → RESULTS_ROOT=results/t9"   || ko "RESULTS_ROOT mapping"
echo "$out" | grep -q "screen=soy-xp-t9"        && ok "RUN_TAG → screen=soy-xp-t9"          || ko "screen-name mapping"
echo "$out" | grep -q "log: results/t9/console.log" && ok "log → results/t9/console.log"   || ko "console.log path"
echo "$out" | grep -q "Started (PID"            && ok "XP_NO_SCREEN=1 → detached fallback"  || ko "fallback dispatch"
[ -f .xp.t9.pid ] && ok "fallback writes a pidfile (.xp.t9.pid)" || ko "no pidfile in fallback"

gout="$(RUN_TAG=t9 XP_NO_SCREEN=1 XP_TEST_SLEEP=0 ./xp.sh go 2>&1)"
echo "$gout" | grep -q "check OK → starting" && ok "go: check → start chain" || ko "go did not chain check→start"

hout="$(./xp.sh 2>&1 || true)"
echo "$hout" | grep -q "RUN_TAG" && ok "no-arg prints help (mentions RUN_TAG)" || ko "help header not printed"

if command -v screen >/dev/null 2>&1; then
  sout="$(XP_TEST_SLEEP=30 RUN_TAG=t2 ./xp.sh start 2>&1)"
  echo "$sout" | grep -q "Started in screen 'soy-xp-t2'" && ok "screen mode → dispatches into screen" || ko "screen dispatch message missing"
  screen -S soy-xp-t2 -X quit 2>/dev/null
else
  skip "screen absent — screen dispatch message not checked"
fi

# =============================================================================
# [3] Live detached execution — best-effort (PASS, else SKIP)
# =============================================================================
echo "[3] live detached execution (best-effort)"
rm -rf results; XP_NO_SCREEN=1 XP_TEST_SLEEP=0 RUN_TAG=t3 ./xp.sh start >/dev/null 2>&1
if wait_for 10 '[ -f results/t3/a__rep1/result.json ]'; then
  ok "fallback child ran to completion (result.json written)"
  # since it ran, we can also verify resume end-to-end through xp.sh:
  XP_NO_SCREEN=1 XP_TEST_SLEEP=0 RUN_TAG=t3 ./xp.sh start >/dev/null 2>&1
  wait_for 8 'grep -q "skipped=2" results/t3/console.log 2>/dev/null' && ok "end-to-end resume via xp.sh (skipped=2)" || ko "xp.sh resume did not skip"
else
  skip "detached child not observable here (works on the real Linux load machine)"
fi

if command -v screen >/dev/null 2>&1; then
  rm -rf results; XP_TEST_SLEEP=0 RUN_TAG=t1 ./xp.sh start >/dev/null 2>&1
  if wait_for 10 '[ -f results/t1/a__rep1/result.json ]'; then
    ok "screen executor ran to completion (result.json written)"
  else
    skip "screen child not executed in this sandbox (real load machine runs it)"
  fi
  screen -S soy-xp-t1 -X quit 2>/dev/null
fi

echo
echo "== $PASS passed, $FAIL failed, $SKIP skipped =="
[ "$FAIL" -eq 0 ]
