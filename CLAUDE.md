# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SoY-locust is an advanced load testing framework that integrates Locust with Docker Swarm, Traefik reverse proxy, and comprehensive monitoring capabilities. The framework provides detailed application metrics collection without requiring modifications to target microservices.

## Development Commands

### Running Load Tests

**Single test execution:**
```bash
python run_load_test.py \
    --users <number_of_users> \
    --spawn-rate <spawn_rate> \
    --run-time <duration> \
    --host http://localhost:80 \
    --csv <output_csv_path> \
    --locust-file <locust_test_file> \
    --loadshape-file <loadshape_file>
```

**Batch testing:**
```bash
./run_locust_files.sh <path_to_loadshape_file>
# Example: ./run_locust_files.sh locust_file/loadshapes/cyclical_shape.py
```

### Docker Swarm Management

The framework automatically manages Docker Swarm deployment through `run_load_test.py`:
- `initSys()`: Initializes Docker Swarm
- `startSys()`: Deploys the stack using configuration from locust file
- `stopSys()`: Removes the stack after testing

### Dependencies and Setup

**Python dependencies:**
```bash
pip install -r requirements.txt
```

Key dependencies include:
- locust (load testing)
- prometheus-api-client (metrics collection)
- docker (container management)
- scipy, numpy (scientific computing)
- casadi, pyomo, pyscipopt (optimization)

**System requirements:**
- Docker and Docker Swarm (must be initialized: `docker swarm init`)
- Python 3.x
- Available ports: 80, 8080, 9090, 8081, 9100, 9646

## Architecture

### Core Components

1. **Load Testing Engine** (`locust_file/`)
   - Base class: `BaseExp` (abstract HttpUser class)
   - Test scenarios: `SoyMonoShorterIfLogin_*.py` files
   - Load shapes: `locust_file/loadshapes/` directory

2. **Control System** (`controller/`)
   - `ControlLoop`: Main control loop implementation
   - `OPTCTRL`: Optimization-based controller
   - Uses model predictive control for resource scaling

3. **Monitoring System** (`estimator/`)
   - `Monitoring`: Metrics collection from Prometheus, Docker, and Traefik
   - `QNEstimaator`: Queue network estimation
   - Collects system, application, and Traefik metrics

4. **Configuration** (`config/`)
   - `config.py`: Global configuration
   - Logging configuration with colored output support

### Docker Stack Architecture

The system uses `sou/monotloth-v5.yml` which includes:
- **Traefik**: Reverse proxy and load balancer (ports 80, 8080)
- **Gateway**: Main application gateway
- **Microservices**: ms-exercise, ms-other
- **Monitoring**: Prometheus (9090), cAdvisor (8081), Node Exporter (9100)
- **Database**: PostgreSQL

### Metrics Collection

The framework collects comprehensive metrics:

**Traefik Metrics:**
- Incoming request rate
- Completed/failed request rates
- Response times
- Service-specific breakdowns

**System Metrics:**
- CPU utilization per service
- Memory usage
- Container resource consumption
- Docker service replica counts

**Application Metrics:**
- Active user count (via Prometheus gauge)
- Throughput measurements
- Response time distributions

## Configuration System

### Dynamic Configuration Loading

Locust test files contain embedded configuration:
```python
# Configuration extracted via regex from locust files:
"stack_name": "ms-stack-v5"  # Docker stack name
"sysfile": "monotloth-v5.yml"  # Stack configuration file
```

### Service Configuration

The monitoring system automatically constructs service names:
- Full service name: `{stack_name}_{service_name}`
- Default service: `node` (configurable in `config.py`)

### Prometheus Integration

- Default endpoint: `http://localhost:9090`
- Scrape interval: 1 second
- Targets: Locust (9646), Traefik (8080), cAdvisor (8080)

## Control System

### Adaptive Scaling

The control loop implements:
1. **Measurement**: Collects metrics every control period
2. **Estimation**: Uses queue network models for performance prediction
3. **Control**: Applies optimization-based scaling decisions
4. **Actuation**: Scales Docker services with cooldown logic

