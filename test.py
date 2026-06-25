# IMPORTANTE: Monkey patch PRIMA di qualsiasi altro import

from locust import HttpUser, task, between, events, SequentialTaskSet, LoadTestShape,FastHttpUser,constant
import json
from pathlib import Path
import csv
import time
from threading import Lock
import random

USER_INDEX = 0
USER_INDEX_LOCK = Lock()

cwd = Path(__file__).parent


class QuickstartUser(SequentialTaskSet):

    users = None
    exercise_data= None

    def on_start(self):
        with open(f'resources/soymshttp1/users.csv') as csv_file:
            reader = csv.DictReader(csv_file)
            self.users = [row for row in reader]

        self.previous_ok = True  # état initial
        with open(f'resources/soymshttp1/0049_request.json') as json_file:
            self.exercise_data = json.load(json_file)


    @task
    def request_1_0(self):
        response = self.client.request("OPTIONS", "/api/user/login", timeout=15,
                                       name="request_1_0 - (opt)/api/user/login")
        if response.status_code < 300:
            self.previous_ok = True
        else:
            self.previous_ok = False

    @task
    def request_1_1(self):
        if not self.previous_ok:
            return
        index=random.randint(0, len(self.users)-1)



        email = self.users[index ]["email"]
        password = self.users[index ]["password"]
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
        response = self.client.request("OPTIONS", "/api/auth/verify", timeout=15,
                                       name="request_2_0 - (opt)/api/auth/verify")
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

        response = self.client.post(
            "/api/exercise-production",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            json=self.exercise_data,
            name="request_3_1 - POST /api/exercise-production",
            timeout=15
        )
        self.previous_ok = (response.status_code < 300)

    @task
    def request_4_0(self):
        if not self.previous_ok:
            return
        response = self.client.request("OPTIONS", "/api/user/logout", timeout=15,
                                       name="request_4_0 - (opt)/api/user/logout")
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
        response = self.client.request("OPTIONS", "/api/auth/verify", timeout=15,
                                       name="request_5_0 - (opt)/api/auth/verify")
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


class WebsiteUser(FastHttpUser):
    wait_time = constant(0)
    tasks = [QuickstartUser]
