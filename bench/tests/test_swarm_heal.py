"""Unit tests for the Swarm-wedge self-heal loop (bench/runner._ensure_service_scheduled).

No Docker/infra: a fake backend simulates the count of running containers returned by
successive `wait_running` calls, so we exercise the detect→heal→re-scale→re-check logic
deterministically.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from bench.config import CFG
from bench.runner import _ensure_service_scheduled


@dataclass
class _FakeInfra:
    scalable_service: str = "node"
    db_fixups: list = field(default_factory=list)


class _FakeSwarm:
    """Backend stub: `wait_running` pops the next count from a scripted sequence."""

    def __init__(self, running_sequence: List[int], heal_ok: bool = True):
        self._seq = list(running_sequence)
        self._heal_ok = heal_ok
        self.heals = 0
        self.scaled: list = []

    def wait_running(self, service, min_count=1, timeout_s=0.0, interval_s=0.0) -> int:
        return self._seq.pop(0) if self._seq else 0

    def heal(self) -> bool:
        self.heals += 1
        return self._heal_ok

    def scale_many(self, scales) -> None:
        self.scaled.append(dict(scales))


def test_healthy_run_never_heals():
    b = _FakeSwarm([4])          # 4 running from the start, want=4
    ev = _ensure_service_scheduled(_FakeInfra(), b, {"node": 4}, CFG)
    assert b.heals == 0
    assert ev["healed"] is False   # no heal needed
    assert ev["ok"] is True
    assert ev["running_after"] == 4
    assert ev["want"] == 4


def test_wedge_recovers_after_one_restart():
    # 0 running (wedged) → heal → FULL 4 running (recovered)
    b = _FakeSwarm([0, 4])
    ev = _ensure_service_scheduled(_FakeInfra(), b, {"node": 4}, CFG)
    assert b.heals == 1
    assert ev["healed"] is True
    assert ev["ok"] is True
    assert ev["heals"] == 1
    assert ev["running_after"] == 4
    assert b.scaled == [{"node": 4}]   # re-scaled after the heal


def test_partial_heal_is_not_accepted():
    # Regression test for the v4uopt400 incident (2026-07-05): a heal that only
    # restores PART of the desired replicas (e.g. 2 of 6) must NOT be declared
    # "healed" — it used to accept `running >= 1` and start the load against an
    # under-provisioned deploy, inflating the failure rate (manual/step: healed at
    # 2/6 replicas → 49.3% fail; uopt-t50-min4/peak: healed at 2/4 → 46.0% fail).
    b = _FakeSwarm([0, 2], heal_ok=True)   # heals, but only reaches 2 of the 4 wanted
    ev = _ensure_service_scheduled(_FakeInfra(), b, {"node": 4}, CFG, max_heals=1)
    assert b.heals == 1
    assert ev["healed"] is False    # partial recovery must NOT count as healed
    assert ev["ok"] is False
    assert ev["running_after"] == 2
    assert ev["want"] == 4


def test_wedge_recovers_on_second_restart_after_partial_first():
    # 0 → heal → partial (2/4, not enough, keep trying) → heal → 4 (full, healed)
    b = _FakeSwarm([0, 2, 4])
    ev = _ensure_service_scheduled(_FakeInfra(), b, {"node": 4}, CFG, max_heals=2)
    assert b.heals == 2
    assert ev["healed"] is True
    assert ev["ok"] is True
    assert ev["heals"] == 2
    assert ev["running_after"] == 4


def test_persistent_wedge_gives_up_after_max_heals():
    b = _FakeSwarm([0, 0, 0])    # never recovers
    ev = _ensure_service_scheduled(_FakeInfra(), b, {"node": 4}, CFG, max_heals=2)
    assert b.heals == 2
    assert ev["healed"] is False
    assert ev["ok"] is False
    assert ev["running_after"] == 0


def test_disabled_heal_env(monkeypatch):
    monkeypatch.setenv("SOY_SWARM_HEAL", "0")
    b = _FakeSwarm([0])          # wedged, but healing disabled
    ev = _ensure_service_scheduled(_FakeInfra(), b, {"node": 4}, CFG)
    assert b.heals == 0
    assert ev["healed"] is False
    assert ev["ok"] is False
