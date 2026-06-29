"""bench — unified harness for running SoY-locust load tests.

Drives the load (Locust) on several Docker infrastructures (monolith-v4,
monolith-v5, microservices-demo / Online Boutique), with interchangeable
scaling strategies (uopt / hpa / manual / none) and collection of system +
energy metrics (psutil + Scaphandre RAPL + Tasmota power meter).

See README-bench.md for setup and usage.
"""

__version__ = "0.1.0"
