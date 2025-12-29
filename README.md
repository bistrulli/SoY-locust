# SoY-locust: Advanced Load Testing Framework with Traefik Integration

This repository contains a comprehensive load testing framework designed to evaluate the performance of web applications using Locust, Docker Swarm, Traefik reverse proxy, and advanced monitoring capabilities. The framework provides detailed application metrics collection without requiring modifications to the target microservices.

## 🚀 Project Overview

The framework consists of several key components:
- **Load testing scripts** using Locust with custom load shapes
- **Docker Swarm integration** for scalable deployment
- **Traefik reverse proxy** for traffic management and metrics collection
- **Prometheus monitoring stack** with comprehensive metrics collection
- **Automated test execution** and results collection
- **Advanced performance monitoring** and analysis tools

## 🏗️ Architecture

The system uses a modern microservices architecture with the following components:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│     Locust      │    │     Traefik     │    │   Application   │
│  Load Testing   │───▶│  Reverse Proxy  │───▶│  Microservices  │
│    (Port 9646)  │    │   (Port 80/8080)│    │   (Internal)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │   Prometheus    │
                       │   Monitoring    │
                       │   (Port 9090)   │
                       └─────────────────┘
```

## 📂 Repository Structure

```
.
├── run_load_test.py              # Main script for running individual load tests
├── run_locust_files.sh           # Shell script for batch testing
├── locust_file/                  # Directory containing Locust test files
│   └── loadshapes/              # Custom load shape definitions (see [LOADSHAPES_GUIDE.md](LOADSHAPES_GUIDE.md))
├── workloads/                    # CSV waveform files for csv_shape.py
├── sou/                         # Docker Swarm configuration files
│   └── monotloth-v5.yml        # Main Docker Swarm stack configuration (with Traefik)
├── prometheus/                  # Prometheus configuration
│   └── prometheus.yml          # Prometheus scraping configuration
├── estimator/                   # Monitoring and analysis tools
│   └── monitoring.py           # Enhanced monitoring class with Traefik metrics
└── results/                    # Directory for test results
```

## 🔧 Prerequisites

- Python 3.x
- Docker and Docker Swarm
- Locust (`pip install locust`)
- Required Python packages (see requirements.txt)

## 🌐 Service Endpoints

After deploying the stack, the following services are available:

| Service | URL | Description |
|---------|-----|-------------|
| **Application** | `http://localhost:80` | Main application endpoint (via Traefik) |
| **Traefik Dashboard** | `http://localhost:8080` | Traefik management interface |
| **Prometheus** | `http://localhost:9090` | Metrics collection and querying |
| **Locust Web UI** | `http://localhost:8089` | Load testing interface (when running) |
| **Node Exporter** | `http://localhost:9100` | System metrics |
| **cAdvisor** | `http://localhost:8081` | Container metrics |

## 🎯 Running Experiments

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

**Parameters:**
- `--users`: Number of concurrent users
- `--spawn-rate`: Rate at which users are spawned
- `--run-time`: Duration of the test (e.g., "3m" for 3 minutes)
- `--host`: Target URL to test (**Now: `http://localhost:80`**)
- `--csv`: Path for storing test results
- `--locust-file`: Path to the Locust test file
- `--loadshape-file`: Path to the load shape definition file

### Batch Testing

To run multiple tests with different configurations:

```bash
./run_locust_files.sh <path_to_loadshape_file>
```

Example:
```bash
./run_locust_files.sh locust_file/loadshapes/cyclical_shape.py
```

### Available Loadshapes

The framework includes 6 loadshapes for different testing scenarios:

| Loadshape | Pattern | Description |
|-----------|---------|-------------|
| `constant_shape.py` | Flat | Fixed 50 users for 5 minutes |
| `rampup_shape.py` | Linear | 0 → 100 users over 5 minutes |
| `peak_shape.py` | Triangle | Ramp up, hold peak, ramp down |
| `cyclical_shape.py` | Waves | Repeating load cycles |
| `step_shape.py` | Stairs | Discrete step increases/decreases |
| `csv_shape.py` | Custom | Load pattern from CSV file |

**CSV-Based Loadshape:** Reproduce real-world traffic patterns from CSV files:
```bash
CSV_SHAPE_FILE=workloads/twitter.csv \
python run_load_test.py \
    --loadshape-file locust_file/loadshapes/csv_shape.py ...
```

For detailed documentation, see **[LOADSHAPES_GUIDE.md](LOADSHAPES_GUIDE.md)**.

## 📊 Enhanced Metrics Collection

The framework now collects comprehensive metrics through multiple sources:

### Traefik Metrics (NEW)
- **Incoming Requests Rate**: Total requests/second through Traefik
- **Completed Requests Rate**: Successful requests/second (2xx, 3xx status codes)
- **Failed Requests Rate**: Failed requests/second (4xx, 5xx status codes)
- **Response Time**: Average response time via Traefik
- **Service-specific Metrics**: Per-service breakdown of all above metrics

