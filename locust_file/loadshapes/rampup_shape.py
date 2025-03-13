from locust import LoadTestShape

class CustomLoadShape(LoadTestShape):
    """
    A load shape that gradually increases users up to a maximum value.
    """
    max_users = 100
    ramp_duration = 300  # seconds
    
    def tick(self):
        run_time = self.get_run_time()
        if run_time > self.ramp_duration:
            return None  # End the test
        
        current_users = int((run_time / self.ramp_duration) * self.max_users)
        spawn_rate = self.max_users / self.ramp_duration
        
        return current_users, spawn_rate 