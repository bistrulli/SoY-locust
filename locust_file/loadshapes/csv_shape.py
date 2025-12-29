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
from locust import LoadTestShape

def get_env_var(var_name, default=None, is_numeric=False, is_bool=False):
    """
    Reads an environment variable with optional type conversion.
    Returns default if not set.
    """
    value = os.environ.get(var_name)
    if value is None:
        return default

    if is_bool:
        return value.lower() in ("true", "1", "yes")

    if is_numeric:
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            print(f"Warning: '{var_name}' should be numeric, got '{value}'. Using default: {default}")
            return default

    return value


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
    """
    CSV-based load shape that reproduces a waveform from a CSV file.

    The CSV values are normalized and scaled to the range [shift, shift + amplitude].
    Supports two modes:
    - Cyclic: Repeats the CSV pattern when it ends
    - Fit to duration: Stretches/compresses the CSV to fit the test duration
    """

    # Default configuration (can be overridden by environment variables)
    default_csv_file = "workloads/sin400.csv"  # Relative to locust_file/loadshapes/ or absolute
    default_amplitude = 90      # Max users = shift + amplitude
    default_shift = 10          # Minimum users
    default_duration = None     # None = use CSV length, or specify in seconds
    default_fit_trace = False   # False = cyclic, True = fit to duration
    default_spawn_rate = 100    # Aggressive spawn rate for quick scaling

    def __init__(self):
        super().__init__()

        # Load configuration from environment variables or use defaults
        csv_file = get_env_var("CSV_SHAPE_FILE", self.default_csv_file)
        self.amplitude = get_env_var("CSV_SHAPE_AMPLITUDE", self.default_amplitude, is_numeric=True)
        self.shift = get_env_var("CSV_SHAPE_SHIFT", self.default_shift, is_numeric=True)
        self.fit_trace = get_env_var("CSV_SHAPE_FIT_TRACE", self.default_fit_trace, is_bool=True)
        self.spawn_rate = get_env_var("CSV_SHAPE_SPAWN_RATE", self.default_spawn_rate, is_numeric=True)

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

        self.csv_file = str(csv_path)

        # Load and scale the trace data
        raw_data = load_csv_data(self.csv_file)
        if not raw_data:
            print(f"Error: No valid data in CSV file: {self.csv_file}")
            sys.exit(1)

        self.max_index = len(raw_data)
        max_val = max(raw_data)
        min_val = min(raw_data)

        # Normalize and scale: maps [min_val, max_val] -> [shift, shift + amplitude]
        if max_val == min_val:
            # All values are the same, use shift + amplitude/2
            self.scaled_trace = [int(self.shift + self.amplitude / 2)] * self.max_index
        else:
            self.scaled_trace = [
                int((v - min_val) / (max_val - min_val) * self.amplitude + self.shift)
                for v in raw_data
            ]

        # Set duration
        env_duration = get_env_var("CSV_SHAPE_DURATION", self.default_duration, is_numeric=True)
        if env_duration is not None:
            self.duration = int(env_duration)
        elif self.default_duration is not None:
            self.duration = self.default_duration
        else:
            # Default: use CSV length (one value per second) for cyclic, or unlimited
            self.duration = self.max_index if not self.fit_trace else self.max_index

        # Print configuration summary
        print(f"CSV LoadShape initialized:")
        print(f"  - File: {self.csv_file}")
        print(f"  - Data points: {self.max_index}")
        print(f"  - User range: {self.shift} - {self.shift + self.amplitude}")
        print(f"  - Duration: {self.duration}s")
        print(f"  - Mode: {'Fit to duration' if self.fit_trace else 'Cyclic'}")
        print(f"  - Spawn rate: {self.spawn_rate}")

    def tick(self):
        """
        Returns the current user count and spawn rate based on elapsed time.
        Returns None to end the test when duration is exceeded.
        """
        run_time = self.get_run_time()

        # Check if test duration exceeded
        if run_time > self.duration:
            return None

        # Calculate the index into the trace data
        if self.fit_trace:
            # Fit mode: scale the trace to fit the duration
            if self.duration > 0:
                scaling_ratio = self.max_index / self.duration
                trace_index = int(run_time * scaling_ratio)
            else:
                trace_index = 0
            trace_index = min(trace_index, self.max_index - 1)
        else:
            # Cyclic mode: wrap around when trace ends
            trace_index = int(run_time) % self.max_index

        user_count = max(1, self.scaled_trace[trace_index])  # Ensure at least 1 user

        return (user_count, self.spawn_rate)
