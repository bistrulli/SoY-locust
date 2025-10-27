# Guide to Using the Microservices Version (v5)

This guide describes the transition from a monolithic architecture to a microservices-based one managed with Docker Swarm, with a focus on configuring load tests and the automatic replica control system using Locust.

## 1. System Architecture (`monotloth-v5.yml`)

The `monotloth-v5.yml` file is the heart of the new architecture. It defines the services, their relationships, resources, and networks using Docker Swarm.

- **Main Services**: The application is now divided into three main services:
    - `gateway`: The entry point (API Gateway) that routes requests to the appropriate microservices.
    - `ms-exercise`: The microservice that handles the "exercise" logic.
    - `ms-other`: Another microservice for distinct functionalities.

- **Supporting Infrastructure**:
    - **Nginx Proxy**: Each service (`gateway`, `ms-exercise`, `ms-other`) has its own Nginx proxy (`gateway-nginx`, `ms-exercise-nginx`, etc.). This allows for more granular traffic monitoring and management.
    - **Monitoring**: `prometheus` and `cadvisor` are included to collect metrics on the performance and resource usage of the containers.
    - **Database**: A centralized `postgres` service.

- **Deployment**: The `deploy` section of each service defines how Docker Swarm should manage it (initial number of replicas, update and restart policies, CPU/memory limits). The initial replicas are set to `1`, as their scaling will be dynamically managed by the `ControlLoop` in Locust.

## 2. Control and Testing Logic (`SoyMonoShorterIfLogin_x6.py`)

The Locust file has been adapted to handle the new architecture. The fundamental change is that **there is no longer a single controller, but one controller for each microservice** that you want to scale independently.

**Key Concept**: Each microservice is an independent resource with its own performance requirements. Therefore, it is necessary to configure, start, and monitor a separate `ControlLoop` for each one.

## 3. How to Configure a New Locust Test for Microservices

Follow these steps to create or adapt a Locust test file.

### Step 1: Define the Controller Configuration for Each Microservice

For each service you want to control (e.g., `ms-exercise`, `ms-other`, `gateway`), you must create a configuration dictionary similar to `ms_exercise_conf`.

```python
# Example for the 'ms-exercise' service
ms_exercise_conf = {
    # Service name in the docker-compose file (monotloth-v5.yml)
    "service_name": "ms-exercise",
    # Name of the Docker Swarm stack
    "stack_name": "ms-stack-v5",
    # Path to the system definition file
    "sysfile": cwd.parent/"sou"/"monotloth-v5.yml",
    # Controller parameters
    "control_widow": 60,
    "estimation_window": 60,
    "measurament_period": "1s",
    # Output file for the results specific to this service
    "outfile": cwd.parent/"results"/f"{Path(__file__).stem}"/f"{Path(__file__).stem}_ms-exercise.csv",
    # Number of replicas at startup
    "init_repica": 6,
    # Target CPU utilization for the service
    "target_utilization": 0.2,
    # Prometheus configuration
    "disable_prometheus": False,
    "prometheus": {
        "host": "127.0.0.1",
        "port": 9090
    },
    # Optional: to control a remote Docker daemon
    "remote": None,
    "remote_docker_port": None
}

# Do the same for the other services
ms_other_conf = { ... }
gateway_conf = { ... }
```

**Important Parameters:**
- `service_name`: Must exactly match the service name in the `monotloth-v5.yml` file.
- `stack_name`: The name you will give your stack when you deploy it with `docker stack deploy`.
- `outfile`: It is crucial to use different output paths for each controller to prevent result files from overwriting each other.
- `target_utilization`: The CPU utilization target that the controller will try to maintain for that specific service by scaling its replicas accordingly.

### Step 2: Instantiate the Controllers

Create a `ControlLoop` instance for each configuration dictionary.

```python
ctrlLoop_ms_exercise = ControlLoop(config=ms_exercise_conf)
ctrlLoop_ms_other = ControlLoop(config=ms_other_conf)
ctrlLoop_gateway = ControlLoop(config=gateway_conf)
```

### Step 3: Start and Stop the Controllers

Use Locust's events to manage the lifecycle of your controllers. Make sure to start and stop **all** the loops you have created.

```python
@events.test_start.add_listener
def on_locust_start(environment, **_kwargs):
    # Start each control loop in a separate greenlet
    if not isinstance(environment.runner, WorkerRunner):
        gevent.spawn(ctrlLoop_ms_exercise.loop, environment)
        gevent.spawn(ctrlLoop_ms_other.loop, environment)
        gevent.spawn(ctrlLoop_gateway.loop, environment)

@events.test_stop.add_listener
def on_locust_stop(environment, **_kwargs):
    # Save the results for each control loop
    global ctrlLoop_ms_exercise, ctrlLoop_ms_other, ctrlLoop_gateway
    ctrlLoop_ms_exercise.saveResults()
    ctrlLoop_ms_other.saveResults()
    ctrlLoop_gateway.saveResults()
```

## 4. Operational Workflow

1.  **Deploy the Stack**: Before starting the test, deploy the entire architecture to Docker Swarm.
    ```bash
    docker stack deploy -c sou/monotloth-v5.yml ms-stack-v5
    ```
    *(Use `ms-stack-v5` as the stack name for consistency with the controller configurations).*

2.  **Run the Test**: Start Locust as usual, pointing to the Python file you have configured.
    ```bash
    locust -f locust_file/SoyMonoShorterIfLogin_x6.py --headless -u <users> -r <spawn-rate>
    ```

3.  **Analyze the Results**: At the end of the test, you will find the output CSV files for each controlled microservice in the `results/` folder, under the sub-path specified by the `outfile` parameter of each configuration. For example:
    - `results/SoyMonoShorterIfLogin_x6/SoyMonoShorterIfLogin_x6_ms-exercise.csv`
    - `results/SoyMonoShorterIfLogin_x6/SoyMonoShorterIfLogin_x6_ms-other.csv`
    - `results/SoyMonoShorterIfLogin_x6/SoyMonoShorterIfLogin_x6_gateway.csv`
