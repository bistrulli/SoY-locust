from locust import LoadTestShape


class CustomLoadShape(LoadTestShape):
    """
    This load shape simulates a workload pattern with a ramp-up phase, a constant phase, and a pause phase.
    After the total test duration (max_duration) is reached, it returns None, ending the test.
    """

    """
    A constant load shape that maintains a fixed number of users for a set duration.
    """
    use_common_options = True

    def tick(self):
        duration = self.runner.environment.parsed_options.run_time
        num_users = self.runner.environment.parsed_options.num_users
        # spawn_rate = self.runner.environment.parsed_options.spawn_rate
        ramp_duration = self.runner.environment.parsed_options.ramp_duration
        pause_duration = self.runner.environment.parsed_options.pause_duration

        cycle_duration = ramp_duration + duration + pause_duration
        max_duration = cycle_duration * 4
        run_time = self.get_run_time()

        if run_time > max_duration:
            return None  # End the test

        cycle_time = run_time % cycle_duration

        if cycle_time < ramp_duration:
            # Ramp-up phase: linear increase of users
            current_users = int((cycle_time / ramp_duration) * num_users)
            spawn_rate = num_users / ramp_duration
        elif cycle_time < (ramp_duration + duration):
            # Constant phase: maintain num_users
            current_users = num_users
            spawn_rate = 1
        else:
            # Pause phase: drop to zero users
            current_users = 1
            spawn_rate = 1

        return current_users, spawn_rate