### System Metrics
- **CPU Utilization**: Service and system-level CPU usage
- **Memory Usage**: Container and system memory consumption
- **Container Metrics**: Detailed container resource usage via cAdvisor
- **System Metrics**: Host-level metrics via Node Exporter

### Application Metrics
- **Active Users**: Current number of active Locust users
- **Throughput**: Application-level request rate
- **Response Time**: Application-perceived latency
- **Replica Status**: Running and ready replica counts

## 📈 Monitoring Integration

The `estimator/monitoring.py` class has been enhanced with new methods:

```python
# New Traefik metric methods
monitor.getIncomingRequestsFromTraefik()     # Total incoming requests/sec
monitor.getCompletedRequestsFromTraefik()    # Successful requests/sec
monitor.getFailedRequestsFromTraefik()       # Failed requests/sec
monitor.getResponseTimeFromTraefik()         # Average response time
monitor.getRequestsByService(service_name)   # Service-specific metrics
```

All metrics are automatically collected during test execution and saved to CSV files for analysis.

## 💻 Example: Running a Complete Load Test

Here's a practical example using the new Traefik-enabled setup:

```bash
python run_load_test.py \
    --users 100 \
    --spawn-rate 10 \
    --run-time 5m \
    --host http://localhost:80 \
    --csv results/traefik_test_run \
    --locust-file locust_file/SoyMonoShorterIfLogin_x1.py \
    --loadshape-file locust_file/loadshapes/cyclical_shape.py
```

This command will:
1. **Deploy the stack** using `sou/monotloth-v5.yml` (includes Traefik, Prometheus, monitoring)
2. **Launch Locust** with 100 concurrent users targeting `http://localhost:80`
3. **Route traffic** through Traefik reverse proxy for enhanced metrics collection
4. **Collect comprehensive metrics** including Traefik, system, and application metrics
5. **Run for 5 minutes** with cyclical load pattern
6. **Save enhanced results** with all new metric columns to CSV

### What's Different with Traefik Integration

- ✅ **No application modifications** required for metrics collection
- ✅ **Enhanced visibility** into request patterns and response times
- ✅ **Service-level metrics** for microservices monitoring
- ✅ **Centralized traffic management** with load balancing capabilities
- ✅ **Real-time monitoring** via Traefik dashboard

## 📋 Results and Analysis

Test results are stored in the `results/` directory with enhanced data:

### CSV Output Columns
- **Traditional metrics**: cores, rts, tr, users, replica, ready_replica, util, mem
- **New Traefik metrics**: traefik_incoming, traefik_completed, traefik_failed, traefik_response_time

### Monitoring Dashboards
- **Traefik Dashboard** (`http://localhost:8080`): Real-time traffic and service status
- **Prometheus** (`http://localhost:9090`): Query and analyze all collected metrics
- **Locust Web UI** (`http://localhost:8089`): Load testing progress and statistics

## ⚠️ Important Changes from Previous Versions

### 🔄 Port Changes
- **Application endpoint**: `http://localhost:5001` → `http://localhost:80`
- **New Traefik dashboard**: `http://localhost:8080`
- **Prometheus remains**: `http://localhost:9090`

### 📁 Configuration Updates
- **Stack configuration**: Now using `sou/monotloth-v5.yml` (includes Traefik setup)
- **Prometheus config**: Updated with Traefik metrics collection
- **Monitoring class**: Enhanced with Traefik metric methods

### 🔧 Client Configuration
**Important**: Update all Locust scripts and client configurations to use port `80` instead of `5001`:

```python
# Old configuration
host = "http://localhost:5001"

# New configuration
host = "http://localhost:80"
```

## 🚦 Getting Started Quickly

1. **Update your test configurations** to use `http://localhost:80`
2. **Deploy the stack** - the framework automatically uses the new Traefik-enabled configuration
3. **Access the Traefik dashboard** at `http://localhost:8080` to monitor traffic in real-time
4. **Run your tests** as usual - enhanced metrics are collected automatically
5. **Analyze results** using the additional Traefik metrics in your CSV output

## 📝 Notes

- The framework uses **Traefik v2.10** as reverse proxy for enhanced metrics collection
- **Docker Swarm** is required for deployment and service management
- Tests remain **non-destructive** and can be safely interrupted with Ctrl+C
- Each test run creates a **separate results directory** to prevent data overwriting
- **Automatic service discovery** is handled by Traefik for seamless scaling
- **Health checks and load balancing** are automatically configured through Traefik

## 🔍 Troubleshooting

### Common Issues
- **Port conflicts**: Ensure ports 80, 8080, 9090 are available
- **Docker Swarm**: Verify swarm mode is initialized (`docker swarm init`)
- **Service discovery**: Check Traefik dashboard for service registration
- **Metrics collection**: Verify Prometheus targets are healthy at `http://localhost:9090/targets`

### Service Health Checks
- **Traefik**: `http://localhost:8080` should show the dashboard
- **Prometheus**: `http://localhost:9090/targets` should show all targets as "UP"
- **Application**: `http://localhost:80` should serve the application

The enhanced framework provides comprehensive insights into application performance while maintaining the simplicity and reliability of the original load testing capabilities.