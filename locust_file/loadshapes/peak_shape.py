from locust import LoadTestShape

class CustomLoadShape(LoadTestShape):
    """
    A load shape that ramps up to a peak, stays there briefly, then ramps down.
    """
    max_users = 100
    ramp_up_duration = 120    # seconds
    peak_duration = 60        # seconds
    ramp_down_duration = 120  # seconds
    
    total_duration = ramp_up_duration + peak_duration + ramp_down_duration
    
    def tick(self):
        run_time = self.get_run_time()
        if run_time > self.total_duration:
            return None  # End the test
        
        if run_time < self.ramp_up_duration:
            # Ramp up phase
            current_users = int((run_time / self.ramp_up_duration) * self.max_users)
            spawn_rate = self.max_users / self.ramp_up_duration
        elif run_time < (self.ramp_up_duration + self.peak_duration):
            # Peak phase
            current_users = self.max_users
            spawn_rate = 1
        else:
            # Ramp down phase
            ramp_down_time = run_time - self.ramp_up_duration - self.peak_duration
            current_users = int(self.max_users * (1 - (ramp_down_time / self.ramp_down_duration)))
            spawn_rate = self.max_users / self.ramp_down_duration
            
        return max(1, current_users), spawn_rate  # Ensure at least 1 user 