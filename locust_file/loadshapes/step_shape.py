from locust import LoadTestShape

class CustomLoadShape(LoadTestShape):
    """
    A step load shape that increases load in steps and then decreases it.
    """
    step_duration = 60  # seconds per step
    step_users = 20     # users to add/remove per step
    max_users = 100     # maximum number of users
    steps_up = 5        # number of steps to increase users
    steps_down = 5      # number of steps to decrease users
    
    total_duration = (steps_up + steps_down) * step_duration
    
    def tick(self):
        run_time = self.get_run_time()
        if run_time > self.total_duration:
            return None  # End the test
        
        current_step = int(run_time / self.step_duration)
        
        if current_step < self.steps_up:
            # Increasing phase
            current_users = min(self.max_users, (current_step + 1) * self.step_users)
        else:
            # Decreasing phase
            step_down = current_step - self.steps_up
            current_users = max(1, self.max_users - (step_down * self.step_users))
            
        return current_users, self.step_users 