"""Harness locustfiles, with **normalized throughput**.

All set ``wait_time = constant_throughput(BENCH_RPS_PER_USER)``: each
user triggers its scenario at a FIXED rate (iterations/second), regardless of
the app's response time. As a result: the total **offered throughput**
= ``users × BENCH_RPS_PER_USER`` is **identical across all infra** (monoliths
and Online Boutique), which makes the energy/perf comparison fair.

With ``BENCH_RPS_PER_USER=1.0`` (default), ``--users N`` ⇒ N offered iterations/s.
"""
