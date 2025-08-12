#!/usr/bin/env python3
"""
Debug script to find actual cAdvisor container metrics for replica counting
"""

queries_to_test = [
    # Original query that's failing
    'container_last_seen{container_label_com_docker_swarm_service_name=~"ms-stack-v5_.*"}',
    
    # Alternative cAdvisor metrics for counting containers
    'container_cpu_usage_seconds_total{container_label_com_docker_swarm_service_name=~"ms-stack-v5_.*"}',
    'container_memory_usage_bytes{container_label_com_docker_swarm_service_name=~"ms-stack-v5_.*"}',
    'container_spec_cpu_quota{container_label_com_docker_swarm_service_name=~"ms-stack-v5_.*"}',
    
    # Check all container metrics with swarm labels
    '{__name__=~"container_.*", container_label_com_docker_swarm_service_name=~"ms-stack-v5_.*"}',
    
    # Maybe the label name is different
    'container_last_seen{service=~"ms-stack-v5_.*"}',
    'container_cpu_usage_seconds_total{service=~"ms-stack-v5_.*"}',
    
    # Check what labels actually exist for containers
    '{__name__=~"container_.*"}',
    
    # Test specific services
    'container_cpu_usage_seconds_total{container_label_com_docker_swarm_service_name="ms-stack-v5_ms-exercise"}',
    'container_cpu_usage_seconds_total{container_label_com_docker_swarm_service_name="ms-stack-v5_gateway"}',
    'container_cpu_usage_seconds_total{container_label_com_docker_swarm_service_name="ms-stack-v5_ms-other"}',
]

print("🔍 Testing cAdvisor container metrics for replica counting...")
print("Paste these queries into Prometheus to find working metrics:")
print("=" * 80)

for i, query in enumerate(queries_to_test, 1):
    print(f"{i:2d}. {query}")

print("\n" + "=" * 80)
print("INSTRUCTIONS:")
print("1. Run these queries in Prometheus")  
print("2. Find which one returns actual data")
print("3. Check the labels to see the exact service name format")
print("4. Report back with working query and we'll update get_active_replicas()")
print("\nLook for queries that return containers for your services!")