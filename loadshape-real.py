
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
        {"duration": 29, "users": 1, "spawn_rate": 1},
        {"duration": 43, "users": 4000, "spawn_rate": 1000},
        {"duration": 50, "users": 1, "spawn_rate": 1},
        {"duration": 64, "users": 4000, "spawn_rate": 1000},
        {"duration": 86, "users": 1, "spawn_rate": 1},

        {"duration": 114, "users": 1, "spawn_rate": 1},
        {"duration": 128, "users": 4000, "spawn_rate": 1000},
        {"duration": 135, "users": 1, "spawn_rate": 1},
        {"duration": 150, "users": 4000, "spawn_rate": 1000},
        {"duration": 171, "users": 1, "spawn_rate": 1},

        {"duration": 200, "users": 1, "spawn_rate": 1},
        {"duration": 214, "users": 4000, "spawn_rate": 1000},
        {"duration": 221, "users": 1, "spawn_rate": 1},
        {"duration": 235, "users": 4000, "spawn_rate": 1000},
        {"duration": 257, "users": 1, "spawn_rate": 1},

        {"duration": 285, "users": 1, "spawn_rate": 1},
        {"duration": 300, "users": 4000, "spawn_rate": 1000},
        {"duration": 307, "users": 1, "spawn_rate": 1},
        {"duration": 321, "users": 4000, "spawn_rate": 1000},
        {"duration": 342, "users": 1, "spawn_rate": 1},

        {"duration": 371, "users": 1, "spawn_rate": 1},
        {"duration": 385, "users": 4000, "spawn_rate": 1000},
        {"duration": 392, "users": 1, "spawn_rate": 1},
        {"duration": 407, "users": 4000, "spawn_rate": 1000},
        {"duration": 428, "users": 1, "spawn_rate": 1},

        {"duration": 600, "users": 1, "spawn_rate": 1},
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


