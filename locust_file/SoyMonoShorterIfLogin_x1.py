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
           "estimation_window": 10,
           "measurament_period":"1s",
           "outfile":cwd.parent/"results"/f"{Path(__file__).stem}_long.csv",
           "stealth":True,
           "init_repica":1
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

class CustomLoadShape(LoadTestShape):
    """
    This load shape simulates a workload pattern with a ramp-up phase, a constant phase, and a pause phase.
    After the total test duration (max_duration) is reached, it returns None, ending the test.
    """
    max_users = 100
    ramp_duration = 60         # seconds for ramp-up
    constant_duration = 60     # seconds for constant load
    pause_duration = 240       # seconds with no load

    cycle_duration = ramp_duration + constant_duration + pause_duration

    max_duration = cycle_duration*4         # total duration of the test in seconds

    def tick(self):
        run_time = self.get_run_time()
        if run_time > self.max_duration:
            return None  # End the test
        
        cycle_time = run_time % self.cycle_duration

        if cycle_time < self.ramp_duration:
            # Ramp-up phase: linear increase of users
            current_users = int((cycle_time / self.ramp_duration) * self.max_users)
            spawn_rate = self.max_users / self.ramp_duration
        elif cycle_time < (self.ramp_duration + self.constant_duration):
            # Constant phase: maintain max_users
            current_users = self.max_users
            spawn_rate = 1
        else:
            # Pause phase: drop to zero users
            current_users = 1
            spawn_rate = 1

        return current_users, spawn_rate
