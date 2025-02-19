from locust import HttpUser, task, between, LoadTestShape
from locust import events
from locust.runners import WorkerRunner
import json
import gevent
import csv
from pathlib import Path
import time
from base_exp import BaseExp,resourceDir
from controller import ControlLoop
import gevent

cwd=Path(__file__).parent

exp_conf={ "sercice_name": "monotloth-stack_node",
           "sysfile": cwd.parent/"sou"/"monotloth-v4.yaml"
         }

#Qui la logica di avvio del control loop specifica per ogni locus file
ctrlLoop=ControlLoop(config=exp_conf)
@events.test_start.add_listener
def on_locust_start(environment, **_kwargs):
    if not isinstance(environment.runner, WorkerRunner):
        gevent.spawn(ctrlLoop.loop, environment)

class SoyMonoUser(BaseExp):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def userLogic(self):
        # Implementazione specifica della logica utente
        email = self.user_data['email']
        password = self.user_data['password']
        # OPTIONS before login
        self.client.request("OPTIONS", "/api/user/login")
        # Login
        login_response = self.client.post(
            "/api/user/login",
            headers={"Content-Type": "application/json"},
            json={"email": email, "password": password},
        )
        if login_response.status_code == 200:
            access_token = login_response.cookies.get("access_token")
            refresh_token = login_response.cookies.get("refresh_token")
            if access_token:
                # OPTIONS before auth verify
                self.client.request("OPTIONS", "/api/auth/verify")
                # Auth verify
                self.client.get(
                    "/api/auth/verify",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                # OPTIONS before exercise production
                self.client.request("OPTIONS", "/api/exercise-production")
                # Exercise production
                with open(f'{resourceDir.absolute()}/soymono2/0046_request.json') as json_file:
                    exercise_data = json.load(json_file)
                    self.client.post(
                        "/api/exercise-production",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json",
                        },
                        json=exercise_data,
                    )
                # OPTIONS before logout
                self.client.request("OPTIONS", "/api/user/logout")
                # Logout
                self.client.delete(
                    "/api/user/logout",
                    headers={"Authorization": f"Bearer {access_token}"},
                )

# class CustomLoadShape(LoadTestShape):
#     max_users = 200
#     phase_duration = 60
#     rest_duration = 240
    
#     stages = [
#         {"duration": phase_duration, "users": max_users, "spawn_rate": 10},
#         {"duration": phase_duration + rest_duration, "users": 0, "spawn_rate": 0},
#     ] * 5

#     def tick(self):
#         run_time = self.get_run_time()

#         for stage in self.stages:
#             if run_time < stage["duration"]:
#                 return stage["users"], stage["spawn_rate"]

#         return None
