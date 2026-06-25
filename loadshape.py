
from locust import HttpUser, task, between, events, SequentialTaskSet
from locust import LoadTestShape
import json
from pathlib import Path
import csv
import time
import math

cwd = Path(__file__).parent
RUN_OPTS = {}


class RampShape(LoadTestShape):


    def tick(self):
        global RUN_OPTS
        current_run_time = self.get_run_time()

        run_time = RUN_OPTS.get("run_time", 60)
        ramp_duration = RUN_OPTS.get("ramp_duration", 10)
        spawn_rate = RUN_OPTS.get("spawn_rate", 10)
        num_users = RUN_OPTS.get("num_users", 100)


        if current_run_time < run_time:
            user_count = int(current_run_time * spawn_rate)
            if user_count > num_users:
                user_count = num_users
            return (user_count, spawn_rate)
        return None


@events.init_command_line_parser.add_listener
def _(parser):
    parser.add_argument("--run_time", type=int, env_var="run_time", default=60, help="run_time")
    parser.add_argument("--num_users", type=int, env_var="num_users", default=100, help="num_users")
    parser.add_argument("--spawn_rate", type=float, env_var="SPAWN_RATE", default=10, help="spawn_rate")
#    parser.add_argument("--ramp_duration", type=float, env_var="ramp_duration", default=10, help="ramp_duration")


@events.init.add_listener
def on_locust_init(environment, **kwargs):
    # parsed_options contient les arguments CLI
    opts = environment.parsed_options
    RUN_OPTS["run_time"] = int(opts.run_time)
#    RUN_OPTS["ramp_duration"] = int(opts.ramp_duration)
    RUN_OPTS["num_users"] = int(opts.num_users)
    RUN_OPTS["spawn_rate"] = int(opts.spawn_rate)


