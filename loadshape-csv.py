"""
CSV-based LoadShape for Locust

This load shape reads a waveform from a CSV file and reproduces it during the load test.
The CSV file should contain a single column of numeric values (one per line, no header).
Each value represents the target user count for that second of the test.

Configuration can be done via:
1. Class-level constants (defaults)
2. Environment variables (override defaults)

Environment Variables:
- CSV_SHAPE_FILE: Path to the CSV file containing the waveform
- CSV_SHAPE_AMPLITUDE: Maximum users above the baseline (default: 90)
- CSV_SHAPE_SHIFT: Baseline user count (default: 10)
- CSV_SHAPE_DURATION: Total test duration in seconds (default: from CSV length)
- CSV_SHAPE_FIT_TRACE: "true" to stretch/compress CSV to fit duration, "false" for cyclic (default: false)
- CSV_SHAPE_SPAWN_RATE: Spawn rate for user changes (default: 100)

Example usage:
    python run_load_test.py --loadshape-file locust_file/loadshapes/csv_shape.py ...

With environment variables:
    CSV_SHAPE_FILE=workloads/twitter.csv CSV_SHAPE_AMPLITUDE=100 python run_load_test.py ...
"""

import os
import sys
from pathlib import Path
from locust import LoadTestShape, HttpUser, task, between, events, SequentialTaskSet



RUN_OPTS = {}
max_index = None
max_val = None
min_val = None
scaled_trace = []



def load_csv_data(file_path):
    """
    Load CSV data from file. Supports both single-column CSV and plain text with one value per line.
    Returns a list of float values.
    """
    data = []
    try:
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    # Handle potential CSV format with header or plain numbers
                    try:
                        value = float(line.replace(',', ''))
                        data.append(value)
                    except ValueError:
                        # Skip non-numeric lines (could be header)
                        continue
        return data
    except FileNotFoundError:
        print(f"Error: CSV file not found: {file_path}")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading CSV file '{file_path}': {e}")
        sys.exit(1)


class CustomLoadShape(LoadTestShape):


    def tick(self):
        global RUN_OPTS, max_index, max_val, min_val, scaled_trace
        """
        Returns the current user count and spawn rate based on elapsed time.
        Returns None to end the test when duration is exceeded.
        """
        run_time = self.get_run_time()
        # print(f"Elapsed time: {run_time}s")
        # Check if test duration exceeded
        if run_time > RUN_OPTS["run_time"]:
            return None

        # Calculate the index into the trace data
        if RUN_OPTS["CSV_SHAPE_FIT_TRACE"]:
            # Fit mode: scale the trace to fit the duration
            if RUN_OPTS["run_time"] > 0:
                scaling_ratio = max_index / RUN_OPTS["run_time"]
                trace_index = int(run_time * scaling_ratio)
            else:
                trace_index = 0
            trace_index = min(trace_index, max_index - 1)
        else:
            # Cyclic mode: wrap around when trace ends
            trace_index = int(run_time) % max_index

        user_count = max(1, scaled_trace[trace_index])  # Ensure at least 1 user

        return (user_count, RUN_OPTS["spawn_rate"])


@events.init_command_line_parser.add_listener
def _(parser):
    parser.add_argument("--run_time", type=int, env_var="run_time", default=60, help="run_time")
    parser.add_argument("--num_users", type=int, env_var="num_users", default=100, help="num_users")
    parser.add_argument("--spawn_rate", type=int, env_var="SPAWN_RATE", default=10, help="spawn_rate")
    parser.add_argument("--ramp_duration", type=int, env_var="ramp_duration", default=10, help="ramp_duration")
    parser.add_argument("--CSV_SHAPE_FILE", type=str, env_var="CSV_SHAPE_FILE", default="workloads/twitter.csv",
                        help="CSV_SHAPE_FILE")
    parser.add_argument("--CSV_SHAPE_SHIFT", type=str, env_var="CSV_SHAPE_SHIFT", default=0, help="CSV_SHAPE_SHIFT")
    parser.add_argument("--CSV_SHAPE_FIT_TRACE", type=bool, env_var="CSV_SHAPE_FIT_TRACE", default=True,
                        help="CSV_SHAPE_FIT_TRACE")



@events.init.add_listener
def on_locust_init(environment, **kwargs):
    global RUN_OPTS, max_index, max_val, min_val, scaled_trace
    # parsed_options contient les arguments CLI
    opts = environment.parsed_options
    RUN_OPTS["run_time"] = int(opts.run_time)
    RUN_OPTS["ramp_duration"] = int(opts.ramp_duration)
    RUN_OPTS["num_users"] = int(opts.num_users)
    RUN_OPTS["spawn_rate"] = int(opts.spawn_rate)
    RUN_OPTS["CSV_SHAPE_FILE"] = opts.CSV_SHAPE_FILE

    RUN_OPTS["CSV_SHAPE_SHIFT"] = int(opts.CSV_SHAPE_SHIFT)
    RUN_OPTS["CSV_SHAPE_FIT_TRACE"] = bool(opts.CSV_SHAPE_FIT_TRACE)

    # Load configuration from environment variables or use defaults
    csv_file = RUN_OPTS.get("CSV_SHAPE_FILE")
    amplitude = RUN_OPTS["num_users"]
    shift = RUN_OPTS["CSV_SHAPE_SHIFT"]
    fit_trace = RUN_OPTS["CSV_SHAPE_FIT_TRACE"]
    spawn_rate = RUN_OPTS["spawn_rate"]

    # Resolve CSV file path
    csv_path = Path(csv_file)
    if not csv_path.is_absolute():
        # Try relative to current directory first
        if not csv_path.exists():
            # Try relative to this file's directory
            script_dir = Path(__file__).parent
            csv_path = script_dir / csv_file
            if not csv_path.exists():
                # Try from project root
                project_root = script_dir.parent.parent
                csv_path = project_root / csv_file

    csv_file = str(csv_path)

    # Load and scale the trace data
    raw_data = load_csv_data(csv_file)
    if not raw_data:
        print(f"Error: No valid data in CSV file: {csv_file}")
        sys.exit(1)

    max_index = len(raw_data)
    max_val = max(raw_data)
    min_val = min(raw_data)

    # Normalize and scale: maps [min_val, max_val] -> [shift, shift + amplitude]
    if max_val == min_val:
        # All values are the same, use shift + amplitude/2
        scaled_trace = [int(shift + amplitude / 2)] * max_index
    else:
        scaled_trace = [
            int((v - min_val) / (max_val - min_val) * amplitude + shift)
            for v in raw_data
        ]

    # Set duration
    env_duration = RUN_OPTS.get("run_time")
    if env_duration is not None:
        duration = int(env_duration)
    else:
        # Default: use CSV length (one value per second) for cyclic, or unlimited
        duration = max_index if not fit_trace else max_index

    # Print configuration summary
    print(f"CSV LoadShape initialized:")
    print(f"  - File: {csv_file}")
    print(f"  - Data points: {max_index}")
    print(f"  - User range: {shift} - {shift + amplitude}")
    print(f"  - Duration: {duration}s")
    print(f"  - Mode: {'Fit to duration' if fit_trace else 'Cyclic'}")
    print(f"  - Spawn rate: {spawn_rate}")

