# IMPORTANTE: Monkey patch PRIMA di qualsiasi altro import

from locust import HttpUser, task, between, events
import json
from pathlib import Path
from base_exp import BaseExp,resourceDir


cwd=Path(__file__).parent


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


class SoyMonoUser(BaseExp):

    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", 15)  # Timeout predefinito di 15 secondi
        return super().request(method, url, **kwargs)

    def __init__(self, *args, **kwargs):
        print("Initializing SoyMonoUser...")
        super().__init__(*args, **kwargs)
        # Fix gevent/threading conflict by disabling cookies
        import requests.cookies
        self.client.cookies = requests.cookies.RequestsCookieJar()

    def userLogic(self):
        print("UserLogic")
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
