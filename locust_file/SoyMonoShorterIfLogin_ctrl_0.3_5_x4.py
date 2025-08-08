from locust import HttpUser, task, between
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

exp_conf={ "service_name": "node",
           "stack_name": "ms-stack-v5",
           "sysfile": cwd.parent/"sou"/"monotloth-v4.yml",
           "control_widow": 1,
           "estimation_window": 10,
           "measurament_period":"1s",
           "outfile":cwd.parent/"results"/f"{Path(__file__).stem}"/f"{Path(__file__).stem}.csv",
           "stealth":False,
           "init_repica":1,
           "prediction_horizon":5,
           "target_utilization":0.3,
           "prometheus":{
               "host":"192.168.3.102",
               "port":9090
           },
           "remote":"192.168.3.102",
           "remote_docker_port":2375
         }

#Qui la logica di avvio del control loop specifica per ogni locus file
ctrlLoop=ControlLoop(config=exp_conf)
@events.test_start.add_listener
def on_locust_start(environment, **_kwargs):
    if not isinstance(environment.runner, WorkerRunner):
        gevent.spawn(ctrlLoop.loop, environment)

@events.test_stop.add_listener
def on_locust_stop(environment, **_kwargs):
    global ctrlLoop
    ctrlLoop.saveResults()

class SoyMonoUser(BaseExp):

    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", 1)  # Timeout predefinito di 10 secondi
        return super().request(method, url, **kwargs)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def userLogic(self):
        # Implementazione specifica della logica utente
        email = self.user_data['email']
        password = self.user_data['password']
        # OPTIONS before login
        self.client.request("OPTIONS", "/api/user/login", timeout=1)
        # Login
        login_response = self.client.post(
            "/api/user/login",
            headers={"Content-Type": "application/json"},
            json={"email": email, "password": password},
            timeout=1
        )
        if login_response.status_code == 200:
            access_token = login_response.cookies.get("access_token")
            refresh_token = login_response.cookies.get("refresh_token")
            if access_token:
                # OPTIONS before auth verify
                self.client.request("OPTIONS", "/api/auth/verify", timeout=1)
                # Auth verify
                self.client.get(
                    "/api/auth/verify",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=1
                )
                # OPTIONS before exercise production
                self.client.request("OPTIONS", "/api/exercise-production", timeout=1)
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
                        timeout=1
                    )
                # OPTIONS before logout
                self.client.request("OPTIONS", "/api/user/logout", timeout=1)
                # Logout
                self.client.delete(
                    "/api/user/logout",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=1
                )
