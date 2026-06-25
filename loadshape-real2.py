
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

    stages = [
        {"duration": 4115, "users": 1, "spawn_rate": 1},
        {"duration": 5143, "users": 800, "spawn_rate": 800},
        {"duration": 7200, "users": 1, "spawn_rate": 1},
        {"duration": 8229, "users": 800, "spawn_rate": 800},
        {"duration": 12343, "users": 1, "spawn_rate": 1},

        {"duration": 16458, "users": 1, "spawn_rate": 1},
        {"duration": 17486, "users": 800, "spawn_rate": 800},
        {"duration": 19543, "users": 1, "spawn_rate": 1},
        {"duration": 20572, "users": 800, "spawn_rate": 800},
        {"duration": 24686, "users": 1, "spawn_rate": 1},

        {"duration": 28800, "users": 1, "spawn_rate": 1},
        {"duration": 29829, "users": 800, "spawn_rate": 800},
        {"duration": 31886, "users": 1, "spawn_rate": 1},
        {"duration": 32915, "users": 800, "spawn_rate": 800},
        {"duration": 37029, "users": 1, "spawn_rate": 1},

        {"duration": 41143, "users": 1, "spawn_rate": 1},
        {"duration": 42172, "users": 800, "spawn_rate": 800},
        {"duration": 44229, "users": 1, "spawn_rate": 1},
        {"duration": 45258, "users": 800, "spawn_rate": 800},
        {"duration": 49372, "users": 1, "spawn_rate": 1},

        {"duration": 53486, "users": 1, "spawn_rate": 1},
        {"duration": 54515, "users": 800, "spawn_rate": 800},
        {"duration": 56572, "users": 1, "spawn_rate": 1},
        {"duration": 57600, "users": 800, "spawn_rate": 800},
        {"duration": 61715, "users": 1, "spawn_rate": 1},

        {"duration": 74058, "users": 1, "spawn_rate": 1},
        {"duration": 12343, "users": 1, "spawn_rate": 1},
    ]


    def tick(self):
        current_run_time = self.get_run_time()

        for stage in self.stages:
            if current_run_time < stage["duration"]:
                tick_data = (stage["users"], stage["spawn_rate"])
                return tick_data

        return None


@events.init_command_line_parser.add_listener
def _(parser):
    parser.add_argument("--run_time", type=int, env_var="run_time", default=60, help="run_time")
    parser.add_argument("--num_users", type=int, env_var="num_users", default=100, help="num_users")
    parser.add_argument("--spawn_rate", type=float, env_var="SPAWN_RATE", default=10, help="spawn_rate")
    parser.add_argument("--ramp_duration", type=float, env_var="ramp_duration", default=10, help="ramp_duration")


@events.init.add_listener
def on_locust_init(environment, **kwargs):
    # parsed_options contient les arguments CLI
    opts = environment.parsed_options
    RUN_OPTS["run_time"] = int(opts.run_time)
    RUN_OPTS["ramp_duration"] = int(opts.ramp_duration)
    RUN_OPTS["num_users"] = int(opts.num_users)
    RUN_OPTS["spawn_rate"] = int(opts.spawn_rate)


