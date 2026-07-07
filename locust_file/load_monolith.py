"""*Load-only* locustfile for the monoliths (v4 & v5).

Reproduces the user behavior of ``SoyMonoShorterIfLogin_*`` (login →
verify → exercise-production → logout) BUT **without** an embedded control loop:
scaling is driven externally by ``bench.scaling.ScalingLoop``.

``base_exp`` already starts the Locust Prometheus server (gauge
``locust_active_users`` on :9646) used as the active-users signal.

Usage (via the harness):
    locust -f locust_file/load_monolith.py,<loadshape> --host http://localhost:80 ...
"""
import json
import os
from pathlib import Path

from locust import constant_throughput

from base_exp import BaseExp, resourceDir


class SoyMonoUser(BaseExp):
    # Normalized throughput: each user triggers its scenario at a FIXED rate
    # (iterations/s), regardless of the response time → offered throughput
    # = users × BENCH_RPS_PER_USER, identical across infra.
    wait_time = constant_throughput(float(os.getenv("BENCH_RPS_PER_USER", "1.0")))

    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", 15)
        return super().request(method, url, **kwargs)

    def userLogic(self):
        email = self.user_data["email"]
        password = self.user_data["password"]

        self.client.request("OPTIONS", "/api/user/login", timeout=15)
        login_response = self.client.post(
            "/api/user/login",
            headers={"Content-Type": "application/json"},
            json={"email": email, "password": password},
            timeout=15,
        )
        if login_response.status_code == 200:
            access_token = login_response.cookies.get("access_token")
            if access_token:
                self.client.request("OPTIONS", "/api/auth/verify", timeout=15)
                self.client.get(
                    "/api/auth/verify",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=15,
                )
                self.client.request("OPTIONS", "/api/exercise-production", timeout=15)
                with open(f"{resourceDir.absolute()}/soymono2/0046_request.json") as f:
                    exercise_data = json.load(f)
                self.client.post(
                    "/api/exercise-production",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    json=exercise_data,
                    timeout=15,
                )
                self.client.request("OPTIONS", "/api/user/logout", timeout=15)
                self.client.delete(
                    "/api/user/logout",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=15,
                )
