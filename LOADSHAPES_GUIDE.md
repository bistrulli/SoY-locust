# Loadshapes Guide

This guide provides comprehensive documentation for all loadshapes available in the SoY-locust framework. Loadshapes control how the number of virtual users changes over time during a load test.

## Table of Contents

1. [Introduction](#introduction)
2. [Available Loadshapes](#available-loadshapes)
3. [Built-in Loadshapes](#built-in-loadshapes)
4. [CSV-Based Loadshape](#csv-based-loadshape)
5. [Creating Custom Loadshapes](#creating-custom-loadshapes)
6. [Integration with Test Runner](#integration-with-test-runner)

---

## Introduction

### What are Loadshapes?

Loadshapes are Locust classes that define how the number of concurrent virtual users changes over the duration of a load test. Instead of maintaining a fixed number of users, loadshapes allow you to simulate realistic traffic patterns such as:

- Gradual ramp-ups during peak hours
- Cyclical patterns reflecting daily usage
- Sudden spikes to test system resilience
- Real-world traffic traces from production logs

### How Loadshapes Work

Every loadshape extends Locust's `LoadTestShape` class and implements the `tick()` method, which is called approximately once per second. This method returns:

- A tuple `(user_count, spawn_rate)` to continue the test with the specified number of users
- `None` to end the test

```python
from locust import LoadTestShape

class CustomLoadShape(LoadTestShape):
    def tick(self):
        run_time = self.get_run_time()  # Elapsed time in seconds

        if run_time > 300:  # End after 5 minutes
            return None

        user_count = 50
        spawn_rate = 10
        return (user_count, spawn_rate)
```

---

## Available Loadshapes

| Loadshape | File | Pattern | Duration | User Range | Use Case |
|-----------|------|---------|----------|------------|----------|
| **Constant** | `constant_shape.py` | Flat line | 300s | 50 | Baseline performance |
| **Ramp-up** | `rampup_shape.py` | Linear increase | 300s | 0 → 100 | Gradual load increase |
| **Peak** | `peak_shape.py` | Triangle | 300s | 0 → 100 → 1 | Spike testing |
| **Cyclical** | `cyclical_shape.py` | Repeating waves | 1440s | 1 ↔ 100 | Daily patterns |
| **Step** | `step_shape.py` | Staircase | 600s | 20 → 100 → 1 | Threshold testing |
| **CSV** | `csv_shape.py` | From file | Configurable | Configurable | Real-world traces |

All loadshapes are located in: `locust_file/loadshapes/`

---

## Built-in Loadshapes

### 1. Constant Shape (`constant_shape.py`)

Maintains a fixed number of users throughout the test duration. Ideal for baseline performance testing and establishing benchmarks.

**Pattern Visualization:**
```
Users
  50 |████████████████████████████████████████
     |
   0 +----------------------------------------→ Time
     0                                      300s
```

**Configuration:**
| Parameter | Value | Description |
|-----------|-------|-------------|
| `users` | 50 | Fixed number of users |
| `duration` | 300 | Test duration in seconds |

**Example:**
```bash
python run_load_test.py \
    --users 1 --spawn-rate 100 --run-time 5m \
    --host http://localhost:80 \
    --csv results/constant_test \
    --locust-file locust_file/SoyMonoShorterIfLogin_x1.py \
    --loadshape-file locust_file/loadshapes/constant_shape.py
```

---

### 2. Ramp-up Shape (`rampup_shape.py`)

Linearly increases users from 0 to maximum over the test duration. Useful for identifying at what load level performance begins to degrade.

**Pattern Visualization:**
```
Users
 100 |                                    ████
  75 |                              ██████
  50 |                        ██████
  25 |                  ██████
   0 |████████████████████████████████████████→ Time
     0                                      300s
```

**Configuration:**
| Parameter | Value | Description |
|-----------|-------|-------------|
| `max_users` | 100 | Maximum users at end |
| `ramp_duration` | 300 | Time to reach max users |

**Example:**
```bash
python run_load_test.py \
    --users 1 --spawn-rate 100 --run-time 5m \
    --host http://localhost:80 \
    --csv results/rampup_test \
    --locust-file locust_file/SoyMonoShorterIfLogin_x1.py \
    --loadshape-file locust_file/loadshapes/rampup_shape.py
```

---

### 3. Peak Shape (`peak_shape.py`)

Creates a triangular pattern: ramp-up to peak, hold at peak, then ramp-down. Simulates traffic spikes and tests system recovery.

**Pattern Visualization:**
```
Users
 100 |              ████████████
  75 |          ████            ████
  50 |      ████                    ████
  25 |  ████                            ████
   0 |██                                    ██→ Time
     0    120s         180s              300s
     └─ramp─┘└──peak──┘└────ramp down────┘
```

**Configuration:**
| Parameter | Value | Description |
|-----------|-------|-------------|
| `max_users` | 100 | Peak user count |
| `ramp_up_duration` | 120 | Seconds to reach peak |
| `peak_duration` | 60 | Seconds at peak |
| `ramp_down_duration` | 120 | Seconds to decrease |

**Example:**
```bash
python run_load_test.py \
    --users 1 --spawn-rate 100 --run-time 5m \
    --host http://localhost:80 \
    --csv results/peak_test \
    --locust-file locust_file/SoyMonoShorterIfLogin_x1.py \
    --loadshape-file locust_file/loadshapes/peak_shape.py
```

---

### 4. Cyclical Shape (`cyclical_shape.py`)

Repeating pattern with ramp-up, constant load, and pause phases. Simulates recurring traffic patterns like daily usage cycles.

**Pattern Visualization:**
```
Users
 100 |    ████            ████            ████
  50 |  ██    ██        ██    ██        ██
   1 |██        ████████        ████████      → Time
     0   120s        360s        720s      1440s
     └─cycle 1─┘└──cycle 2──┘└──cycle 3──┘└──cycle 4──┘
```

**Each Cycle (360 seconds):**
| Phase | Duration | Users |
|-------|----------|-------|
| Ramp-up | 60s | 0 → 100 |
| Constant | 60s | 100 |
| Pause | 240s | 1 |

**Configuration:**
| Parameter | Value | Description |
|-----------|-------|-------------|
| `max_users` | 100 | Peak users per cycle |
| `ramp_duration` | 60 | Ramp-up time |
| `constant_duration` | 60 | Time at peak |
| `pause_duration` | 240 | Idle time |
| `max_duration` | 1440 | Total test (4 cycles) |

**Example:**
```bash
python run_load_test.py \
    --users 1 --spawn-rate 100 --run-time 24m \
    --host http://localhost:80 \
    --csv results/cyclical_test \
    --locust-file locust_file/SoyMonoShorterIfLogin_x1.py \
    --loadshape-file locust_file/loadshapes/cyclical_shape.py
```

---

### 5. Step Shape (`step_shape.py`)

Increases load in discrete steps, then decreases. Useful for identifying performance thresholds at specific user counts.

**Pattern Visualization:**
```
Users
 100 |                    ████████
  80 |              ██████        ██████
  60 |        ██████                    ██████
  40 |  ██████                                ██████
  20 |██                                            ██
   0 +------------------------------------------------→ Time
     0   60  120  180  240  300  360  420  480  540  600s
```

**Configuration:**
| Parameter | Value | Description |
|-----------|-------|-------------|
| `step_duration` | 60 | Seconds per step |
| `step_users` | 20 | Users added/removed per step |
| `max_users` | 100 | Maximum users |
| `steps_up` | 5 | Number of increasing steps |
| `steps_down` | 5 | Number of decreasing steps |

**Example:**
```bash
python run_load_test.py \
    --users 1 --spawn-rate 100 --run-time 10m \
    --host http://localhost:80 \
    --csv results/step_test \
    --locust-file locust_file/SoyMonoShorterIfLogin_x1.py \
    --loadshape-file locust_file/loadshapes/step_shape.py
```

---

## CSV-Based Loadshape

### Overview

The `csv_shape.py` loadshape reads a waveform from a CSV file, allowing you to reproduce real-world traffic patterns or custom-designed load profiles. This is particularly useful for:

- Replaying production traffic patterns
- Testing with mathematically generated waveforms (sine, sawtooth, etc.)
- Reproducing specific load scenarios from historical data

### CSV File Format

The CSV file should contain a single column of numeric values, one per line, with no header:

```
10
15
23
45
67
89
100
95
...
```

Each value represents the target user count for that second of the test. The values are automatically normalized and scaled to your configured range.

### Available Sample CSV Files

Located in `workloads/`:

| File | Data Points | Duration | Pattern | Description |
|------|-------------|----------|---------|-------------|
| `sin400.csv` | 800 | ~13 min | Sine wave | Smooth periodic load |
| `sin800.csv` | 800 | ~13 min | Sine wave | Longer period sine |
| `twitter.csv` | 3601 | ~60 min | Real trace | Actual Twitter traffic pattern |

### Configuration

Configure via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `CSV_SHAPE_FILE` | `workloads/sin400.csv` | Path to CSV file |
| `CSV_SHAPE_AMPLITUDE` | `90` | User range (max - min users) |
| `CSV_SHAPE_SHIFT` | `10` | Baseline (minimum) users |
| `CSV_SHAPE_DURATION` | CSV length | Total test duration in seconds |
| `CSV_SHAPE_FIT_TRACE` | `false` | `true` = fit to duration, `false` = cyclic |
| `CSV_SHAPE_SPAWN_RATE` | `100` | Spawn rate for scaling |

### Scaling Formula

CSV values are normalized and scaled using:

```
user_count = ((csv_value - csv_min) / (csv_max - csv_min)) * amplitude + shift
```

**Example:** With `amplitude=90` and `shift=10`:
- CSV minimum value → 10 users
- CSV maximum value → 100 users (10 + 90)

### Operating Modes

#### Cyclic Mode (default)

When `CSV_SHAPE_FIT_TRACE=false`, the CSV pattern repeats cyclically:

```
CSV Data: [10, 50, 100, 50, 10]  (5 points)
Test Duration: 15 seconds

Second 0-4:   [10, 50, 100, 50, 10]  ← First cycle
Second 5-9:   [10, 50, 100, 50, 10]  ← Second cycle
Second 10-14: [10, 50, 100, 50, 10]  ← Third cycle
```

#### Fit-to-Duration Mode

When `CSV_SHAPE_FIT_TRACE=true`, the CSV is stretched or compressed to match the test duration:

```
CSV Data: [10, 50, 100, 50, 10]  (5 points)
Test Duration: 10 seconds

The 5 CSV points are stretched across 10 seconds:
Second 0-1: 10 users
Second 2-3: 50 users
Second 4-5: 100 users
Second 6-7: 50 users
Second 8-9: 10 users
```

### Usage Examples

#### Basic Usage (Default Settings)

Uses `sin400.csv` with 10-100 user range in cyclic mode:

```bash
python run_load_test.py \
    --users 1 --spawn-rate 100 --run-time 15m \
    --host http://localhost:80 \
    --csv results/csv_test \
    --locust-file locust_file/SoyMonoShorterIfLogin_x1.py \
    --loadshape-file locust_file/loadshapes/csv_shape.py
```

#### Twitter Trace Replay

Reproduce real Twitter traffic pattern:

```bash
CSV_SHAPE_FILE=workloads/twitter.csv \
CSV_SHAPE_AMPLITUDE=150 \
CSV_SHAPE_SHIFT=20 \
CSV_SHAPE_DURATION=3600 \
python run_load_test.py \
    --users 1 --spawn-rate 100 --run-time 60m \
    --host http://localhost:80 \
    --csv results/twitter_replay \
    --locust-file locust_file/SoyMonoShorterIfLogin_x1.py \
    --loadshape-file locust_file/loadshapes/csv_shape.py
```

This configures:
- User range: 20-170 users (shift=20, amplitude=150)
- Duration: 3600 seconds (1 hour)
- Pattern: Real Twitter traffic trace

#### Fit CSV to Custom Duration

Stretch a short CSV to match a longer test:

```bash
CSV_SHAPE_FILE=workloads/sin400.csv \
CSV_SHAPE_FIT_TRACE=true \
CSV_SHAPE_DURATION=1800 \
CSV_SHAPE_AMPLITUDE=200 \
CSV_SHAPE_SHIFT=50 \
python run_load_test.py \
    --users 1 --spawn-rate 100 --run-time 30m \
    --host http://localhost:80 \
    --csv results/fitted_sine \
    --locust-file locust_file/SoyMonoShorterIfLogin_x1.py \
    --loadshape-file locust_file/loadshapes/csv_shape.py
```

This configures:
- User range: 50-250 users
- Duration: 1800 seconds (30 minutes)
- Mode: Fit-to-duration (stretches 800 CSV points to 1800 seconds)

### Creating Custom CSV Waveforms

#### Manual Creation

Create a text file with one numeric value per line:

```bash
# Generate a simple ramp pattern
seq 10 100 > workloads/custom_ramp.csv

# Generate repeated values
yes 50 | head -n 300 > workloads/constant_50.csv
```

#### Python Generation

```python
import numpy as np

# Generate sine wave
t = np.linspace(0, 4*np.pi, 800)
values = 50 + 40 * np.sin(t)
np.savetxt('workloads/custom_sine.csv', values.astype(int), fmt='%d')

# Generate sawtooth wave
t = np.linspace(0, 1, 600)
values = 10 + 90 * (t % 0.2) / 0.2
np.savetxt('workloads/sawtooth.csv', values.astype(int), fmt='%d')

# Generate random walk
import random
values = [50]
for _ in range(599):
    change = random.randint(-5, 5)
    values.append(max(10, min(100, values[-1] + change)))
np.savetxt('workloads/random_walk.csv', values, fmt='%d')
```

#### From Production Logs

Extract user counts from production metrics:

```bash
# Example: Extract from Prometheus query result
curl -s 'http://prometheus:9090/api/v1/query_range?query=active_users&start=2024-01-01T00:00:00Z&end=2024-01-01T01:00:00Z&step=1s' \
  | jq -r '.data.result[0].values[][1]' > workloads/production_trace.csv
```

---

## Creating Custom Loadshapes

### Template

```python
from locust import LoadTestShape

class CustomLoadShape(LoadTestShape):
    """
    Brief description of this loadshape.
    """

    # Configuration parameters
    duration = 300      # Total test duration in seconds
    max_users = 100     # Maximum concurrent users

    def tick(self):
        """
        Called approximately once per second.

        Returns:
            tuple: (user_count, spawn_rate) to continue
            None: to end the test
        """
        run_time = self.get_run_time()

        # End condition
        if run_time > self.duration:
            return None

        # Calculate current user count based on elapsed time
        current_users = self._calculate_users(run_time)
        spawn_rate = 10  # Users per second when scaling

        return (current_users, spawn_rate)

    def _calculate_users(self, run_time):
        """Custom logic to determine user count."""
        # Your implementation here
        return self.max_users
```

### Best Practices

1. **Always handle test termination**: Return `None` when the test should end
2. **Use meaningful spawn rates**: Higher rates (50-100) for quick scaling, lower (1-10) for gradual changes
3. **Ensure minimum users**: Use `max(1, user_count)` to prevent zero users
4. **Document parameters**: Include docstrings explaining configuration options
5. **Keep calculations simple**: Complex math in `tick()` can affect timing accuracy

### The `tick()` Method Contract

| Return Value | Meaning |
|--------------|---------|
| `(user_count, spawn_rate)` | Continue test with specified users |
| `None` | End the test immediately |

**Important:** The spawn rate controls how quickly Locust adds or removes users to reach the target count. A rate of 100 means Locust will add/remove up to 100 users per second.

---

## Integration with Test Runner

### Single Test Execution

The loadshape file is passed via the `--loadshape-file` parameter:

```bash
python run_load_test.py \
    --users 1 \
    --spawn-rate 100 \
    --run-time 5m \
    --host http://localhost:80 \
    --csv results/test \
    --locust-file locust_file/SoyMonoShorterIfLogin_x1.py \
    --loadshape-file locust_file/loadshapes/cyclical_shape.py
```

**Note:** The `--users` and `--spawn-rate` parameters are initial values; the loadshape takes control once the test starts.

### Batch Testing

Run multiple locust files with the same loadshape:

```bash
./run_locust_files.sh locust_file/loadshapes/csv_shape.py
```

This iterates through all `SoyMonoShorterIfLogin_*.py` files, running each with the specified loadshape.

### How It Works Internally

The test runner constructs a Locust command combining both files:

```bash
locust --headless \
    -f "locust_file/SoyMonoShorterIfLogin_x1.py,locust_file/loadshapes/csv_shape.py" \
    --host http://localhost:80 \
    ...
```

Locust loads both files, using:
- The test file for user behavior (`SoyMonoShorterIfLogin_x1.py` defines what users do)
- The loadshape file for user count control (`csv_shape.py` defines how many users)

---

## Quick Reference

### Environment Variables for CSV Shape

```bash
export CSV_SHAPE_FILE=workloads/twitter.csv
export CSV_SHAPE_AMPLITUDE=90
export CSV_SHAPE_SHIFT=10
export CSV_SHAPE_DURATION=3600
export CSV_SHAPE_FIT_TRACE=false
export CSV_SHAPE_SPAWN_RATE=100
```

### Common Commands

```bash
# Constant load test
python run_load_test.py --loadshape-file locust_file/loadshapes/constant_shape.py ...

# Ramp-up test
python run_load_test.py --loadshape-file locust_file/loadshapes/rampup_shape.py ...

# CSV-based with Twitter trace
CSV_SHAPE_FILE=workloads/twitter.csv \
python run_load_test.py --loadshape-file locust_file/loadshapes/csv_shape.py ...

# Batch testing
./run_locust_files.sh locust_file/loadshapes/cyclical_shape.py
```

### File Locations

```
locust_file/loadshapes/
├── constant_shape.py   # Fixed user count
├── rampup_shape.py     # Linear increase
├── peak_shape.py       # Triangle pattern
├── cyclical_shape.py   # Repeating cycles
├── step_shape.py       # Discrete steps
└── csv_shape.py        # CSV-based waveform

workloads/
├── sin400.csv          # Sine wave (800 points)
├── sin800.csv          # Sine wave (800 points)
└── twitter.csv         # Real Twitter trace (3601 points)
```
