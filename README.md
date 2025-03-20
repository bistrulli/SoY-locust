# SoY-locust: Load Testing Framework

This repository contains a load testing framework designed to evaluate the performance of web applications using Locust, Docker Swarm, and custom load shape definitions. The framework is particularly focused on testing applications with different scaling configurations and load patterns.

## Project Overview

The framework consists of several key components:
- Load testing scripts using Locust
- Docker Swarm integration for deployment
- Custom load shape definitions for different testing scenarios
- Automated test execution and results collection
- Performance monitoring and analysis tools

## Repository Structure

```
.
├── run_load_test.py          # Main script for running individual load tests
├── run_locust_files.sh       # Shell script for batch testing
├── locust_file/             # Directory containing Locust test files
│   └── loadshapes/         # Custom load shape definitions
├── sou/                     # Docker Swarm configuration files
│   └── monotloth-v4.yml    # Main Docker Swarm stack configuration
└── results/                # Directory for test results
```

## Prerequisites

- Python 3.x
- Docker and Docker Swarm
- Locust (`pip install locust`)
- Required Python packages (see requirements.txt)

## Running Experiments

### Single Test Execution

To run a single load test, use the `run_load_test.py` script:

```bash
python run_load_test.py \
    --users <number_of_users> \
    --spawn-rate <spawn_rate> \
    --run-time <duration> \
    --host <target_url> \
    --csv <output_csv_path> \
    --locust-file <locust_test_file> \
    --loadshape-file <loadshape_file>
```

Parameters:
- `--users`: Number of concurrent users
- `--spawn-rate`: Rate at which users are spawned
- `--run-time`: Duration of the test (e.g., "3m" for 3 minutes)
- `--host`: Target URL to test
- `--csv`: Path for storing test results
- `--locust-file`: Path to the Locust test file
- `--loadshape-file`: Path to the load shape definition file

### Batch Testing

To run multiple tests with different configurations, use the `run_locust_files.sh` script:

```bash
./run_locust_files.sh <path_to_loadshape_file>
```

Example:
```bash
./run_locust_files.sh locust_file/loadshapes/cyclical_shape.py
```

This script will:
1. Automatically detect and run all test files matching the pattern `SoyMonoShorterIfLogin*.py`
2. Create separate result directories for each test
3. Update the Docker Swarm configuration based on the test requirements
4. Execute the tests sequentially
5. Store results and logs in the `results/` directory

## Results

Test results are stored in the `results/` directory, organized by test name. Each test directory contains:
- CSV files with detailed metrics
- Log files with execution information
- Performance data for analysis

## Notes

- The framework uses Docker Swarm for deployment, so ensure your Docker environment is properly configured
- Tests are designed to be non-destructive and can be safely interrupted using Ctrl+C
- Each test run creates a new results directory to prevent overwriting previous results

## Example: Running a Single Load Test

Here's a practical example of how to run a load test using `run_load_test.py`:

```bash
python run_load_test.py \
    --users 100 \
    --spawn-rate 10 \
    --run-time 5m \
    --host http://localhost:5001 \
    --csv results/test_run \
    --locust-file locust_file/SoyMonoShorterIfLogin_x1.py \
    --loadshape-file locust_file/loadshapes/cyclical_shape.py
```

This command will:
1. Start a Docker Swarm stack using the configuration in `sou/monotloth-v4.yml`
2. Launch Locust with 100 concurrent users
3. Spawn users at a rate of 10 users per second
4. Run the test for 5 minutes
5. Target the application at `http://localhost:5001`
6. Save results to the `results/test_run` directory
7. Use the test scenario defined in `SoyMonoShorterIfLogin_x1.py`
8. Apply the load pattern defined in `cyclical_shape.py`

The test will automatically:
- Deploy the necessary Docker services
- Execute the load test
- Collect performance metrics
- Clean up resources when finished

You can monitor the test progress in real-time through the logs, and the final results will be available in the specified CSV file.