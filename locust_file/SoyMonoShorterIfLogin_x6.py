# IMPORTANTE: Monkey patch PRIMA di qualsiasi altro import
import gevent.monkey
gevent.monkey.patch_all()

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

ms_exercise_conf={ "service_name": "ms-exercise",
           "stack_name": "ms-stack-v5",
           "sysfile": cwd.parent/"sou"/"monotloth-v5.yml",
           "control_widow": 15,
           "estimation_window": 10,
           "measurament_period":"1s",
           "outfile":cwd.parent/"results"/f"{Path(__file__).stem}"/f"{Path(__file__).stem}_ms-exercise.csv",
           "stealth":True,
           "init_repica":6,
           "prediction_horizon":10,
           "target_utilization":0.2,
           "prometheus":{
               "host":"127.0.0.1",
               "port":9090
           },
           #"remote":"192.168.3.102",
           #"remote_docker_port":2375
           "remote":None,
           "remote_docker_port":None
         }

ms_other_conf={ "service_name": "ms-other",
           "stack_name": "ms-stack-v5",
           "sysfile": cwd.parent/"sou"/"monotloth-v5.yml",
           "control_widow": 15,
           "estimation_window": 10,
           "measurament_period":"1s",
           "outfile":cwd.parent/"results"/f"{Path(__file__).stem}"/f"{Path(__file__).stem}_ms-other.csv",
           "stealth":True,
           "init_repica":6,
           "prediction_horizon":10,
           "target_utilization":0.2,
           "prometheus":{
               "host":"127.0.0.1",
               "port":9090
           },
           #"remote":"192.168.3.102",
           #"remote_docker_port":2375
           "remote":None,
           "remote_docker_port":None
         }

gateway_conf={ "service_name": "gateway",
           "stack_name": "ms-stack-v5",
           "sysfile": cwd.parent/"sou"/"monotloth-v5.yml",
           "control_widow": 15,
           "estimation_window": 10,
           "measurament_period":"1s",
           "outfile":cwd.parent/"results"/f"{Path(__file__).stem}"/f"{Path(__file__).stem}_gateway.csv",
           "stealth":True,
           "init_repica":6,
           "prediction_horizon":10,
           "target_utilization":0.2,
           "prometheus":{
               "host":"127.0.0.1",
               "port":9090
           },
           #"remote":"192.168.3.102",
           #"remote_docker_port":2375
           "remote":None,
           "remote_docker_port":None
         } 

#Qui la logica di avvio del control loop specifica per ogni locus file
ctrlLoop_ms_exercise=ControlLoop(config=ms_exercise_conf)
ctrlLoop_ms_other=ControlLoop(config=ms_other_conf)
ctrlLoop_gateway=ControlLoop(config=gateway_conf)

@events.test_start.add_listener
def on_locust_start(environment, **_kwargs):
    if not isinstance(environment.runner, WorkerRunner):
        gevent.spawn(ctrlLoop_ms_exercise.loop, environment)
        gevent.spawn(ctrlLoop_ms_other.loop, environment)
        gevent.spawn(ctrlLoop_gateway.loop, environment)

@events.test_stop.add_listener
def on_locust_stop(environment, **_kwargs):
    global ctrlLoop_ms_exercise, ctrlLoop_ms_other, ctrlLoop_gateway
    ctrlLoop_ms_exercise.saveResults()
    ctrlLoop_ms_other.saveResults()
    ctrlLoop_gateway.saveResults()

class SoyMonoUser(BaseExp):

    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", 15)  # Timeout predefinito di 15 secondi
        return super().request(method, url, **kwargs)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Fix gevent/threading conflict by disabling cookies
        import requests.cookies
        self.client.cookies = requests.cookies.RequestsCookieJar()

    def userLogic(self):
        # Implementazione specifica della logica utente
        email = self.user_data['email']
        password = self.user_data['password']
        # OPTIONS before login
        try:
            self.client.request("OPTIONS", "/api/user/login", timeout=15, name="(opt)/api/user/login")
        except Exception:
            pass
        # Login
        login_response = self.client.post(
            "/api/user/login",
            headers={"Content-Type": "application/json"},
            json={"email": email, "password": password},
            name="POST /api/user/login",
            timeout=15
        )
        if login_response.status_code == 200:
            # Extract tokens from response cookies
            access_token = None
            refresh_token = None
            for cookie in login_response.cookies:
                if cookie.name == "access_token":
                    access_token = cookie.value
                elif cookie.name == "refresh_token":
                    refresh_token = cookie.value
            
        else:
            # Log debug info for non-200 responses and stop this user iteration
            try:
                body_preview = login_response.text[:200]
            except Exception:
                body_preview = ""
            self.environment.events.request.fire(
                request_type="POST",
                name="POST /api/user/login [debug]",
                response_time=0,
                response_length=len(login_response.content or b"") if hasattr(login_response, 'content') else 0,
                exception=Exception(f"Login failed {login_response.status_code}: {body_preview}")
            )
            return

        if access_token:
            # OPTIONS before auth verify
            try:
                self.client.request("OPTIONS", "/api/auth/verify", timeout=15, name="(opt)/api/auth/verify")
            except Exception:
                pass
            # Auth verify
            self.client.get(
                "/api/auth/verify",
                headers={"Authorization": f"Bearer {access_token}"},
                name="GET /api/auth/verify",
                timeout=15
            )
            # OPTIONS before exercise production
            try:
                self.client.request("OPTIONS", "/api/exercise-production", timeout=15, name="(opt)/api/exercise-production")
            except Exception:
                pass
            # Exercise production
            #with open(f'{resourceDir.absolute()}/soymono2/0046_request.json') as json_file:
            with open(f'{resourceDir.absolute()}/soymshttp1/0049_request.json') as json_file:
                exercise_data = json.load(json_file)
                self.client.post(
                    "/api/exercise-production",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    json=exercise_data,
                    name="POST /api/exercise-production",
                    timeout=15
                )
            # OPTIONS before logout
            try:
                self.client.request("OPTIONS", "/api/user/logout", timeout=15, name="(opt)/api/user/logout")
            except Exception:
                pass
            # Logout
            self.client.delete(
                "/api/user/logout",
                headers={"Authorization": f"Bearer {access_token}"},
                name="DELETE /api/user/logout",
                timeout=15
            )
