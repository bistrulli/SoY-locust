#!/usr/bin/env python3
"""
Test the fixed replica counting queries
"""

print("🔍 Test these FIXED queries in Prometheus:")
print("=" * 60)

services = ["ms-exercise", "gateway", "ms-other"]
stack_name = "ms-stack-v5"

for i, service in enumerate(services, 1):
    print(f"\n{i}. Service: {service}")
    full_service_name = f"{stack_name}_{service}"
    
    replica_query = f'count(container_last_seen{{container_label_com_docker_swarm_service_name="{full_service_name}"}})'
    cpu_query = f'sum(rate(container_cpu_usage_seconds_total{{container_label_com_docker_swarm_service_name="{full_service_name}"}}[1m]))'
    
    print(f"   Replicas: {replica_query}")
    print(f"   CPU:      {cpu_query}")

print("\n" + "=" * 60)
print("✅ These queries should now work!")
print("- Each service has multiple containers (replicas) with the SAME service_name")
print("- count() will return the number of containers = number of replicas")
print("- sum(rate()) will return total CPU usage across all replicas")