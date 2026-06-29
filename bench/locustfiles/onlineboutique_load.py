"""Online Boutique with **normalized throughput**.

Wraps the original ``WebsiteUser`` (shop scenario), forcing
``wait_time = constant_throughput(BENCH_RPS_PER_USER)`` → fixed offered throughput,
identical to the monoliths. The upstream
``microservices-demo/src/loadgenerator/locustfile.py`` stays intact.
"""
import importlib.util
import os
from pathlib import Path

from locust import constant_throughput

_RPS = float(os.getenv("BENCH_RPS_PER_USER", "1.0"))
_ORIG = (Path(__file__).resolve().parents[2]
         / "microservices-demo/src/loadgenerator/locustfile.py")

_spec = importlib.util.spec_from_file_location("_ob_orig", _ORIG)
_ob = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ob)


class WebsiteUser(_ob.WebsiteUser):
    """Online Boutique, normalized throughput (constant_throughput)."""
    wait_time = constant_throughput(_RPS)
