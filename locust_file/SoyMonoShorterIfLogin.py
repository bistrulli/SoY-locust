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
           "sysfile": cwd.parent/"sou"/"monotloth-v4.yml",
           "control_widow": 15,
           "estimation_window": 20,
           "measurament_period":"1s",
           "outfile":cwd.parent/"results"/f"{Path(__file__).stem}.csv",
           "stealth":False
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

class RampLoadShape(LoadTestShape):
    """
    Load shape that ramps up users from 0 to max_users linearly over ramp_up_time seconds,
    then maintains max_users until run_time is reached.
    """
    max_users = 80
    ramp_up_time = 300  # secondi per l'incremento lineare
    run_time = 600      # durata totale del test in secondi

    def tick(self):
        current_time = self.get_run_time()
        if current_time < self.run_time:
            # Aumento lineare degli utenti
            current_users = int(self.max_users * current_time / self.ramp_up_time)
            spawn_rate = current_users / 10 if current_users > 0 else 1
            return current_users, spawn_rate