### Control Parameters

Key configuration parameters:
- `prediction_horizon`: Future prediction window
- `control_widow`: Control action frequency
- `estimation_window`: Historical data window
- `target_utilization`: Target CPU utilization
- `stealth`: Read-only mode flag

### Scaling Logic

- **Upscaling**: Immediate response for performance
- **Downscaling**: Cautious approach using maximum of recent suggestions
- **Cooldown**: Prevents oscillatory scaling behavior

## File Structure Conventions

### Test Files
- Pattern: `SoyMonoShorterIfLogin_*.py`
- Replica configuration encoded in filename (e.g., `_x4` for 4 replicas)
- Must inherit from `BaseExp` and implement `userLogic()`

### Load Shapes
- Location: `locust_file/loadshapes/`
- Standard shapes: constant, cyclical, peak, rampup, step
- Define user spawn patterns over time

### Results Storage
- Primary: `results/` directory
- Runtime data: `runtime_data/`
- Timestamped subdirectories prevent data overwriting

## Important Service Endpoints

After stack deployment:
- Application: `http://localhost:80` (via Traefik)
- Traefik Dashboard: `http://localhost:8080`
- Prometheus: `http://localhost:9090`
- Locust Web UI: `http://localhost:8089` (when running)
- Node Exporter: `http://localhost:9100`
- cAdvisor: `http://localhost:8081`

## Testing and Development

### Running Tests
No explicit test framework is configured. The system is primarily tested through load test execution and validation of the Docker stack deployment.

### Development Workflow
1. Modify locust test files or load shapes
2. Run single tests for validation using `run_load_test.py`
3. Use batch testing for comprehensive evaluation with `run_locust_files.sh`
4. Monitor results through Prometheus and Traefik dashboards
5. Analyze CSV outputs for performance insights

### Debugging and Monitoring
- Enhanced logging with colored output (configurable via `SOY_LOG_LEVEL` and `SOY_NO_COLORS`)
- Real-time monitoring via Prometheus at `http://localhost:9090`
- Traefik dashboard for traffic visualization at `http://localhost:8080`
- Service health checks through Docker Swarm
- Detailed CSV output for post-analysis in `results/` and `runtime_data/`

### Common Development Tasks

**Creating new test scenarios:**
- Extend `BaseExp` class in `locust_file/base_exp.py`
- Follow naming convention: `SoyMonoShorterIfLogin_*.py`
- Include embedded configuration for stack_name and sysfile

**Modifying load patterns:**
- Edit files in `locust_file/loadshapes/`
- Available shapes: constant, cyclical, peak, rampup, step

**Scaling configuration:**
- Modify replica counts in Docker stack files (`sou/monotloth-v5.yml`)
- Update service configuration in locust test files

## Environment Variables

- `SOY_LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)
- `SOY_NO_COLORS`: Disable colored logging output ('1', 'true', 'yes')

## Important Notes for Development

### Port Migration
The system has migrated from direct application endpoints to Traefik routing:
- **Old**: `http://localhost:5001`
- **New**: `http://localhost:80`

Update all test configurations to use port 80 for proper Traefik integration.

### Common Issues and Solutions

**Docker Swarm not initialized:**
```bash
docker swarm init
```

**Port conflicts:**
Ensure ports 80, 8080, 9090, 8081, 9100, 9646 are available before starting tests.

**Service discovery issues:**
Check Traefik dashboard at `http://localhost:8080` to verify service registration.

**Metrics collection problems:**
Verify Prometheus targets are healthy at `http://localhost:9090/targets`.

### Code Structure Notes

**Control System Integration:**
- Control loop runs automatically during load tests when enabled
- Uses model predictive control for adaptive resource scaling
- Integrates with Docker API for service replica management

**Monitoring Architecture:**
- Prometheus metrics collected from multiple sources (Locust port 9646, Traefik port 8080, cAdvisor port 8080)
- Enhanced monitoring class provides Traefik-specific methods
- CSV output includes both traditional and Traefik metrics