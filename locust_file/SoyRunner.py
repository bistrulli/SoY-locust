from locust import HttpUser, task, between
from locust import events
from locust.runners import WorkerRunner
import json
import gevent
import csv
from pathlib import Path
import time
from base_exp import BaseExp, resourceDir
from controller import ControlLoop
import gevent
import json

cwd = Path(__file__).parent

with open('/tmp/xp.json') as f:
    exp_conf = json.load(f)
    print(exp_conf)

with open(f'{resourceDir.absolute()}/paths.json') as f:
    paths = json.load(f)
    print(paths)



# Qui la logica di avvio del control loop specifica per ogni locus file
ctrlLoop = ControlLoop(config=exp_conf)


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
        self.client.request("OPTIONS", paths[exp_conf["stack_name"]]["login"], timeout=1)
        # Login
        login_response = self.client.post(
            paths[exp_conf["stack_name"]]["login"],
            headers={"Content-Type": "application/json"},
            json={"email": email, "password": password},
            timeout=1
        )
        if login_response.status_code == 200:
            access_token = login_response.cookies.get("access_token")
            refresh_token = login_response.cookies.get("refresh_token")
            if access_token:
                # OPTIONS before auth verify
                self.client.request("OPTIONS", paths[exp_conf["stack_name"]]["verify"], timeout=1)
                # Auth verify
                self.client.get(
                    paths[exp_conf["stack_name"]]["verify"],
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=1
                )
                # OPTIONS before exercise production
                self.client.request("OPTIONS", paths[exp_conf["stack_name"]]["exercice"], timeout=1)
                # Exercise production
                with open(f'{resourceDir.absolute()}/{paths[exp_conf["stack_name"]]["file"]}') as json_file:
                    exercise_data = json.load(json_file)
                    self.client.post(
                        paths[exp_conf["stack_name"]]["exercice"],
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json",
                        },
                        json=exercise_data,
                        timeout=1
                    )
                # OPTIONS before logout
                self.client.request("OPTIONS", paths[exp_conf["stack_name"]]["logout"], timeout=1)
                # Logout
                self.client.delete(
                    paths[exp_conf["stack_name"]]["logout"],
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=1
                )
