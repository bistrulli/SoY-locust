# SoY-locust: Envoy Integration Architecture

## Overview

SoY-locust has been extended with an advanced architecture that integrates Envoy proxies to provide detailed metrics at both system level (via cAdvisor) and application level (via Envoy). This configuration enables comprehensive microservices performance monitoring during load testing.

## Architecture

### Core Components

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│     Locust      │───▶│  gateway-envoy  │───▶│     gateway     │───▶│  ms-exercise    │
│  Load Testing   │    │  (Port 9901)    │    │   (Port 8080)   │    │  (Port 5001)    │
│  (Port 80)      │    │                 │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘
                                │                                              │
                                │                                              ▼
                                │                                    ┌─────────────────┐
                                │                                    │ms-exercise-envoy│
                                │                                    │  (Port 9901)    │
                                │                                    └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │   Prometheus    │
                       │   (Port 9090)   │
                       │                 │
                       │ Targets:        │
                       │ • cAdvisor      │
                       │ • Envoy proxies │
                       │ • Node exporter │
                       └─────────────────┘
```

### Service Stack

1. **Applications**:
   - `gateway`: Main gateway service
   - `ms-exercise`: Exercise microservice
   - `ms-other`: Other microservice
   - `postgres`: PostgreSQL database

2. **Envoy Proxies**:
   - `gateway-envoy`: Gateway proxy (port 80→9901)
   - `ms-exercise-envoy`: ms-exercise proxy (port 15091→15090)
   - `ms-other-envoy`: ms-other proxy (port 15092→15090)

3. **Monitoring Stack**:
   - `prometheus`: Prometheus server (port 9090)
   - `cadvisor`: Container metrics (port 8081)
   - `node-exporter`: Host metrics (port 9100)

## Key Configurations

### Port Mapping

| Service | External Port | Internal Port | Function |
|---------|---------------|---------------|----------|
| gateway-envoy | 80 | 9901 | Main HTTP traffic |
| gateway-envoy | 15000 | 15000 | Admin interface |
| ms-exercise-envoy | 15091 | 15090 | Stats/metrics |
| ms-other-envoy | 15092 | 15090 | Stats/metrics |
| prometheus | 9090 | 9090 | Prometheus UI |
| cadvisor | 8081 | 8080 | cAdvisor UI |

### Network Configuration

- **monitoring**: Network for monitoring services (Prometheus, cAdvisor, Node Exporter)
- **backend**: Network for applications and database
- Envoy proxies are connected to **both** networks to enable communication

## Management Commands

### System Startup

```bash
# 1. Ensure Docker Swarm is initialized
docker swarm init

# 2. Deploy complete stack
docker stack deploy -c sou/monotloth-v5-envoy-simple.yml ms-stack-v5
```

### Status Verification

```bash
# Verify active services
docker service ls | grep ms-stack-v5

# Verify Prometheus targets
curl http://localhost:9090/targets
# Or visit http://localhost:9090/targets in browser
```

### System Shutdown

```bash
# Remove complete stack
docker stack rm ms-stack-v5

# Verify removal
docker service ls
```

### Specific Service Restart

```bash
# Restart Prometheus (after configuration changes)
docker service update --force ms-stack-v5_prometheus

# Restart single service
docker service update --force ms-stack-v5_gateway-envoy
```

## Load Testing Execution

### Single Test

```bash
python run_load_test.py \
    --users 50 \
    --spawn-rate 5 \
    --run-time 300s \
    --host http://localhost:80 \
    --csv results/test_envoy \
    --locust-file locust_file/SoyMonoShorterIfLogin_x1.py \
    --loadshape-file locust_file/loadshapes/constant_shape.py
```

### Debug Test

```bash
python debug_locust.py
```

## Prometheus Monitoring Queries

### 1. System Metrics (cAdvisor)

#### CPU Usage per Service
```promql
# CPU usage of all replicas for a service
sum(rate(container_cpu_usage_seconds_total{container_label_com_docker_swarm_service_name=~"ms-stack-v5_SERVICE_NAME.*"}[1m])) by (container_label_com_docker_swarm_service_name)

# Example for ms-exercise
sum(rate(container_cpu_usage_seconds_total{container_label_com_docker_swarm_service_name=~"ms-stack-v5_ms-exercise.*"}[1m]))
```

#### Memory Usage per Service
```promql
# Memory usage of all replicas for a service
sum(container_memory_usage_bytes{container_label_com_docker_swarm_service_name=~"ms-stack-v5_SERVICE_NAME.*"}) by (container_label_com_docker_swarm_service_name)

# Example for ms-exercise
sum(container_memory_usage_bytes{container_label_com_docker_swarm_service_name=~"ms-stack-v5_ms-exercise.*"})
```

#### Network I/O per Service
```promql
# Network receive rate
sum(rate(container_network_receive_bytes_total{container_label_com_docker_swarm_service_name=~"ms-stack-v5_SERVICE_NAME.*"}[1m])) by (container_label_com_docker_swarm_service_name)

# Network transmit rate
sum(rate(container_network_transmit_bytes_total{container_label_com_docker_swarm_service_name=~"ms-stack-v5_SERVICE_NAME.*"}[1m])) by (container_label_com_docker_swarm_service_name)
```

### 2. Application Metrics (Envoy)

#### Incoming Request Rate
```promql
# HTTP incoming request rate to gateway
rate(envoy_http_downstream_rq_total{envoy_http_conn_manager_prefix="gateway_hcm"}[1m])

