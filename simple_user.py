from locust import HttpUser, task, between

class MyUser(HttpUser):
    wait_time = between(1, 1)  # Each user waits exactly 1 second between requests

    @task
    def get_root(self):
        self.client.get("/")  # Sends a GET request to "http://localhost/"