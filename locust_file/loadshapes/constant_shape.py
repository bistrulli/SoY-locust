from locust import LoadTestShape


class CustomLoadShape(LoadTestShape):
    """
    A constant load shape that maintains a fixed number of users for a set duration.
    """
    use_common_options = True

    def tick(self):
        duration = self.runner.environment.parsed_options.run_time
        num_users = self.runner.environment.parsed_options.num_users
        spawn_rate = self.runner.environment.parsed_options.spawn_rate
        run_time = self.get_run_time()

        if run_time > duration:
            return None  # End the test
        print("Constant Load Shape: ", num_users, spawn_rate, run_time)
        return num_users, spawn_rate, run_time
