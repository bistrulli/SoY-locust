from locust import HttpUser, task, between, LoadTestShape
import json
import csv
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

resourceDir = Path(__file__).parent.parent / Path("resources")

class SoyMonoUser(HttpUser):
    wait_time = between(1, 1.0001)
    user_index = 0  # Static variable to keep track of user index

    headers_15 = {
            "Access-Control-Request-Headers": "cache-control,content-type",
            "Access-Control-Request-Method": "POST",
            "Origin": "http://192.168.3.136:3001",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
        }

    headers_16 = {
        "Accept": "application/json, text/plain, */*",
        "Cache-Control": "no-cache",
        "Content-Language": "en",
        "Content-Type": "application/json",
        "Origin": "http://192.168.3.136:3001",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }

    headers_6 = {
        "Access-Control-Request-Headers": "cache-control",
        "Access-Control-Request-Method": "GET",
        "Origin": "http://192.168.3.136:3001",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }

    headers_34 = {
        "Accept": "application/json, text/plain, */*",
        "Cache-Control": "no-cache",
        "Content-Language": "en",
        "If-None-Match": "W/\"6c-2eI3aulyU1sMMO4jADRTZot5SA4\"",
        "Origin": "http://192.168.3.136:3001",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }

    headers_55 = {
        "Access-Control-Request-Headers": "cache-control",
        "Access-Control-Request-Method": "DELETE",
        "Origin": "http://192.168.3.136:3001",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }

    def on_start(self):
        # Load users from the CSV file and assign a user to the process
        if not hasattr(self, 'users'):
            with open(f'{resourceDir}/soymono2/users.csv') as csv_file:
                reader = csv.DictReader(csv_file)
                SoyMonoUser.users = [row for row in reader]

        # Assign a unique incremental ID for each user
        self.user_data = SoyMonoUser.users[SoyMonoUser.user_index % len(SoyMonoUser.users)]
        SoyMonoUser.user_index += 1

    @task
    def login_and_actions(self):
        email = self.user_data['email']
        password = self.user_data['password']
        try:
            # Login
            # login_response = self.client.post(
            #     "/api/user/login",
            #     headers={
            #         "Content-Type": "application/json",
            #     },
            #     json={"email": email, "password": password},
            # )
            login_response = self.client.post(
                "/api/user/login",
                headers=SoyMonoUser.headers_16,
                json={
                    "email": email,
                    "password": password,
                },
            )

            if login_response.status_code == 200:
                access_token = login_response.cookies.get("access_token")
                refresh_token = login_response.cookies.get("refresh_token")

                if access_token:
                    # Auth verify
                    # self.client.get(
                    #     "/api/auth/verify",
                    #     headers={"Authorization": f"Bearer {access_token}"},
                    # )
                    self.client.get("/api/auth/verify", headers=SoyMonoUser.headers_34)

                    # # Exercise production
                    # with open(f'{resourceDir}/soymono2/0046_request.json') as json_file:
                    #     exercise_data = json.load(json_file)
                    #     self.client.post(
                    #         "/api/exercise-production",
                    #         headers={
                    #             "Authorization": f"Bearer {access_token}",
                    #             "Content-Type": "application/json",
                    #         },
                    #         json=exercise_data
                    #     )
                    
                
                    json_data = json.load(open(f'{resourceDir}/soymono2/0046_request.json'))
                    self.client.post(
                        "/api/exercise-production",
                        headers=SoyMonoUser.headers_16,
                        json=json_data
                    )

                    # Logout
                    self.client.delete(
                        "/api/user/logout",
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
            else:
                logger.error(f"Login failed with status code {login_response.status_code}: {login_response.text}")
        except Exception as e:
            # Log exception details
            logger.error("An exception occurred during login and actions:")
            logger.error(f"Type: {type(e)}")
            logger.error(f"Details: {e}")
            if hasattr(e, 'request'):
                logger.error(f"Request: {e.request}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response: {e.response.status_code} - {e.response.text}")
            # Optionally re-raise the exception to stop the task
            raise
