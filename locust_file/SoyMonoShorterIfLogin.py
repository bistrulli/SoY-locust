from locust import HttpUser, task, between, LoadTestShape
from locust import events
from locust.runners import WorkerRunner
import json
import gevent
import csv
from pathlib import Path

end=None

@events.test_start.add_listener
def on_locust_start(environment, **_kwargs):
    global end
    end=False
    if not isinstance(environment.runner, WorkerRunner):
        gevent.spawn(controller_loop, environment)

@events.test_stop.add_listener
def on_locust_stop(environment, **_kwargs):
    global end
    end=True

def controller_loop(environment):
    import time  # Necessario per time.time()
    global setCores, quotaCores
    shape = environment.shape_class
    while not end:
        # Ottieni il tempo corrente:
        if hasattr(environment, "shape_class") and environment.shape_class is not None:
            t = environment.shape_class.get_run_time()
        else:
            t = time.time() - environment.runner.start_time
        # cores = controller.tick(t)
        # setCores = min(int(cores), controller.max_cores-1)
        # quotaCores = max(controller.min_cores, cores-setCores)
        # setCores = max(setCores, 1)
        # print(f"{controller.name} - t: {int(t)} - cores: {cores} - RT: {controller.monitoring.getRT()} - users: {controller.monitoring.getUsers()}")
        # containerSet.update(cpuset_cpus=f"{cpu_range_start}-{cpu_range_start+setCores-1}")
        # if cores != setCores:
        #     containerQuotas.update(cpu_quota=int(quotaCores*CPU_PERIOD), cpu_period=CPU_PERIOD)
        print(f"###tick={t}###")
        sleep(1)

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
