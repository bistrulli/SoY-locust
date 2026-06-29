"""Standalone, infra-agnostic loadshapes (monoliths & Online Boutique).

Each shape is a standalone ``LoadTestShape``, loaded by Locust via
``-f <locustfile>,<shape>``. The amplitude is ``--users`` (standard option); the
timing comes from environment variables (``SHAPE_`` prefix) with defaults —
no custom CLI option required, unlike the old shapes in
``locust_file/loadshapes/``.
"""
