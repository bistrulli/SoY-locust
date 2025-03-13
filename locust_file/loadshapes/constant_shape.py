from locust import LoadTestShape

class CustomLoadShape(LoadTestShape):
    """
    A constant load shape that maintains a fixed number of users for a set duration.
    """
    users = 50          # fixed number of users
    duration = 300      # seconds
    
    def tick(self):
        run_time = self.get_run_time()
        if run_time > self.duration:
            return None  # End the test
            
        return self.users, 10  # Fixed users and spawn rate 