# For specific services via cluster
rate(envoy_cluster_upstream_rq_total{envoy_cluster_name="CLUSTER_NAME"}[1m])

# Example for gateway
rate(envoy_cluster_upstream_rq_total{envoy_cluster_name="gateway_cluster"}[1m])
```

#### Completed Request Rate
```promql
# Rate of completed requests
rate(envoy_cluster_upstream_rq_completed{envoy_cluster_name="CLUSTER_NAME"}[1m])

# Example for gateway
rate(envoy_cluster_upstream_rq_completed{envoy_cluster_name="gateway_cluster"}[1m])
```

#### Response Time
```promql
# 95th percentile response time
histogram_quantile(0.95, rate(envoy_cluster_upstream_rq_time_bucket{envoy_cluster_name="CLUSTER_NAME"}[1m]))

# Average response time
rate(envoy_cluster_upstream_rq_time_sum{envoy_cluster_name="CLUSTER_NAME"}[1m]) / 
rate(envoy_cluster_upstream_rq_time_count{envoy_cluster_name="CLUSTER_NAME"}[1m])
```

#### Requests by Response Code
```promql
# Rate for specific response code
rate(envoy_cluster_upstream_rq{envoy_cluster_name="CLUSTER_NAME",envoy_response_code="200"}[1m])

# Rate by response class (2xx, 4xx, 5xx)
rate(envoy_cluster_upstream_rq_xx{envoy_cluster_name="CLUSTER_NAME",envoy_response_code_class="2"}[1m])
```

### 3. Replica Count

#### Replica Count per Service
```promql
# Number of active containers per service
count(container_last_seen{container_label_com_docker_swarm_service_name=~"ms-stack-v5_SERVICE_NAME.*"}) by (container_label_com_docker_swarm_service_name)

# Example for ms-exercise
count(container_last_seen{container_label_com_docker_swarm_service_name=~"ms-stack-v5_ms-exercise.*"})

# List all services and their replicas
count(container_last_seen{container_label_com_docker_stack_namespace="ms-stack-v5"}) by (container_label_com_docker_swarm_service_name)
```

## Parametric Queries for Dashboards

### Template for Specific Service

```promql
# Replace $service_name with service name (e.g: ms-exercise, gateway, ms-other)

# Total CPU Usage
sum(rate(container_cpu_usage_seconds_total{container_label_com_docker_swarm_service_name=~"ms-stack-v5_$service_name.*"}[1m]))

# Total Memory Usage  
sum(container_memory_usage_bytes{container_label_com_docker_swarm_service_name=~"ms-stack-v5_$service_name.*"})

# Network I/O
sum(rate(container_network_receive_bytes_total{container_label_com_docker_swarm_service_name=~"ms-stack-v5_$service_name.*"}[1m]))
sum(rate(container_network_transmit_bytes_total{container_label_com_docker_swarm_service_name=~"ms-stack-v5_$service_name.*"}[1m]))

# Replica Count
count(container_last_seen{container_label_com_docker_swarm_service_name=~"ms-stack-v5_$service_name.*"})
```

### Template for Envoy Cluster

```promql
# Replace $cluster_name with Envoy cluster name (e.g: gateway_cluster, ms_exercise_cluster)

# Request Rate
rate(envoy_cluster_upstream_rq_total{envoy_cluster_name="$cluster_name"}[1m])

# Completed Rate
rate(envoy_cluster_upstream_rq_completed{envoy_cluster_name="$cluster_name"}[1m])

# Response Time (95th)
histogram_quantile(0.95, rate(envoy_cluster_upstream_rq_time_bucket{envoy_cluster_name="$cluster_name"}[1m]))
```

## Useful Endpoints

- **Prometheus UI**: http://localhost:9090
- **cAdvisor UI**: http://localhost:8081  
- **Envoy Admin (Gateway)**: http://localhost:15000
- **Envoy Admin (ms-exercise)**: http://localhost:15001
- **Envoy Admin (ms-other)**: http://localhost:15002
- **Application**: http://localhost:80

## Troubleshooting

### Prometheus Targets DOWN

```bash
# Verify active services
docker service ls | grep envoy

# Verify service networks
docker service inspect ms-stack-v5_prometheus --format '{{.Spec.TaskTemplate.Networks}}'
docker service inspect ms-stack-v5_ms-exercise-envoy --format '{{.Spec.TaskTemplate.Networks}}'

# Should share at least one network
```

### Missing Metrics

```bash
# Test Envoy endpoint from inside network
docker exec -it $(docker ps --filter "name=prometheus" -q) wget -O- http://ms-stack-v5_gateway-envoy:15000/stats/prometheus | head -10
```

### Complete Restart

```bash
# Complete removal and re-deploy
docker stack rm ms-stack-v5
sleep 30
docker stack deploy -c sou/monotloth-v5-envoy-simple.yml ms-stack-v5
```

## Future Developments

1. **Grafana Dashboard**: Create dashboards for metrics visualization
2. **Alerting**: Configure alerts on critical thresholds
3. **Automation**: Scripts for deployment and monitoring automation
4. **Scaling**: Integration with automatic controller for dynamic scaling
5. **Correlation**: Algorithms for system/application metrics correlation

## Key Files

- `sou/monotloth-v5-envoy-simple.yml`: Main Docker stack
- `prometheus/prometheus-envoy.yml`: Prometheus configuration  
- `sou/envoy-config/`: Envoy configurations for each service
- `debug_locust.py`: Debug test script
- `run_load_test.py`: Main load testing script