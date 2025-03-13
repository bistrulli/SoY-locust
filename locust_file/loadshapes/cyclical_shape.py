from locust import LoadTestShape

class CustomLoadShape(LoadTestShape):
    """
    This load shape simulates a workload pattern with a ramp-up phase, a constant phase, and a pause phase.
    After the total test duration (max_duration) is reached, it returns None, ending the test.
    """
    max_users = 100
    ramp_duration = 60         # seconds for ramp-up
    constant_duration = 60     # seconds for constant load
    pause_duration = 240       # seconds with no load

    cycle_duration = ramp_duration + constant_duration + pause_duration

    max_duration = cycle_duration*4         # total duration of the test in seconds

    def tick(self):
        run_time = self.get_run_time()
        if run_time > self.max_duration:
            return None  # End the test
        
        cycle_time = run_time % self.cycle_duration

        if cycle_time < self.ramp_duration:
            # Ramp-up phase: linear increase of users
            current_users = int((cycle_time / self.ramp_duration) * self.max_users)
            spawn_rate = self.max_users / self.ramp_duration
        elif cycle_time < (self.ramp_duration + self.constant_duration):
            # Constant phase: maintain max_users
            current_users = self.max_users
            spawn_rate = 1
        else:
            # Pause phase: drop to zero users
            current_users = 1
            spawn_rate = 1

        return current_users, spawn_rate 