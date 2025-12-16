# IMPORTANTE: Monkey patch PRIMA di qualsiasi altro import

from locust import HttpUser, task, between, events, SequentialTaskSet
import json
from pathlib import Path
import time

cwd = Path(__file__).parent


@events.init_command_line_parser.add_listener
def _(parser):
    parser.add_argument("--ramp_duration", type=int, env_var="RAMP_DURATION", default=10, help="ramp_duration")
    parser.add_argument("--pause_duration", type=int, env_var="PAUSE_DURATION", default=5, help="pause_duration")


@events.test_start.add_listener
def on_locust_start(environment, **_kwargs):
    print("events.test_start.add_listener")


@events.test_stop.add_listener
def on_locust_stop(environment, **_kwargs):
    print("events.test_stop.add_listener")


class QuickstartUser(SequentialTaskSet):
    wait_time = between(1, 5)

    def on_start(self):
        self.previous_ok = True  # état initial

    @task
    def request_1_0(self):
        response = self.client.request("OPTIONS", "/api/user/login", timeout=15, name="request_1_0 - (opt)/api/user/login")
        if response.status_code < 300:
            self.previous_ok = True
        else:
            self.previous_ok = False

    @task
    def request_1_1(self):
        if not self.previous_ok:
            return
        email = "etud-ig3-2@yopmail.fr"
        password = "plageCT"
        response = self.client.post(
            "/api/user/login",
            headers={"Content-Type": "application/json"},
            json={"email": email, "password": password},
            name="request_1_1 - POST /api/user/login",
            timeout=15
        )
        if response.status_code < 300:
            self.previous_ok = True
            self.access_token = None
            self.refresh_token = None
            for cookie in response.cookies:
                if cookie.name == "access_token":
                    self.access_token = cookie.value
                elif cookie.name == "refresh_token":
                    refresh_token = cookie.value

        else:
            self.previous_ok = False


    @task
    def request_2_0(self):
        if not self.previous_ok:
            return
        response = self.client.request("OPTIONS", "/api/auth/verify", timeout=15, name="request_2_0 - (opt)/api/auth/verify")
        self.previous_ok = (response.status_code < 300)

    @task
    def request_2_1(self):
        if not self.previous_ok:
            return
        response = self.client.get(
            "/api/auth/verify",
            headers={"Authorization": f"Bearer {self.access_token}"},
            name="request_2_1 - GET /api/auth/verify",
            timeout=15
        )
        self.previous_ok = (response.status_code < 300)

    @task
    def request_3_0(self):
        if not self.previous_ok:
            return
        response = self.client.request("OPTIONS", "/api/exercise-production", timeout=15,
                                       name="request_3_0 - (opt)/api/exercise-production")
        self.previous_ok = (response.status_code < 300)

    @task
    def request_3_1(self):
        if not self.previous_ok:
            return
        with open(f'resources/soymshttp1/0049_request.json') as json_file:
            exercise_data = json.load(json_file)

        response = self.client.post(
            "/api/exercise-production",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            json=exercise_data,
            name="request_3_1 - POST /api/exercise-production",
            timeout=15
        )
        self.previous_ok = (response.status_code < 300)


    @task
    def request_4_0(self):
        if not self.previous_ok:
            return
        response = self.client.request("OPTIONS", "/api/user/logout", timeout=15, name="request_4_0 - (opt)/api/user/logout")
        self.previous_ok = (response.status_code < 300)

    @task
    def request_4_1(self):
        if not self.previous_ok:
            return
        response = self.client.delete(
            "/api/user/logout",
            headers={"Authorization": f"Bearer {self.access_token}"},
            name="request_4_1 - DELETE /api/user/logout",
            timeout=15
        )
        self.previous_ok = (response.status_code < 300)


    @task
    def request_5_0(self):
        if not self.previous_ok:
            return
        response = self.client.request("OPTIONS", "/api/auth/verify", timeout=15, name="request_5_0 - (opt)/api/auth/verify")
        self.previous_ok = (response.status_code < 300)

    @task
    def request_5_1(self):
        if not self.previous_ok:
            return
        response = self.client.get(
            "/api/auth/verify",
            headers={"Authorization": f"Bearer {self.access_token}"},
            name="request_5_1 - GET /api/auth/verify",
            timeout=15
        )
        return response.status_code == 401

class WebsiteUser(HttpUser):
    tasks = [QuickstartUser]
