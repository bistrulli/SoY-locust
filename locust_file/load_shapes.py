from locust import LoadTestShape

class CyclicalLoadShape(LoadTestShape):
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

class StepLoadShape(LoadTestShape):
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

class ConstantLoadShape(LoadTestShape):
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

class RampUpLoadShape(LoadTestShape):
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

class PeakLoadShape(LoadTestShape):
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

# Dictionary to map shape names to their respective classes
shape_classes = {
    "cyclical": CyclicalLoadShape,
    "step": StepLoadShape,
    "constant": ConstantLoadShape,
    "rampup": RampUpLoadShape,
    "peak": PeakLoadShape
}

def get_shape_class(shape_name):
    """
    Returns the LoadShape class for the given shape name.
    """
    if shape_name not in shape_classes:
        raise ValueError(f"Unknown shape: {shape_name}. Available shapes: {', '.join(shape_classes.keys())}")
    return shape_classes[shape_name] 