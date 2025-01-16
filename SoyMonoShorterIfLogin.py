from locust import HttpUser, task, between, LoadTestShape
import json
import csv

resourceDir="./resources"

class SoyMonoUser(HttpUser):
    wait_time = between(5, 10)
    user_index = 0  # Static variable to keep track of user index

    def on_start(self):
        # Carica gli utenti dal file CSV e assegna un utente al processo
        if not hasattr(self, 'users'):
            with open(f'{resourceDir}/soymono2/users.csv') as csv_file:
                reader = csv.DictReader(csv_file)
                SoyMonoUser.users = [row for row in reader]

        # Assegna un ID univoco incrementale per ogni utente
        self.user_data = SoyMonoUser.users[SoyMonoUser.user_index % len(SoyMonoUser.users)]
        SoyMonoUser.user_index += 1

    @task
    def login_and_actions(self):
        email = self.user_data['email']
        password = self.user_data['password']

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
                # Auth verify
                self.client.get(
                    "/api/auth/verify",
                    headers={"Authorization": f"Bearer {access_token}"},
                )

                # Exercise production
                with open(f'{resourceDir}/soymono2/0046_request.json') as json_file:
                    exercise_data = json.load(json_file)
                self.client.post(
                    "/api/exercise-production",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    json=exercise_data,
                )

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
