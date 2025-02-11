from locust import HttpUser, task, between, LoadTestShape
from locust import events
from locust.runners import WorkerRunner
import json
import gevent
import csv
from pathlib import Path
import time
from estimator import QNEstimaator
from controller import OPTCTRL
from estimator import Monitoring
from locust_plugins.listeners import PrometheusListener


end=None
setCores=1
quotaCores=0
estimator=None
controller=None
monitor=None

# Abilita Prometheus su porta 9646
PrometheusListener()  

@events.test_start.add_listener
def on_locust_start(environment, **_kwargs):
    global end
    end = False
    # Salva il tempo di inizio in environment se non esiste
    if not hasattr(environment, "start_time"):
        environment.start_time = time.time()
    if not isinstance(environment.runner, WorkerRunner):
        gevent.spawn(controller_loop, environment)

@events.test_stop.add_listener
def on_locust_stop(environment, **_kwargs):
    global end
    end=True

def controller_loop(environment): 
    import time  # Necessario per time.time()
    global setCores, quotaCores, estimator, controller
    estimator=QNEstimaator()
    controller=OPTCTRL(init_cores=setCores, min_cores=0.1, max_cores=16, st=1)
    monitor=Monitoring(window=30, sla=0.2)
    while not end:
        # Ottieni il tempo corrente.
        # Se environment.runner non ha start_time, usa il valore salvato in environment.start_time
        if hasattr(environment, "shape_class") and environment.shape_class is not None:
            t = environment.shape_class.get_run_time()
        else:
            t = time.time() - (getattr(environment.runner, "start_time", environment.start_time))
        print(f"###tick={t}###")
        monitor.tick(t)
        time.sleep(1)

resourceDir=Path(__file__).parent.parent/Path("resources")

class SoyMonoUser(HttpUser):
    wait_time = between(1, 1)
    user_index = 0  # Static variable to keep track of user index

    def on_start(self):
        # Carica gli utenti dal file CSV e assegna un utente al processo
        if not hasattr(self, 'users'):
            with open(f'{resourceDir.absolute()}/soymono2/users.csv') as csv_file:
                reader = csv.DictReader(csv_file)
                SoyMonoUser.users = [row for row in reader]

        # Assegna un ID univoco incrementale per ogni utente
        self.user_data = SoyMonoUser.users[SoyMonoUser.user_index % len(SoyMonoUser.users)]
        SoyMonoUser.user_index += 1

    @task
    def login_and_actions(self):
        email = self.user_data['email']
        password = self.user_data['password']

        # OPTIONS before login
        self.client.request("OPTIONS", "/api/user/login")
        
        # Login
        login_response = self.client.post(
            "/api/user/login",
            headers={
                "Content-Type": "application/json",
            },
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
